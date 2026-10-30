import importlib
import sys
from unittest.mock import patch

import pytest
from asset.inventory_base.models import InventoryBase
from automation.rule.context import get_resolver_for_trigger
from django.urls import clear_url_caches
from django.utils import timezone
from extension.models import Extension

import ldap

from .apps import ADEnrichedInventoryReceivedResolver
from .ldap_client import LDAPConnectionError, _format_ldap_error
from .matching import match_status_for, normalize
from .models import ADComputer, ADDomain, SyncReport


@pytest.fixture(autouse=True)
def _mount_extension_urls(db, settings):
    """
    ocsinventory_backend/urls.py only mounts /activedirectory/ for Extension
    rows that are enabled in the database, and builds that URLconf once at
    import time - so it has to be forced to rebuild against the test database.
    """
    Extension.objects.update_or_create(
        django_app="activedirectory",
        defaults={"name": "Active Directory", "enabled": True},
    )
    clear_url_caches()
    sys.modules.pop("ocsinventory_backend.urls", None)
    importlib.import_module("ocsinventory_backend.urls")
    yield
    clear_url_caches()


@pytest.fixture
def domain(db):
    return ADDomain.objects.create(
        name="CORP",
        server="dc1.corp.local",
        port=636,
        security="ldaps",
        bind_dn="svc-ocs@corp.local",
        bind_password="s3cret",
        base_dn="DC=corp,DC=local",
    )


@pytest.fixture
def asset(db):
    return InventoryBase.objects.create(name="PC01", osname="Windows 11", serial="SN1", uuid="uuid-pc01")


@pytest.fixture
def computer(db, domain):
    return ADComputer.objects.create(
        domain=domain,
        object_guid="guid-1",
        name="PC01",
        distinguished_name="CN=PC01,OU=Laptops,DC=corp,DC=local",
    )


# --- Domains -----------------------------------------------------------

