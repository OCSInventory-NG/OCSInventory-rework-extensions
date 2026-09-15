import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.db import models

HOSTNAME_PATTERN = re.compile(
    r'^(?=.{1,255}$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.?$'
)


def validate_hostname_or_ip(value):
    try:
        validate_ipv46_address(value)
    except ValidationError:
        if not HOSTNAME_PATTERN.match(value):
            raise ValidationError(
                "Enter a valid IPv4, IPv6 address, or hostname.",
                code="invalid",
            )


class ProxmoxServer(models.Model):
    """Modèle pour stocker les informations de connexion d'un hyperviseur Proxmox"""
    
    name = models.CharField(max_length=255, unique=True)
    description = models.CharField(max_length=255, blank=True, default="")
    ip_address = models.CharField(max_length=255, validators=[validate_hostname_or_ip])
    port = models.IntegerField(default=8006)
    node_names = models.JSONField(default=list)
    username = models.CharField(max_length=255)
    token_id = models.CharField(max_length=255)
    token_secret = models.CharField(max_length=512)
    request_delay = models.FloatField(default=3000)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-updated_at"]
    
    def __str__(self):
        return f"{self.name} ({self.ip_address}:{self.port})"


class ProxmoxAsset(models.Model):
    """Link between a ProxmoxServer and an InventoryBase asset."""

    server = models.ForeignKey(
        ProxmoxServer,
        on_delete=models.CASCADE,
        related_name="proxmox_assets",
    )
    asset = models.OneToOneField(
        "inventory_base.InventoryBase",
        on_delete=models.CASCADE,
        related_name="proxmox_asset",
    )
    vmid = models.IntegerField()
    resource_type = models.CharField(
        max_length=10,
        choices=[("qemu", "QEMU VM"), ("lxc", "LXC Container")],
    )
    status = models.CharField(max_length=50, blank=True)
    last_update = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("server", "vmid", "resource_type")]
        ordering = ["server", "resource_type", "vmid"]

    def __str__(self):
        return f"{self.server.name} - {self.resource_type.upper()} {self.vmid}"
