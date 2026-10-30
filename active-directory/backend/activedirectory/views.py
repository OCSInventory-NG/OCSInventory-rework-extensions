import logging

import django_filters
from asset.inventory_base.models import InventoryBase
from permission.permissions import DefaultModelPermissions
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.response import Response

from .ldap_client import test_connection
from .models import ADComputer, ADDomain, SyncReport
from .serializers import (
    ADComputerSerializer,
    ADDomainSerializer,
    ADDomainTestSerializer,
    SyncReportSerializer,
)

logger = logging.getLogger("extensions.activedirectory")


class RequireChangePermission(DjangoModelPermissions):
    """
    Require change_<model> for every method, for actions that are not plain
    CRUD (test/link/unlink) but still change or probe server-side state.
    """

    perms_map = {method: ["%(app_label)s.change_%(model_name)s"] for method in DjangoModelPermissions.perms_map}


class RequireAddOrChangePermission(DjangoModelPermissions):
    """
    Require add_<model> OR change_<model>: the non-detail test/ action is
    used from the creation form (no domain saved yet, needs add_addomain)
    as well as, potentially, an edit context.
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        model = self._queryset(view).model
        app_label = model._meta.app_label
        model_name = model._meta.model_name
        return user.has_perm(f"{app_label}.add_{model_name}") or user.has_perm(
            f"{app_label}.change_{model_name}"
        )


CONNECTION_TARGET_FIELDS = ("server", "port", "security", "verify_certificate", "bind_dn")


def _run_connection_test(payload, stored_domain=None):
    serializer = ADDomainTestSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    if not serializer.validated_data.get("bind_password"):
        target_changed = stored_domain is None or any(
            serializer.validated_data[field] != getattr(stored_domain, field)
            for field in CONNECTION_TARGET_FIELDS
        )
        if target_changed:
            raise serializers.ValidationError(
                {"bind_password": "Enter the password to test these connection settings."}
            )
        serializer.validated_data["bind_password"] = stored_domain.bind_password

    # Never saved: connect() only reads these fields, it never persists
    # the unvalidated/not-yet-confirmed candidate.
    candidate = ADDomain(**serializer.validated_data)

    ok, error = test_connection(candidate)
    if ok:
        return Response({"ok": True, "server": candidate.server})
    return Response({"ok": False, "error": error})


class ADDomainViewSet(viewsets.ModelViewSet):
    permission_classes = [DefaultModelPermissions]
    queryset = ADDomain.objects.all()
    serializer_class = ADDomainSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "server", "base_dn"]
    ordering_fields = ["id", "name", "last_sync_at", "last_sync_status"]

    @action(detail=True, methods=["post"], url_path="test", permission_classes=[RequireChangePermission])
    def test_existing(self, request, pk=None):
        """
        Test the connection using the submitted form fields (edit form),
        not blindly the saved row: an admin must be able to try a server or
        credential change before saving it. An empty/missing bind_password
        falls back to the one already stored, as long as the connection
        target is unchanged (see CONNECTION_TARGET_FIELDS).
        """
        return _run_connection_test(request.data, stored_domain=self.get_object())

    @action(
        detail=False,
        methods=["post"],
        url_path="test",
        permission_classes=[RequireAddOrChangePermission],
    )
    def test_new(self, request):
        """
        Same as above, for the creation form: there is no saved domain yet,
        so bind_password can't fall back to anything and is required.
        """
        return _run_connection_test(request.data)


class ADComputerFilterSet(django_filters.FilterSet):
    ou = django_filters.CharFilter(field_name="ou", lookup_expr="icontains")

    class Meta:
        model = ADComputer
        fields = ["domain", "asset", "match_status", "in_directory", "ou", "enabled"]


class ADComputerViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Read-only plus delete: rows only ever come from a sync (no create/update
    through the API), but a row for a computer no longer in the directory
    (in_directory=False) can be removed by hand. A later sync recreates it
    if the object still exists in AD, so deleting is never destructive of
    directory data - it only clears OCS Inventory's local record.
    """

    permission_classes = [DefaultModelPermissions]
    queryset = ADComputer.objects.select_related("domain", "asset").all()
    serializer_class = ADComputerSerializer
    filterset_class = ADComputerFilterSet
    filter_backends = [
        django_filters.rest_framework.DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]
    search_fields = ["name", "dns_hostname", "assigned_user_name", "assigned_user_login"]
    ordering_fields = ["id", "name", "ou", "match_status", "last_seen_at"]

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """
        Aggregate counts for the computer list, so a server-paginated list
        doesn't need every row loaded client side to show totals/filters.
        Accepts the same ?domain= filter as the list endpoint.
        """
        queryset = ADComputer.objects.all()
        domain_id = request.query_params.get("domain")
        if domain_id:
            queryset = queryset.filter(domain_id=domain_id)

        # Removed computers keep their match_status: match counts only use present ones.
        present = queryset.filter(in_directory=True)
        return Response({
            "total": queryset.count(),
            "linked": present.filter(match_status="linked").count(),
            "unlinked": present.filter(match_status="unlinked").count(),
            "ambiguous": present.filter(match_status="ambiguous").count(),
            "removed": queryset.filter(in_directory=False).count(),
        })

    @action(detail=True, methods=["post"], permission_classes=[RequireChangePermission])
    def link(self, request, pk=None):
        computer = self.get_object()
        asset_id = request.data.get("asset")
        if not asset_id:
            return Response(
                {"asset": "This field is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            asset = InventoryBase.objects.get(id=asset_id)
        except InventoryBase.DoesNotExist:
            return Response(
                {"asset": "No asset found with this id."}, status=status.HTTP_400_BAD_REQUEST
            )

        if ADComputer.objects.filter(asset=asset).exclude(id=computer.id).exists():
            return Response(
                {"asset": "This asset is already linked to another AD computer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        computer.asset = asset
        computer.link_mode = "manual"
        computer.match_status = "linked"
        computer.save(update_fields=["asset", "link_mode", "match_status"])

        return Response(self.get_serializer(computer).data)

    @action(detail=True, methods=["post"], permission_classes=[RequireChangePermission])
    def unlink(self, request, pk=None):
        computer = self.get_object()
        computer.asset = None
        # "manual_unlinked", not "": a plain sync must not silently relink
        # this computer on its next run, the same way it would never
        # overwrite a manual link.
        computer.link_mode = "manual_unlinked"
        computer.match_status = "unlinked"
        computer.save(update_fields=["asset", "link_mode", "match_status"])

        return Response(self.get_serializer(computer).data)


class SyncReportViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [DefaultModelPermissions]
    queryset = SyncReport.objects.select_related("domain").all()
    serializer_class = SyncReportSerializer
    filter_backends = [
        django_filters.rest_framework.DjangoFilterBackend,
        OrderingFilter,
    ]
    filterset_fields = ["domain"]
    ordering_fields = ["id", "started_at", "status"]