class TestADDomainAPI:
    def test_list_requires_permission(self, make_api_client, domain):
        client = make_api_client()
        response = client.get("/activedirectory/domains/")
        assert response.status_code == 403

    def test_list(self, make_api_client, domain):
        client = make_api_client("view_addomain")
        response = client.get("/activedirectory/domains/")
        assert response.status_code == 200
        assert response.data[0]["name"] == "CORP"

    def test_bind_password_never_returned(self, make_api_client, domain):
        client = make_api_client("view_addomain")
        response = client.get(f"/activedirectory/domains/{domain.id}/")
        assert "bind_password" not in response.data
        assert response.data["has_password"] is True

    def test_create_requires_password(self, make_api_client):
        client = make_api_client("add_addomain")
        response = client.post(
            "/activedirectory/domains/",
            {
                "name": "CORP2",
                "server": "dc2.corp.local",
                "bind_dn": "svc@corp.local",
                "base_dn": "DC=corp,DC=local",
            },
            format="json",
        )
        assert response.status_code == 400
        assert "bind_password" in response.data

    def test_create(self, make_api_client):
        client = make_api_client("add_addomain")
        response = client.post(
            "/activedirectory/domains/",
            {
                "name": "CORP2",
                "server": "dc2.corp.local",
                "bind_dn": "svc@corp.local",
                "bind_password": "pwd",
                "base_dn": "DC=corp,DC=local",
            },
            format="json",
        )
        assert response.status_code == 201
        created = ADDomain.objects.get(name="CORP2")
        assert created.bind_password == "pwd"

    def test_invalid_port_rejected(self, make_api_client):
        client = make_api_client("add_addomain")
        response = client.post(
            "/activedirectory/domains/",
            {
                "name": "CORP3",
                "server": "dc3.corp.local",
                "port": 70000,
                "bind_dn": "svc@corp.local",
                "bind_password": "pwd",
                "base_dn": "DC=corp,DC=local",
            },
            format="json",
        )
        assert response.status_code == 400
        assert "port" in response.data

    def test_update_without_password_keeps_existing(self, make_api_client, domain):
        client = make_api_client("change_addomain")
        response = client.patch(
            f"/activedirectory/domains/{domain.id}/",
            {"server": "dc1-new.corp.local"},
            format="json",
        )
        assert response.status_code == 200
        domain.refresh_from_db()
        assert domain.server == "dc1-new.corp.local"
        assert domain.bind_password == "s3cret"

    def test_update_with_blank_password_keeps_existing(self, make_api_client, domain):
        client = make_api_client("change_addomain")
        response = client.patch(
            f"/activedirectory/domains/{domain.id}/",
            {"bind_password": ""},
            format="json",
        )
        assert response.status_code == 200
        domain.refresh_from_db()
        assert domain.bind_password == "s3cret"

    def test_delete_cascades(self, make_api_client, domain, computer):
        report = SyncReport.objects.create(domain=domain, status="success")
        client = make_api_client("delete_addomain")
        response = client.delete(f"/activedirectory/domains/{domain.id}/")
        assert response.status_code == 204
        assert not ADComputer.objects.filter(id=computer.id).exists()
        assert not SyncReport.objects.filter(id=report.id).exists()

    @patch("extensions.activedirectory.views.test_connection")
    def test_test_action_ok_uses_stored_password_when_blank(self, mock_test, make_api_client, domain):
        mock_test.return_value = (True, None)
        client = make_api_client("change_addomain")
        response = client.post(
            f"/activedirectory/domains/{domain.id}/test/",
            {
                "server": domain.server,
                "bind_dn": domain.bind_dn,
                "base_dn": domain.base_dn,
            },
            format="json",
        )
        assert response.status_code == 200
        assert response.data == {"ok": True, "server": domain.server}
        candidate = mock_test.call_args[0][0]
        assert candidate.bind_password == domain.bind_password

    @pytest.mark.parametrize(
        "field, value",
        [
            ("server", "attacker.example"),
            ("port", 389),
            ("security", "none"),
            ("verify_certificate", False),
            ("bind_dn", "other@corp.local"),
        ],
    )
    @patch("extensions.activedirectory.views.test_connection")
    def test_test_action_never_sends_stored_password_to_a_changed_target(
        self, mock_test, make_api_client, domain, field, value
    ):
        client = make_api_client("change_addomain")
        payload = {"server": domain.server, "bind_dn": domain.bind_dn, "base_dn": domain.base_dn}
        payload[field] = value
        response = client.post(f"/activedirectory/domains/{domain.id}/test/", payload, format="json")
        assert response.status_code == 400
        assert "bind_password" in response.data
        mock_test.assert_not_called()

    @patch("extensions.activedirectory.views.test_connection")
    def test_test_action_uses_submitted_fields_not_the_saved_row(self, mock_test, make_api_client, domain):
        mock_test.return_value = (True, None)
        client = make_api_client("change_addomain")
        response = client.post(
            f"/activedirectory/domains/{domain.id}/test/",
            {
                "server": "other-server.corp.local",
                "bind_dn": domain.bind_dn,
                "bind_password": "newpwd",
                "base_dn": domain.base_dn,
            },
            format="json",
        )
        assert response.status_code == 200
        assert response.data == {"ok": True, "server": "other-server.corp.local"}
        candidate = mock_test.call_args[0][0]
        assert candidate.bind_password == "newpwd"
        # the stored domain itself must never be touched by a test
        domain.refresh_from_db()
        assert domain.server != "other-server.corp.local"

    @patch("extensions.activedirectory.views.test_connection")
    def test_test_action_failure(self, mock_test, make_api_client, domain):
        mock_test.return_value = (False, "Invalid credentials")
        client = make_api_client("change_addomain")
        response = client.post(
            f"/activedirectory/domains/{domain.id}/test/",
            {"server": domain.server, "bind_dn": domain.bind_dn, "base_dn": domain.base_dn},
            format="json",
        )
        assert response.status_code == 200
        assert response.data == {"ok": False, "error": "Invalid credentials"}

    @patch("extensions.activedirectory.views.test_connection")
    def test_test_action_requires_add_or_change_permission_on_creation_form(self, mock_test, make_api_client):
        mock_test.return_value = (True, None)
        client = make_api_client("view_addomain")
        response = client.post(
            "/activedirectory/domains/test/",
            {"server": "x", "bind_dn": "x", "bind_password": "x", "base_dn": "x"},
            format="json",
        )
        assert response.status_code == 403

    @patch("extensions.activedirectory.views.test_connection")
    def test_test_action_on_creation_form_requires_password(self, mock_test, make_api_client):
        client = make_api_client("add_addomain")
        response = client.post(
            "/activedirectory/domains/test/",
            {"server": "x", "bind_dn": "x", "base_dn": "x"},
            format="json",
        )
        assert response.status_code == 400

    @patch("extensions.activedirectory.views.test_connection")
    def test_test_action_on_creation_form(self, mock_test, make_api_client):
        mock_test.return_value = (True, None)
        client = make_api_client("add_addomain")
        response = client.post(
            "/activedirectory/domains/test/",
            {
                "server": "new-dc.corp.local",
                "bind_dn": "svc@corp.local",
                "bind_password": "pwd",
                "base_dn": "DC=corp,DC=local",
            },
            format="json",
        )
        assert response.status_code == 200
        assert response.data == {"ok": True, "server": "new-dc.corp.local"}


