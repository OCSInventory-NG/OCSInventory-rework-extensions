import logging

from django.apps import AppConfig

logger = logging.getLogger("extensions.proxmoxapi")


class ProxmoxEnrichedInventoryReceivedResolver:
    """
    Wraps the core 'inventory_received' resolver to also expose proxmox sync
    context (server/node/vmid/resource_type/status) when it is available on
    the instance, so proxmox-specific rules can be written on the existing
    'inventory_received' trigger instead of a dedicated one.
    """

    proxmox_schema = {
        "proxmox": {
            "server":        {"type": "string"},
            "node":          {"type": "string"},
            "vmid":          {"type": "integer"},
            "resource_type": {"type": "string"},
            "status":        {"type": "string"},
        }
    }

    def __init__(self, base_resolver):
        self.base_resolver = base_resolver

    def build(self, instance):
        data = self.base_resolver.build(instance)
        proxmox_data = getattr(instance, "_proxmox_context_data", None)
        if proxmox_data:
            data["proxmox"] = proxmox_data
        return data

    def get_schema(self):
        schema = dict(self.base_resolver.get_schema())
        schema.update(self.proxmox_schema)
        return schema


class ProxmoxapiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "extensions.proxmoxapi"
    verbose_name = "Proxmox API Extension"

    def ready(self):
        try:
            import sys
            from extensions.proxmoxapi.management import proxmoxInventory
            sys.modules["automation.tasks.proxmoxInventory"] = proxmoxInventory

            self._extend_inventory_received_context()
        except Exception:
            logger.exception(
                "proxmoxapi extension failed to initialize."
            )

    def _extend_inventory_received_context(self):
        from automation.rule.context import (
            RESOLVER_REGISTRY,
            TRIGGER_DEFAULT_RESOLVERS,
            get_resolver_for_trigger,
        )

        base_resolver = get_resolver_for_trigger("inventory_received")
        if isinstance(base_resolver, ProxmoxEnrichedInventoryReceivedResolver):
            return

        slug = TRIGGER_DEFAULT_RESOLVERS.get("inventory_received", "inventory_received")
        RESOLVER_REGISTRY[slug] = ProxmoxEnrichedInventoryReceivedResolver(base_resolver)


