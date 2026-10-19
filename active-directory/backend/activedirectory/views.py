import django_filters
from asset.inventory_base.models import InventoryBase
from django.core.management import call_command
from permission.permissions import DefaultModelPermissions
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.response import Response

from .ldap_client import test_connection
from .management.commands.ad_sync import is_sync_running
from .models import ADComputer, ADDomain, SyncReport
from .serializers import ADComputerSerializer, ADDomainSerializer, SyncReportSerializer


class RequireChangePermission(DjangoModelPermissions):
    """
    Require change_<model> for every method, for actions that are not plain
    CRUD (test/sync/link/unlink) but still change or probe server-side state.
    """

    perms_map = {method: ["%(app_label)s.change_%(model_name)s"] for method in DjangoModelPermissions.perms_map}


class ADDomainViewSet(viewsets.ModelViewSet):
    permission_classes = [DefaultModelPermissions]
    queryset = ADDomain.objects.all()
    serializer_class = ADDomainSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "server", "base_dn"]
    ordering_fields = ["id", "name", "last_sync_at", "last_sync_status"]

    @action(detail=True, methods=["post"], permission_classes=[RequireChangePermission])
    def test(self, request, pk=None):
        domain = self.get_object()
        ok, error = test_connection(domain)
        if ok:
            return Response({"ok": True, "server": domain.server})
        return Response({"ok": False, "error": error})

    @action(detail=True, methods=["post"], permission_classes=[RequireChangePermission])
    def sync(self, request, pk=None):
        domain = self.get_object()
        if is_sync_running(domain):
            return Response(
                {"detail": "A synchronization is already running for this domain."},
                status=status.HTTP_409_CONFLICT,
            )

        call_command("ad_sync", domain=domain.id)
        report = SyncReport.objects.filter(domain=domain).order_by("-started_at").first()
        return Response({"report": report.id if report else None}, status=status.HTTP_202_ACCEPTED)


class ADComputerFilterSet(django_filters.FilterSet):
    ou = django_filters.CharFilter(field_name="ou", lookup_expr="icontains")

    class Meta:
        model = ADComputer
        fields = ["domain", "asset", "match_status", "in_directory", "ou"]


class ADComputerViewSet(viewsets.ReadOnlyModelViewSet):
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
        computer.link_mode = ""
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