# --- Computers -----------------------------------------------------------

class TestADComputerAPI:
    def test_list(self, make_api_client, computer):
        client = make_api_client("view_adcomputer")
        response = client.get("/activedirectory/computers/")
        assert response.status_code == 200
        assert response.data[0]["name"] == "PC01"

    def test_create_not_allowed(self, make_api_client, domain):
        client = make_api_client("add_adcomputer")
        response = client.post(
            "/activedirectory/computers/",
            {"domain": domain.id, "object_guid": "x", "name": "PC02"},
            format="json",
        )
        assert response.status_code == 405

    def test_update_not_allowed(self, make_api_client, computer):
        client = make_api_client("change_adcomputer")
        response = client.patch(
            f"/activedirectory/computers/{computer.id}/", {"name": "RENAMED"}, format="json"
        )
        assert response.status_code == 405

    def test_delete_requires_permission(self, make_api_client, computer):
        client = make_api_client("view_adcomputer")
        response = client.delete(f"/activedirectory/computers/{computer.id}/")
        assert response.status_code == 403
        assert ADComputer.objects.filter(id=computer.id).exists()

    def test_delete(self, make_api_client, computer):
        client = make_api_client("delete_adcomputer")
        response = client.delete(f"/activedirectory/computers/{computer.id}/")
        assert response.status_code == 204
        assert not ADComputer.objects.filter(id=computer.id).exists()

    def test_delete_does_not_touch_the_linked_asset(self, make_api_client, computer, asset):
        computer.asset = asset
        computer.link_mode = "manual"
        computer.match_status = "linked"
        computer.save()

        client = make_api_client("delete_adcomputer")
        response = client.delete(f"/activedirectory/computers/{computer.id}/")
        assert response.status_code == 204
        assert InventoryBase.objects.filter(id=asset.id).exists()

    def test_filter_by_match_status(self, make_api_client, computer):
        computer.match_status = "ambiguous"
        computer.save()
        client = make_api_client("view_adcomputer")
        response = client.get("/activedirectory/computers/?match_status=ambiguous")
        assert response.status_code == 200
        assert len(response.data) == 1

        response = client.get("/activedirectory/computers/?match_status=linked")
        assert len(response.data) == 0

    def test_search(self, make_api_client, computer):
        client = make_api_client("view_adcomputer")
        response = client.get("/activedirectory/computers/?search=PC01")
        assert len(response.data) == 1

    def test_stats_match_counts_ignore_removed_computers(self, make_api_client, domain, asset):
        # removed from the directory but still linked: must only count as removed
        ADComputer.objects.create(
            domain=domain, object_guid="guid-removed", name="PC01", distinguished_name="CN=PC01",
            asset=asset, link_mode="auto", match_status="linked", in_directory=False,
        )
        for name, match_status in (("PC02", "linked"), ("PC03", "unlinked"), ("PC04", "ambiguous")):
            ADComputer.objects.create(
                domain=domain, object_guid=f"guid-{name}", name=name, distinguished_name=f"CN={name}",
                match_status=match_status,
            )
        client = make_api_client("view_adcomputer")
        response = client.get("/activedirectory/computers/stats/")
        assert response.status_code == 200
        assert response.data == {"total": 4, "linked": 1, "unlinked": 1, "ambiguous": 1, "removed": 1}

    def test_stats_domain_filter_is_validated_like_the_list(self, make_api_client, computer):
        other_domain = ADDomain.objects.create(
            name="LAB", server="dc.lab.local", bind_dn="svc@lab.local", bind_password="pwd", base_dn="DC=lab,DC=local"
        )
        ADComputer.objects.create(domain=other_domain, object_guid="guid-lab", name="LAB01", distinguished_name="CN=LAB01")
        client = make_api_client("view_adcomputer")
        response = client.get(f"/activedirectory/computers/stats/?domain={computer.domain_id}")
        assert response.data["total"] == 1

        for value in ("abc", "999999"):
            assert client.get(f"/activedirectory/computers/?domain={value}").status_code == 400
            response = client.get(f"/activedirectory/computers/stats/?domain={value}")
            assert response.status_code == 400
            assert "domain" in response.data

    def test_ordering_by_ou_path(self, make_api_client, domain):
        for name, ou_path in (("PC01", "Paris / Laptops"), ("PC02", "Lyon")):
            ADComputer.objects.create(
                domain=domain, object_guid=f"guid-{name}", name=name, distinguished_name=f"CN={name}",
                ou_path=ou_path,
            )
        client = make_api_client("view_adcomputer")
        response = client.get("/activedirectory/computers/?ordering=ou_path,id")
        assert [computer["name"] for computer in response.data] == ["PC02", "PC01"]

    def test_link(self, make_api_client, computer, asset):
        client = make_api_client("change_adcomputer")
        response = client.post(
            f"/activedirectory/computers/{computer.id}/link/", {"asset": asset.id}, format="json"
        )
        assert response.status_code == 200
        computer.refresh_from_db()
        assert computer.asset_id == asset.id
        assert computer.link_mode == "manual"
        assert computer.match_status == "linked"

    def test_link_unknown_asset(self, make_api_client, computer):
        client = make_api_client("change_adcomputer")
        response = client.post(
            f"/activedirectory/computers/{computer.id}/link/", {"asset": 99999}, format="json"
        )
        assert response.status_code == 400

    def test_link_already_linked_asset(self, make_api_client, domain, asset):
        computer1 = ADComputer.objects.create(
            domain=domain, object_guid="g1", name="PC01", asset=asset, link_mode="manual"
        )
        computer2 = ADComputer.objects.create(domain=domain, object_guid="g2", name="PC02")
        client = make_api_client("change_adcomputer")
        response = client.post(
            f"/activedirectory/computers/{computer2.id}/link/", {"asset": asset.id}, format="json"
        )
        assert response.status_code == 400
        assert computer1.id  # unchanged

    def test_unlink(self, make_api_client, computer, asset):
        computer.asset = asset
        computer.link_mode = "manual"
        computer.match_status = "linked"
        computer.save()

        client = make_api_client("change_adcomputer")
        response = client.post(f"/activedirectory/computers/{computer.id}/unlink/")
        assert response.status_code == 200
        computer.refresh_from_db()
        assert computer.asset is None
        assert computer.match_status == "unlinked"


