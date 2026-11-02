import re

from rest_framework import serializers

from .models import ADComputer, ADDomain, SyncReport

ATTRIBUTE_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")


class ADDomainSerializer(serializers.ModelSerializer):
    bind_password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, style={"input_type": "password"}
    )
    has_password = serializers.SerializerMethodField()
    computers_count = serializers.SerializerMethodField()

    class Meta:
        model = ADDomain
        fields = [
            "id",
            "name",
            "server",
            "port",
            "security",
            "verify_certificate",
            "bind_dn",
            "bind_password",
            "has_password",
            "base_dn",
            "assigned_user_attribute",
            "is_active",
            "last_sync_at",
            "last_sync_status",
            "computers_count",
        ]
        read_only_fields = ["id", "last_sync_at", "last_sync_status"]

    def get_has_password(self, obj):
        return bool(obj.bind_password)

    def get_computers_count(self, obj):
        return obj.computers.count()

    def validate_port(self, value):
        if not (1 <= value <= 65535):
            raise serializers.ValidationError("Port must be between 1 and 65535.")
        return value

    def validate_assigned_user_attribute(self, value):
        if not ATTRIBUTE_NAME_PATTERN.match(value):
            raise serializers.ValidationError(
                "Must be a valid LDAP attribute name."
            )
        return value

    def validate(self, attrs):
        # Required at creation; an empty/missing value on update keeps the
        # stored password (see update()).
        if self.instance is None and not attrs.get("bind_password"):
            raise serializers.ValidationError(
                {"bind_password": "This field is required when creating a domain."}
            )
        return attrs

    def update(self, instance, validated_data):
        if not validated_data.get("bind_password"):
            validated_data.pop("bind_password", None)
        return super().update(instance, validated_data)


class ADDomainTestSerializer(serializers.Serializer):
    """
    Validates the connection fields sent to test/, which may describe a
    domain not yet saved (creation form) or override some fields of an
    existing one (edit form) rather than always testing the stored row.
    """

    server = serializers.CharField()
    port = serializers.IntegerField(min_value=1, max_value=65535, default=636)
    security = serializers.ChoiceField(choices=ADDomain.SECURITY_CHOICES, default="ldaps")
    verify_certificate = serializers.BooleanField(default=True)
    bind_dn = serializers.CharField()
    bind_password = serializers.CharField(required=False, allow_blank=True, default="")
    base_dn = serializers.CharField()


class AssignedUserSerializer(serializers.Serializer):
    raw = serializers.CharField()
    name = serializers.CharField()
    login = serializers.CharField()
    email = serializers.CharField()


class ADComputerSerializer(serializers.ModelSerializer):
    domain_name = serializers.CharField(source="domain.name", read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True, default=None)
    assigned_user = serializers.SerializerMethodField()

    class Meta:
        model = ADComputer
        fields = [
            "id",
            "domain",
            "domain_name",
            "object_guid",
            "name",
            "dns_hostname",
            "distinguished_name",
            "ou",
            "ou_path",
            "os_name",
            "os_version",
            "enabled",
            "description",
            "when_created",
            "last_logon",
            "password_last_set",
            "assigned_user",
            "asset",
            "asset_name",
            "link_mode",
            "match_status",
            "in_directory",
            "last_seen_at",
        ]
        read_only_fields = fields

    def get_assigned_user(self, obj):
        return {
            "raw": obj.assigned_user_raw,
            "name": obj.assigned_user_name,
            "login": obj.assigned_user_login,
            "email": obj.assigned_user_email,
        }


class SyncReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncReport
        fields = [
            "id",
            "domain",
            "status",
            "started_at",
            "finished_at",
            "created_count",
            "updated_count",
            "linked_count",
            "missing_count",
            "error_message",
        ]
        read_only_fields = fields
