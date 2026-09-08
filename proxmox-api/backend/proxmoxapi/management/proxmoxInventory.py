import logging

from automation.tasks.abstractTask import AbstractTask
from django.core.management import call_command

logger = logging.getLogger("mgmt.management.commands.ProxmoxInventory")


class ProxmoxInventory(AbstractTask):
    """Sync Proxmox VE VMs and LXC containers as inventory assets."""

    def execute(self):
        logger.info("Starting Proxmox inventory synchronization")
        call_command("proxmox_inventory")
        logger.info("Proxmox inventory synchronization completed")