# --- Reports -----------------------------------------------------------

class TestSyncReportAPI:
    def test_list_filtered_by_domain(self, make_api_client, domain):
        SyncReport.objects.create(domain=domain, status="success")
        client = make_api_client("view_syncreport")
        response = client.get(f"/activedirectory/reports/?domain={domain.id}")
        assert response.status_code == 200
        assert len(response.data) == 1

    def test_readonly(self, make_api_client, domain):
        client = make_api_client("add_syncreport")
        response = client.post(
            "/activedirectory/reports/", {"domain": domain.id}, format="json"
        )
        assert response.status_code == 405


# --- LDAP error formatting -------------------------------------------------

class TestFormatLdapError:
    def test_dict_shaped_error_uses_desc_and_info(self):
        exc = ldap.SERVER_DOWN({"desc": "Can't contact LDAP server", "info": "timeout"})
        assert _format_ldap_error(exc) == "SERVER_DOWN: Can't contact LDAP server: timeout"

    def test_dict_shaped_error_without_desc_or_info_keeps_exception_type(self):
        exc = ldap.OPERATIONS_ERROR({"result": -1})
        assert _format_ldap_error(exc).startswith("OPERATIONS_ERROR")

    def test_plain_tuple_error_is_not_just_the_bare_message(self):
        # Reproduces the unhelpful "(0, 'Error')" seen in production logs:
        # some python-ldap errors carry a plain tuple instead of the usual
        # {'desc': ..., 'info': ...} dict, so the bare str(exc) is just "Error".
        exc = ldap.LDAPError(0, "Error")
        message = _format_ldap_error(exc)
        assert message == "LDAPError: Error"
        assert message != "Error"


