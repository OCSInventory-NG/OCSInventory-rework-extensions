from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ProxmoxAsset, ProxmoxServer
from .serializer import ProxmoxAssetSerializer, ProxmoxServerSerializer
from permission.permissions import DefaultModelPermissions
from rest_framework.filters import OrderingFilter, SearchFilter


class ProxmoxServerViewSet(viewsets.ModelViewSet):
    permission_classes = [DefaultModelPermissions]
    queryset = ProxmoxServer.objects.all()
    serializer_class = ProxmoxServerSerializer
    model = ProxmoxServer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "ip_address", "username"]
    ordering_fields = ["id", "name", "ip_address", "created_at", "updated_at"]

    @action(detail=True, methods=["get"], url_path="assets")
    def assets(self, request, pk=None):
        server = self.get_object()
        qs = server.proxmox_assets.select_related("asset").all()
        serializer = ProxmoxAssetSerializer(qs, many=True)
        return Response(serializer.data)


class ProxmoxAssetViewSet(viewsets.ModelViewSet):
    permission_classes = [DefaultModelPermissions]
    queryset = ProxmoxAsset.objects.select_related("server", "asset").all()
    serializer_class = ProxmoxAssetSerializer
    model = ProxmoxAsset
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["server__name", "asset__name", "resource_type", "status"]
    ordering_fields = ["id", "vmid", "resource_type", "status", "last_update"]
