import logging

from automation.tasks.abstractTask import AbstractTask
from django.core.management import call_command

logger = logging.getLogger("mgmt.management.commands.ADSync")


class ADSync(AbstractTask):
    """Sync Active Directory computer objects for all active domains."""

    def execute(self):
        logger.info("Starting Active Directory synchronization")
        call_command("ad_sync")
        logger.info("Active Directory synchronization completed")
