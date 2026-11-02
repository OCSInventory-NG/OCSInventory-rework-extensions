import logging

from django.apps import AppConfig

logger = logging.getLogger("extensions.activedirectory")


class ADEnrichedInventoryReceivedResolver:
    """
    Wraps the core 'inventory_received' resolver to also expose the AD
    computer linked to the asset (domain/ou/enabled/assigned_user), so AD
    based rules can be written on the existing trigger instead of a new one.
    """

    ad_schema = {
        "activedirectory": {
            "domain": {"type": "string"},
            "ou": {"type": "string"},
            "enabled": {"type": "boolean"},
            "assigned_user": {"type": "string"},
        }
    }

    def __init__(self, base_resolver):
        self.base_resolver = base_resolver

    def build(self, instance):
        data = self.base_resolver.build(instance)
        computer = getattr(instance, "ad_computer", None)
        if computer is not None:
            data["activedirectory"] = {
                "domain": computer.domain.name,
                "ou": computer.ou,
                "enabled": computer.enabled,
                "assigned_user": computer.assigned_user_login or "",
            }
        return data

    def get_schema(self):
        schema = dict(self.base_resolver.get_schema())
        schema.update(self.ad_schema)
        return schema


class ActivedirectoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "extensions.activedirectory"
    verbose_name = "Active Directory"

    def ready(self):
        try:
            import sys

            from extensions.activedirectory.management import ad_sync_task

            sys.modules["automation.tasks.ad_sync_task"] = ad_sync_task

            self._extend_inventory_received_context()
        except Exception:
            logger.exception("activedirectory extension failed to initialize.")

    def _extend_inventory_received_context(self):
        from automation.rule.context import (
            RESOLVER_REGISTRY,
            TRIGGER_DEFAULT_RESOLVERS,
            get_resolver_for_trigger,
        )

        base_resolver = get_resolver_for_trigger("inventory_received")
        if isinstance(base_resolver, ADEnrichedInventoryReceivedResolver):
            return

        slug = TRIGGER_DEFAULT_RESOLVERS.get("inventory_received", "inventory_received")
        RESOLVER_REGISTRY[slug] = ADEnrichedInventoryReceivedResolver(base_resolver)
