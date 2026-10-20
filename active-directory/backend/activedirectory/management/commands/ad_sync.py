import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from extensions.activedirectory.ldap_client import (
    LDAPConnectionError,
    connect,
    iter_computers,
    resolve_assigned_user,
)
from extensions.activedirectory.matching import find_asset_candidates, match_status_for
from extensions.activedirectory.models import ADComputer, ADDomain, SyncReport

logger = logging.getLogger("mgmt.management.commands.ad_sync")


class Command(BaseCommand):
    help = "Synchronize Active Directory computer objects for active domains"

    def add_arguments(self, parser):
        parser.add_argument(
            "--domain",
            type=int,
            help="Restrict the sync to a single domain id",
        )

    def handle(self, *args, **options):
        domains = ADDomain.objects.filter(is_active=True)
        if options.get("domain"):
            domains = domains.filter(id=options["domain"])
            if not domains.exists():
                raise CommandError(f"No active domain found with id {options['domain']}")

        if not domains.exists():
            logger.info("No active Active Directory domain configured.")
            return

        for domain in domains:
            sync_domain(domain)


def is_sync_running(domain):
    return SyncReport.objects.filter(domain=domain, status="running").exists()


def sync_domain(domain):
    if is_sync_running(domain):
        logger.warning("Sync already running for domain %s, skipping.", domain.name)
        return None

    report = SyncReport.objects.create(domain=domain, status="running")
    created = updated = linked = 0
    seen_guids = set()

    try:
        conn = connect(domain)
        try:
            for entry in iter_computers(domain):
                seen_guids.add(entry["object_guid"])
                was_created, was_linked = upsert_computer(domain, entry, conn)
                created += int(was_created)
                updated += int(not was_created)
                linked += int(was_linked)
        finally:
            conn.unbind_s()

        missing = mark_missing_computers(domain, seen_guids)

        report.status = "success"
        report.created_count = created
        report.updated_count = updated
        report.linked_count = linked
        report.missing_count = missing
        report.finished_at = timezone.now()
        report.save()

        domain.last_sync_at = report.finished_at
        domain.last_sync_status = "success"
        domain.save(update_fields=["last_sync_at", "last_sync_status"])

        logger.info(
            "Domain %s: %d created, %d updated, %d linked, %d missing",
            domain.name, created, updated, linked, missing,
        )
    except LDAPConnectionError as exc:
        report.status = "error"
        report.error_message = str(exc)
        report.finished_at = timezone.now()
        report.save()

        domain.last_sync_at = report.finished_at
        domain.last_sync_status = "error"
        domain.save(update_fields=["last_sync_at", "last_sync_status"])

        logger.error("Domain %s sync failed: %s", domain.name, exc)

    return report


def upsert_computer(domain, entry, conn):
    assigned_name, assigned_login, assigned_email = resolve_assigned_user(
        domain, conn, entry["assigned_user_raw"]
    )

    computer, created = ADComputer.objects.get_or_create(
        domain=domain,
        object_guid=entry["object_guid"],
        defaults={"name": entry["name"]},
    )

    computer.name = entry["name"]
    computer.dns_hostname = entry["dns_hostname"]
    computer.distinguished_name = entry["distinguished_name"]
    computer.ou = entry["ou"]
    computer.ou_path = build_ou_path(entry["ou"])
    computer.os_name = entry["os_name"]
    computer.os_version = entry["os_version"]
    computer.enabled = entry["enabled"]
    computer.description = entry["description"]
    computer.when_created = entry["when_created"]
    computer.last_logon = entry["last_logon"]
    computer.password_last_set = entry["password_last_set"]
    computer.assigned_user_raw = entry["assigned_user_raw"]
    computer.assigned_user_name = assigned_name
    computer.assigned_user_login = assigned_login
    computer.assigned_user_email = assigned_email
    computer.in_directory = True
    computer.last_seen_at = timezone.now()

    was_linked = False
    if computer.link_mode != "manual":
        candidates = find_asset_candidates(entry["sam_account_name"] or entry["name"])
        status = match_status_for(candidates.count())
        computer.match_status = status
        if status == "linked":
            computer.asset = candidates.first()
            computer.link_mode = "auto"
            was_linked = True
        else:
            computer.asset = None
            computer.link_mode = ""

    computer.save()
    return created, was_linked


def build_ou_path(ou_dn):
    """'OU=Laptops,OU=Paris,DC=corp,DC=local' -> 'Paris / Laptops'."""
    if not ou_dn:
        return ""
    parts = [
        part.split("=", 1)[1]
        for part in ou_dn.split(",")
        if part.upper().startswith("OU=")
    ]
    return " / ".join(reversed(parts))


def mark_missing_computers(domain, seen_guids):
    missing_qs = (
        ADComputer.objects.filter(domain=domain, in_directory=True)
        .exclude(object_guid__in=seen_guids)
    )
    count = missing_qs.count()
    missing_qs.update(in_directory=False)
    return count