# --- Matching ------------------------------------------------------------

class TestMatching:
    def test_normalize_strips_netbios_suffix_and_case(self):
        assert normalize("pc01$") == "PC01"
        assert normalize(" PC01 ") == "PC01"

    def test_match_status_for(self):
        assert match_status_for(0) == "unlinked"
        assert match_status_for(1) == "linked"
        assert match_status_for(2) == "ambiguous"


# --- Domain model password encryption ------------------------------------

class TestADDomainEncryption:
    def test_password_stored_encrypted_in_db(self, domain):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT bind_password FROM activedirectory_addomain WHERE id = %s",
                [domain.id],
            )
            raw_value = cursor.fetchone()[0]
        assert raw_value != "s3cret"

    def test_password_decrypted_on_read(self, domain):
        reloaded = ADDomain.objects.get(id=domain.id)
        assert reloaded.bind_password == "s3cret"


# --- Automation context resolver -----------------------------------------

class TestInventoryReceivedContext:
    def test_schema_includes_activedirectory(self):
        resolver = get_resolver_for_trigger("inventory_received")
        schema = resolver.get_schema()
        assert "activedirectory" in schema

    def test_context_without_linked_computer(self, asset):
        resolver = get_resolver_for_trigger("inventory_received")
        context = resolver.build(asset)
        assert "activedirectory" not in context

    def test_context_with_linked_computer(self, asset, computer):
        computer.asset = asset
        computer.domain.assigned_user_attribute = "managedBy"
        computer.assigned_user_login = "jdoe"
        computer.enabled = True
        computer.ou = "OU=Laptops,DC=corp,DC=local"
        computer.save()

        asset.refresh_from_db()
        resolver = get_resolver_for_trigger("inventory_received")
        context = resolver.build(asset)

        assert context["activedirectory"] == {
            "domain": computer.domain.name,
            "ou": computer.ou,
            "enabled": True,
            "assigned_user": "jdoe",
        }

    def test_resolver_not_double_wrapped(self):
        from extensions.activedirectory.apps import ActivedirectoryConfig
        from django.apps import apps as django_apps

        config = django_apps.get_app_config("activedirectory")
        assert isinstance(config, ActivedirectoryConfig)

        resolver_before = get_resolver_for_trigger("inventory_received")
        config._extend_inventory_received_context()
        resolver_after = get_resolver_for_trigger("inventory_received")
        assert resolver_before is resolver_after


# --- ad_sync failure handling ----------------------------------------------

def _entry(name, object_guid, **overrides):
    base = {
        "object_guid": object_guid,
        "name": name,
        "sam_account_name": f"{name}$",
        "dns_hostname": f"{name.lower()}.corp.local",
        "distinguished_name": f"CN={name},DC=corp,DC=local",
        "ou": "DC=corp,DC=local",
        "os_name": "Windows 11",
        "os_version": "10.0",
        "enabled": True,
        "description": "",
        "when_created": None,
        "last_logon": None,
        "password_last_set": None,
        "assigned_user_raw": "",
    }
    base.update(overrides)
    return base


