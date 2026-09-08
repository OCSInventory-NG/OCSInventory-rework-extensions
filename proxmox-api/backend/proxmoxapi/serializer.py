from rest_framework import serializers
from .models import ProxmoxAsset, ProxmoxServer
from ocsinventory_backend.ocs_framework.viewsets import ExpandableFieldsMixin
from rest_framework.serializers import ModelSerializer

class ProxmoxServerSerializer(ExpandableFieldsMixin, ModelSerializer):
    description = serializers.CharField(allow_blank=True, allow_null=True, required=False, default="")

    def validate_description(self, value):
        return value or ""

    class Meta:
        model = ProxmoxServer
        fields = [
            "id",
            "name",
            "description",
            "ip_address",
            "port",
            "node_names",
            "username",
            "token_id",
            "token_secret",
            "request_delay",
            "is_active",
            "created_at",
            "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProxmoxAssetSerializer(ModelSerializer):
    asset_name = serializers.CharField(source="asset.name", read_only=True)

    class Meta:
        model = ProxmoxAsset
        fields = [
            "id",
            "server",
            "asset",
            "asset_name",
            "vmid",
            "resource_type",
            "status",
            "last_update",
        ]
        read_only_fields = ["id", "asset_name", "last_update"]
