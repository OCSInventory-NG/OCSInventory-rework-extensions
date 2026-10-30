import json
import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from extensions.activedirectory.ldap_client import connect, iter_computers, resolve_assigned_user
from extensions.activedirectory.matching import find_asset_candidates, match_status_for
from extensions.activedirectory.models import ADComputer, ADDomain, SyncReport

logger = logging.getLogger("mgmt.management.commands.ad_sync")

_CONFIG = json.loads((Path(__file__).resolve().parents[2] / "config.json").read_text())

# A running SyncReport older than this is considered abandoned (process
# killed, timeout, crash): is_sync_running() ignores it so the domain is
# never stuck forever behind a report that will never be closed.
STALE_RUNNING_REPORT_SECONDS = _CONFIG["stale_running_report_seconds"]


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


def _close_stale_running_reports(domain):
    """
    Close 'running' reports abandoned by a killed process or a timeout.

    A report stuck in 'running' forever would permanently block every future
    sync for this domain (manual and scheduled alike), since is_sync_running()
    would never see it close on its own.
    """
    cutoff = timezone.now() - timezone.timedelta(seconds=STALE_RUNNING_REPORT_SECONDS)

    stale_reports = SyncReport.objects.filter(
        domain=domain, status="running", started_at__lt=cutoff
    )
    for stale_report in stale_reports:
        logger.warning(
            "Domain %s: sync report %s has been running since %s, marking as abandoned.",
            domain.name, stale_report.id, stale_report.started_at,
        )
        stale_report.status = "error"
        stale_report.error_message = (
            f"Abandoned: still 'running' after more than "
            f"{STALE_RUNNING_REPORT_SECONDS}s (process likely killed or timed out)."
        )
        stale_report.finished_at = timezone.now()
        stale_report.save()


def is_sync_running(domain):
    """Tell whether a (non abandoned) sync is currently running for this domain."""
    _close_stale_running_reports(domain)
    return SyncReport.objects.filter(domain=domain, status="running").exists()


def start_sync_report(domain):
    """
    Atomically create the 'running' SyncReport for a sync about to start, or
    return None if one is already in progress.

    Locks the domain row for the check-then-create so two concurrent sync
    requests (e.g. a manual trigger racing the scheduler) can't both pass the
    is_sync_running() check and create two running reports at once.
    """
    with transaction.atomic():
        ADDomain.objects.select_for_update().get(id=domain.id)
        if is_sync_running(domain):
            return None
        return SyncReport.objects.create(domain=domain, status="running")


def sync_domain(domain):
    report = start_sync_report(domain)
    if report is None:
        logger.warning("Sync already running for domain %s, skipping.", domain.name)
        return None

    created = updated = linked = errors = 0
    seen_guids = set()

    try:
        conn = connect(domain)
        try:
            for entry in iter_computers(domain):
                seen_guids.add(entry["object_guid"])
                try:
                    with transaction.atomic():
                        was_created, was_changed, was_linked = upsert_computer(domain, entry, conn)
                    created += int(was_created)
                    updated += int(was_changed and not was_created)
                    linked += int(was_linked)
                except Exception:
                    errors += 1
                    logger.exception(
                        "Domain %s: failed to process computer %s (guid=%s), skipping it.",
                        domain.name, entry.get("name"), entry.get("object_guid"),
                    )
        finally:
            conn.unbind_s()

        missing = mark_missing_computers(domain, seen_guids)

        report.status = "success" if errors == 0 else "error"
        report.created_count = created
        report.updated_count = updated
        report.linked_count = linked
        report.missing_count = missing
        if errors:
            report.error_message = (
                f"{errors} computer(s) failed to process and were skipped; "
                "see the server log for details."
            )
        report.finished_at = timezone.now()
        report.save()

        domain.last_sync_at = report.finished_at
        domain.last_sync_status = report.status
        domain.save(update_fields=["last_sync_at", "last_sync_status"])

        logger.info(
            "Domain %s: %d created, %d updated, %d linked, %d missing, %d error(s)",
            domain.name, created, updated, linked, missing, errors,
        )
    except Exception as exc:
        report.status = "error"
        report.error_message = str(exc)
        report.finished_at = timezone.now()
        report.save()

        domain.last_sync_at = report.finished_at
        domain.last_sync_status = "error"
        domain.save(update_fields=["last_sync_at", "last_sync_status"])

        logger.exception("Domain %s sync failed: %s", domain.name, exc)

    return report


# Fields compared to tell a real update from a computer that was simply
# seen again unchanged (last_seen_at/in_directory always change, so they are
# deliberately excluded from the comparison).
_TRACKED_FIELDS = [
    "name", "dns_hostname", "distinguished_name", "ou", "ou_path",
    "os_name", "os_version", "enabled", "description", "when_created",
    "last_logon", "password_last_set", "assigned_user_raw",
    "assigned_user_name", "assigned_user_login", "assigned_user_email",
]


def upsert_computer(domain, entry, conn):
    assigned_name, assigned_login, assigned_email = resolve_assigned_user(
        domain, conn, entry["assigned_user_raw"]
    )

    computer, created = ADComputer.objects.get_or_create(
        domain=domain,
        object_guid=entry["object_guid"],
        defaults={"name": entry["name"]},
    )

    before = {field: getattr(computer, field) for field in _TRACKED_FIELDS}

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

    changed = any(before[field] != getattr(computer, field) for field in _TRACKED_FIELDS)

    was_linked = False
    if computer.link_mode not in ("manual", "manual_unlinked"):
        candidates = find_asset_candidates(entry["sam_account_name"] or entry["name"])
        status = match_status_for(candidates.count())

        if status == "linked":
            candidate = candidates.first()
            # asset is a OneToOneField: linking a candidate already held by
            # another ADComputer would raise an IntegrityError. This happens
            # when two domains have a computer with the same name, or when a
            # computer was recreated in AD (new objectGUID, same name) before
            # the old row was marked missing. Free the asset if its current
            # holder is gone from its directory, otherwise leave this
            # computer ambiguous instead of crashing the sync.
            holder = ADComputer.objects.filter(asset=candidate).exclude(id=computer.id).first()
            if holder is not None:
                if holder.in_directory:
                    status = "ambiguous"
                else:
                    holder.asset = None
                    holder.link_mode = ""
                    holder.match_status = "unlinked"
                    holder.save(update_fields=["asset", "link_mode", "match_status"])

        computer.match_status = status
        if status == "linked":
            computer.asset = candidate
            computer.link_mode = "auto"
            was_linked = True
        else:
            computer.asset = None
            computer.link_mode = ""

    computer.save()
    return created, changed, was_linked


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
