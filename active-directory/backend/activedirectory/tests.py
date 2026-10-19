import importlib
import sys
from unittest.mock import patch

import pytest
from asset.inventory_base.models import InventoryBase
from automation.rule.context import get_resolver_for_trigger
from django.urls import clear_url_caches
from extension.models import Extension

from .apps import ADEnrichedInventoryReceivedResolver
from .ldap_client import LDAPConnectionError
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
    def test_test_action_ok(self, mock_test, make_api_client, domain):
        mock_test.return_value = (True, None)
        client = make_api_client("change_addomain")
        response = client.post(f"/activedirectory/domains/{domain.id}/test/")
        assert response.status_code == 200
        assert response.data == {"ok": True, "server": domain.server}

    @patch("extensions.activedirectory.views.test_connection")
    def test_test_action_failure(self, mock_test, make_api_client, domain):
        mock_test.return_value = (False, "Invalid credentials")
        client = make_api_client("change_addomain")
        response = client.post(f"/activedirectory/domains/{domain.id}/test/")
        assert response.status_code == 200
        assert response.data == {"ok": False, "error": "Invalid credentials"}

    @patch("extensions.activedirectory.views.call_command")
    def test_sync_action_returns_report(self, mock_call_command, make_api_client, domain):
        def fake_sync(name, domain=None):
            SyncReport.objects.create(domain_id=domain, status="success")

        mock_call_command.side_effect = fake_sync
        client = make_api_client("change_addomain")
        response = client.post(f"/activedirectory/domains/{domain.id}/sync/")
        assert response.status_code == 202
        assert response.data["report"] is not None

    def test_sync_action_conflict_when_running(self, make_api_client, domain):
        SyncReport.objects.create(domain=domain, status="running")
        client = make_api_client("change_addomain")
        response = client.post(f"/activedirectory/domains/{domain.id}/sync/")
        assert response.status_code == 409


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