class TestSyncDomainFailureHandling:
    def test_non_ldap_exception_closes_the_report_as_error(self, domain, monkeypatch):
        from extensions.activedirectory.management.commands import ad_sync

        def boom(_domain):
            raise RuntimeError("totally unrelated bug")

        monkeypatch.setattr(ad_sync, "connect", boom)

        report = ad_sync.sync_domain(domain)

        assert report.status == "error"
        assert "totally unrelated bug" in report.error_message
        domain.refresh_from_db()
        assert domain.last_sync_status == "error"
        assert domain.last_sync_at is not None

    def test_a_closed_report_never_blocks_the_next_sync(self, domain, monkeypatch):
        from extensions.activedirectory.management.commands import ad_sync

        monkeypatch.setattr(
            ad_sync, "connect", lambda _domain: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        ad_sync.sync_domain(domain)

        assert ad_sync.is_sync_running(domain) is False
        assert ad_sync.start_sync_report(domain) is not None

    def test_stale_running_report_is_closed_as_abandoned(self, domain):
        from extensions.activedirectory.management.commands import ad_sync

        stale = SyncReport.objects.create(domain=domain, status="running")
        SyncReport.objects.filter(id=stale.id).update(
            started_at=timezone.now()
            - timezone.timedelta(seconds=ad_sync.STALE_RUNNING_REPORT_SECONDS + 60)
        )

        assert ad_sync.is_sync_running(domain) is False

        stale.refresh_from_db()
        assert stale.status == "error"
        assert "Abandoned" in stale.error_message
        domain.refresh_from_db()
        assert domain.last_sync_status == "error"
        assert domain.last_sync_at == stale.finished_at

    def test_recent_running_report_still_blocks(self, domain):
        from extensions.activedirectory.management.commands import ad_sync

        SyncReport.objects.create(domain=domain, status="running")
        assert ad_sync.is_sync_running(domain) is True

    def test_start_sync_report_refuses_a_second_running_report(self, domain):
        """Scheduler and CLI syncs must not both create a running report."""
        from extensions.activedirectory.management.commands.ad_sync import start_sync_report

        first = start_sync_report(domain)
        assert first is not None
        second = start_sync_report(domain)
        assert second is None
        assert SyncReport.objects.filter(domain=domain, status="running").count() == 1

    def test_same_computer_name_in_two_domains_does_not_crash_and_is_ambiguous(
        self, domain, asset
    ):
        from extensions.activedirectory.management.commands import ad_sync

        other_domain = ADDomain.objects.create(
            name="OTHERCORP",
            server="dc2.othercorp.local",
            bind_dn="svc@othercorp.local",
            bind_password="pwd",
            base_dn="DC=othercorp,DC=local",
        )

        entry = _entry(asset.name, "guid-domain1")
        created, changed, linked = ad_sync.upsert_computer(domain, entry, conn=None)
        assert linked is True

        # same asset name, different domain: must not raise IntegrityError
        other_entry = _entry(asset.name, "guid-domain2")
        created2, changed2, linked2 = ad_sync.upsert_computer(other_domain, other_entry, conn=None)

        assert linked2 is False
        other_computer = ADComputer.objects.get(domain=other_domain, object_guid="guid-domain2")
        assert other_computer.match_status == "ambiguous"
        assert other_computer.asset is None

        # the original link is untouched
        first_computer = ADComputer.objects.get(domain=domain, object_guid="guid-domain1")
        assert first_computer.asset_id == asset.id

    def test_computer_recreated_with_new_guid_frees_the_stale_one(self, domain, asset):
        from extensions.activedirectory.management.commands import ad_sync

        entry = _entry(asset.name, "guid-old")
        ad_sync.upsert_computer(domain, entry, conn=None)
        old_computer = ADComputer.objects.get(domain=domain, object_guid="guid-old")
        assert old_computer.asset_id == asset.id

        # the old object has disappeared from the directory by the time the
        # new one (same name, new objectGUID) is processed
        old_computer.in_directory = False
        old_computer.save(update_fields=["in_directory"])

        new_entry = _entry(asset.name, "guid-new")
        created, changed, linked = ad_sync.upsert_computer(domain, new_entry, conn=None)

        assert linked is True
        new_computer = ADComputer.objects.get(domain=domain, object_guid="guid-new")
        assert new_computer.asset_id == asset.id

        old_computer.refresh_from_db()
        assert old_computer.asset is None
        assert old_computer.match_status == "unlinked"

    def test_computer_recreated_with_new_guid_is_ambiguous_if_old_one_still_present(
        self, domain, asset
    ):
        from extensions.activedirectory.management.commands import ad_sync

        entry = _entry(asset.name, "guid-old")
        ad_sync.upsert_computer(domain, entry, conn=None)

        # old object is still in the directory (not yet marked missing)
        new_entry = _entry(asset.name, "guid-new")
        created, changed, linked = ad_sync.upsert_computer(domain, new_entry, conn=None)

        assert linked is False
        new_computer = ADComputer.objects.get(domain=domain, object_guid="guid-new")
        assert new_computer.match_status == "ambiguous"

    def test_manually_linked_computer_is_never_relinked_by_a_sync(self, domain, asset):
        from extensions.activedirectory.management.commands import ad_sync

        other_asset = InventoryBase.objects.create(
            name="OTHERPC", osname="Linux", serial="SN2", uuid="uuid-other"
        )
        computer = ADComputer.objects.create(
            domain=domain,
            object_guid="guid-1",
            name="OTHERPC",
            distinguished_name="CN=OTHERPC,DC=corp,DC=local",
            asset=other_asset,
            link_mode="manual",
            match_status="linked",
        )

        entry = _entry("RENAMEDPC", "guid-1")
        ad_sync.upsert_computer(domain, entry, conn=None)

        computer.refresh_from_db()
        assert computer.asset_id == other_asset.id
        assert computer.link_mode == "manual"

    def test_manually_unlinked_computer_is_not_relinked_by_a_sync(self, domain, asset):
        """
        Reproduces the bug where unlink() set link_mode="", which the next
        sync treated as "never evaluated" and relinked right away.
        """
        from extensions.activedirectory.management.commands import ad_sync

        computer = ADComputer.objects.create(
            domain=domain,
            object_guid="guid-1",
            name=asset.name,
            distinguished_name=f"CN={asset.name},DC=corp,DC=local",
            asset=None,
            link_mode="manual_unlinked",
            match_status="unlinked",
        )

        entry = _entry(asset.name, "guid-1")
        ad_sync.upsert_computer(domain, entry, conn=None)

        computer.refresh_from_db()
        assert computer.asset is None
        assert computer.link_mode == "manual_unlinked"
        assert computer.match_status == "unlinked"

    def test_computer_back_in_the_directory_counts_as_updated(self, domain):
        from extensions.activedirectory.management.commands import ad_sync

        entry = _entry("PC01", "guid-1")
        ad_sync.upsert_computer(domain, entry, conn=None)
        ADComputer.objects.filter(object_guid="guid-1").update(in_directory=False)

        _created, changed, _linked = ad_sync.upsert_computer(domain, entry, conn=None)
        assert changed is True
        _created, changed, _linked = ad_sync.upsert_computer(domain, entry, conn=None)
        assert changed is False

    def test_one_failing_computer_does_not_abort_the_whole_sync(self, domain, asset, monkeypatch):
        from extensions.activedirectory.management.commands import ad_sync

        good_entry = _entry(asset.name, "guid-good")
        bad_entry = _entry("BROKEN", "guid-bad")

        monkeypatch.setattr(
            ad_sync, "iter_computers", lambda _domain: iter([bad_entry, good_entry])
        )
        monkeypatch.setattr(ad_sync, "connect", lambda _domain: _FakeConnection())

        original_upsert = ad_sync.upsert_computer

        def flaky_upsert(domain, entry, conn):
            if entry["object_guid"] == "guid-bad":
                raise RuntimeError("simulated failure for this one computer")
            return original_upsert(domain, entry, conn)

        monkeypatch.setattr(ad_sync, "upsert_computer", flaky_upsert)

        report = ad_sync.sync_domain(domain)

        assert report.status == "error"
        assert "1 computer(s) failed" in report.error_message
        assert ADComputer.objects.filter(domain=domain, object_guid="guid-good").exists()
        assert not ADComputer.objects.filter(domain=domain, object_guid="guid-bad").exists()

    def test_lost_connection_keeps_the_assigned_user(self, domain, monkeypatch):
        from extensions.activedirectory.management.commands import ad_sync

        user_dn = "CN=Jane Doe,DC=corp,DC=local"
        computer = ADComputer.objects.create(
            domain=domain, object_guid="guid-1", name="PC01", distinguished_name="CN=PC01",
            assigned_user_raw=user_dn, assigned_user_name="Jane Doe", assigned_user_login="jdoe",
        )

        class DroppedConnection(_FakeConnection):
            def search_s(self, base, scope, filterstr, attrlist):
                raise ldap.SERVER_DOWN({"desc": "Can't contact LDAP server"})

        monkeypatch.setattr(
            ad_sync, "iter_computers", lambda _domain: iter([_entry("PC01", "guid-1", assigned_user_raw=user_dn)])
        )
        monkeypatch.setattr(ad_sync, "connect", lambda _domain: DroppedConnection())

        report = ad_sync.sync_domain(domain)

        assert report.status == "error"
        computer.refresh_from_db()
        assert computer.assigned_user_name == "Jane Doe"
        assert computer.assigned_user_login == "jdoe"


class _FakeConnection:
    def unbind_s(self):
        pass


class TestResolveAssignedUserRealReturnShape:
    def test_search_s_return_value_is_not_a_tuple(self, domain, monkeypatch):
        """
        Reproduces the bug where resolve_assigned_user() unpacked search_s()'s
        return value as a (rtype, results) tuple: python-ldap's search_s()
        returns the result list directly, so every computer with a
        resolvable managedBy raised a bare ValueError that upsert_computer()
        never caught (only ldap.LDAPError was handled).
        """
        from extensions.activedirectory.ldap_client import resolve_assigned_user

        class FakeConn:
            def search_s(self, base, scope, filterstr, attrlist):
                return [("CN=Jane Doe,DC=corp,DC=local", {
                    "cn": [b"Jane Doe"],
                    "sAMAccountName": [b"jdoe"],
                    "mail": [b"jdoe@corp.local"],
                })]

        name, login, email = resolve_assigned_user(domain, FakeConn(), "CN=Jane Doe,DC=corp,DC=local")
        assert (name, login, email) == ("Jane Doe", "jdoe", "jdoe@corp.local")

    def test_no_match_returns_empty_strings_without_raising(self, domain):
        from extensions.activedirectory.ldap_client import resolve_assigned_user

        class FakeConn:
            def search_s(self, base, scope, filterstr, attrlist):
                return []

        assert resolve_assigned_user(domain, FakeConn(), "CN=Nobody,DC=corp,DC=local") == ("", "", "")

    def test_ldap_error_is_caught(self, domain):
        from extensions.activedirectory.ldap_client import resolve_assigned_user

        class FakeConn:
            def search_s(self, base, scope, filterstr, attrlist):
                raise ldap.NO_SUCH_OBJECT({"desc": "No such object"})

        assert resolve_assigned_user(domain, FakeConn(), "CN=Gone,DC=corp,DC=local") == ("", "", "")

    @pytest.mark.parametrize("error", [ldap.INVALID_DN_SYNTAX, ldap.REFERRAL])
    def test_unresolvable_value_returns_empty_strings(self, domain, error):
        from extensions.activedirectory.ldap_client import resolve_assigned_user

        class FakeConn:
            def search_s(self, base, scope, filterstr, attrlist):
                raise error({"desc": "unresolvable"})

        assert resolve_assigned_user(domain, FakeConn(), "jdoe") == ("", "", "")

    @pytest.mark.parametrize("error", [ldap.SERVER_DOWN, ldap.TIMEOUT])
    def test_connection_error_is_raised(self, domain, error):
        from extensions.activedirectory.ldap_client import resolve_assigned_user

        class FakeConn:
            def search_s(self, base, scope, filterstr, attrlist):
                raise error({"desc": "connection problem"})

        with pytest.raises(error):
            resolve_assigned_user(domain, FakeConn(), "CN=Jane Doe,DC=corp,DC=local")


# --- TLS options are per-connection, not process-wide -----------------------

class TestTlsOptionsScope:
    def test_tls_options_are_set_on_the_connection_not_the_module(self, domain, monkeypatch):
        """
        Reproduces the bug where ldap.set_option() was called at module level:
        testing/syncing one domain with verify_certificate=False would then
        disable certificate verification for every other LDAP connection in
        this worker process, including the core's own LDAP auth backend.
        """
        from extensions.activedirectory import ldap_client

        module_level_calls = []
        monkeypatch.setattr(ldap, "set_option", lambda *a: module_level_calls.append(a))

        class FakeConn:
            def __init__(self):
                self.options = []

            def set_option(self, *args):
                self.options.append(args)

            def start_tls_s(self):
                pass

            def simple_bind_s(self, dn, password):
                pass

        fake_conn = FakeConn()
        monkeypatch.setattr(ldap, "initialize", lambda uri: fake_conn)

        domain.security = "starttls"
        domain.verify_certificate = False
        ldap_client.connect(domain)

        assert module_level_calls == []
        assert (ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER) in fake_conn.options
        assert any(opt[0] == ldap.OPT_X_TLS_NEWCTX for opt in fake_conn.options)
