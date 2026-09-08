import datetime
import json
import logging
import threading
import time
import uuid as uuid_module
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import urllib3
from asset.inventory_base.models import InventoryBase
from asset.inventory_field.models import InventoryField
from asset.inventory_section.models import InventorySection
from django.core.management.base import BaseCommand
from django.db import connections, transaction
from extensions.proxmoxapi.models import ProxmoxAsset, ProxmoxServer
from inventory.field.models import Field
from inventory.section.models import Section
from inventory.template.models import Template
from ocsinventory_backend.ocs_framework.logmanager import DynamicLogLevelManager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_EXTENSION_DIR = Path(__file__).resolve().parents[2]
_MANIFEST = json.loads((_EXTENSION_DIR / "extension.json").read_text())
_CONFIG = json.loads((_EXTENSION_DIR / "config.json").read_text())
 
class Command(BaseCommand):
    help = "Sync Proxmox VMs and LXC containers as assets in the database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--loglevel",
            type=str,
            choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
            help="Override logging level",
        )
        parser.add_argument(
            "--server",
            type=str,
            help="Restrict sync to a specific Proxmox server name",
        )

    def handle(self, *args, **options):
        log_manager = DynamicLogLevelManager()
        logger = logging.getLogger("mgmt.management.commands")

        if options["loglevel"]:
            log_manager.set_level_for_logger(
                "mgmt.management.commands", options["loglevel"]
            )

        servers = ProxmoxServer.objects.filter(is_active=True)
        if options["server"]:
            servers = servers.filter(name=options["server"])
            if not servers.exists():
                logger.error(f"No active server found with name '{options['server']}'")
                return

        count = servers.count()
        if count == 0:
            logger.error("No active Proxmox servers configured in the database.")
            return

        logger.info(f"Processing {count} active Proxmox server(s)")

        total_created = total_updated = total_errors = 0

        with ThreadPoolExecutor(
            max_workers=min(_CONFIG["max_server_workers"], count), thread_name_prefix="proxmox-server"
        ) as executor:
            futures = {
                executor.submit(self.sync_server_thread, server, logger): server
                for server in servers
            }
            for future in as_completed(futures):
                server = futures[future]
                try:
                    created, updated, errors = future.result()
                except Exception as exc:
                    logger.error(f"Unhandled error syncing {server.name}: {exc}")
                    created, updated, errors = 0, 0, 1
                total_created += created
                total_updated += updated
                total_errors += errors

        logger.info(
            f"Sync complete - created: {total_created}, "
            f"updated: {total_updated}, errors: {total_errors}"
        )

    def build_session(self, server, request_delay):
        session = requests.Session()
        session.headers.update({
            "Authorization": (
                f"PVEAPIToken={server.username}!{server.token_id}={server.token_secret}"
            )
        })
        session.verify = False
        if request_delay > 0:
            orig_get = session.get
            lock = threading.Lock()
            state = {"next_time": 0.0}

            def throttled_get(url, **kw):
                with lock:
                    now = time.monotonic()
                    wait = state["next_time"] - now
                    if wait > 0:
                        time.sleep(wait)
                        now = time.monotonic()
                    state["next_time"] = now + request_delay
                return orig_get(url, **kw)

            session.get = throttled_get
        return session

    def sync_server_thread(self, server, logger):
        logger.info(f"Connecting to {server.name} ({server.ip_address})")
        try:
            return self.sync_server(server, server.request_delay / 1000, logger)
        finally:
            connections.close_all()

    def sync_server(self, server, request_delay, logger):
        base_url = f"https://{server.ip_address}:{server.port}/api2/json"
        session = self.build_session(server, request_delay)

        node_names = server.node_names or []
        if not node_names:
            logger.error(f"No nodes configured for server {server.name}, skipping.")
            return 0, 0, 0

        created = updated = errors = 0

        with ThreadPoolExecutor(
            max_workers=min(_CONFIG["max_node_workers"], len(node_names)),
            thread_name_prefix=f"proxmox-{server.name}-node",
        ) as executor:
            futures = {
                executor.submit(
                    self.sync_node_thread, server, node_name, session, base_url, logger
                ): node_name
                for node_name in node_names
            }
            for future in as_completed(futures):
                node_name = futures[future]
                try:
                    c, u, e = future.result()
                except Exception as exc:
                    logger.error(f"Unhandled error syncing node {node_name} on {server.name}: {exc}")
                    c, u, e = 0, 0, 1
                created += c
                updated += u
                errors += e

        return created, updated, errors

    def sync_node_thread(self, server, node_name, session, base_url, logger):
        try:
            return self.sync_node(server, node_name, session, base_url, logger)
        finally:
            connections.close_all()

    def sync_node(self, server, node_name, session, base_url, logger):
        created = updated = errors = 0
        backup_storages = self.fetch_backup_storages(session, base_url, server, node_name, logger)

        for resource_type in ("qemu", "lxc"):
            url = f"{base_url}/nodes/{node_name}/{resource_type}"
            logger.debug(f"Fetching {resource_type} from {url}")
            try:
                response = session.get(url, timeout=10)
                response.raise_for_status()
            except requests.RequestException as exc:
                logger.error(f"Failed to fetch {resource_type} from {server.name}/{node_name}: {exc}")
                errors += 1
                continue

            resources = response.json().get("data") or []
            logger.info(
                f"  {server.name}/{node_name}: "
                f"{len(resources)} {resource_type} instance(s) found"
            )

            for resource in resources:
                try:
                    c, u = self.upsert_asset(
                        resource, resource_type, server, node_name,
                        session, base_url, backup_storages, logger,
                    )
                    created += c
                    updated += u
                except Exception as exc:
                    vmid = resource.get("vmid", "?")
                    logger.error(
                        f"  Error processing {resource_type} vmid={vmid} "
                        f"on {server.name}/{node_name}: {exc}"
                    )
                    errors += 1

        return created, updated, errors

    def parse_net_string(self, net_str):
        """Parse 'key=val,key=val,...' Proxmox net config into a dict."""
        return dict(
            item.split("=", 1) for item in net_str.split(",") if "=" in item
        )

    def fetch_config(self, session, base_url, node_name, resource_type, vmid, logger):
        try:
            url = f"{base_url}/nodes/{node_name}/{resource_type}/{vmid}/config"
            resp = session.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json().get("data") or {}
        except Exception as exc:
            logger.debug(f"  Could not fetch config for vmid={vmid}: {exc}")
            return {}

    def fetch_agent_ifaces(self, session, base_url, node_name, vmid, logger):
        agent_ifaces = {}
        try:
            url = (
                f"{base_url}/nodes/{node_name}/qemu/{vmid}"
                "/agent/network-get-interfaces"
            )
            resp = session.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("data") or {}
                ifaces = data if isinstance(data, list) else (data.get("result") or [])
                for iface in ifaces:
                    if iface.get("name") == "lo":
                        continue
                    mac = (iface.get("hardware-address") or "").lower()
                    ipv4 = ipv6 = ""
                    for addr in iface.get("ip-addresses") or []:
                        if addr.get("ip-address-type") == "ipv4" and not ipv4:
                            ipv4 = addr.get("ip-address", "")
                        elif addr.get("ip-address-type") == "ipv6" and not ipv6:
                            ipv6 = addr.get("ip-address", "")
                    agent_ifaces[mac] = {
                        "name": iface.get("name", ""),
                        "ipv4": ipv4,
                        "ipv6": ipv6,
                    }
        except Exception as exc:
            logger.debug(f"  Guest agent unavailable for vmid={vmid}: {exc}")
        return agent_ifaces

    def fetch_backup_storages(self, session, base_url, server, node_name, logger):
        try:
            url = f"{base_url}/nodes/{node_name}/storage?enabled=1&content=backup"
            resp = session.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json().get("data") or []
        except Exception as exc:
            logger.debug(f"  Could not list backup storages on {server.name}/{node_name}: {exc}")
            return []

    def fetch_snapshots(self, session, base_url, node_name, resource_type, vmid, logger):
        snapshots = []
        try:
            url = f"{base_url}/nodes/{node_name}/{resource_type}/{vmid}/snapshot"
            resp = session.get(url, timeout=10)
            resp.raise_for_status()
            for snap in resp.json().get("data") or []:
                if snap.get("name") == "current":
                    continue
                snaptime = snap.get("snaptime", "")
                snapshots.append({
                    "name":        snap.get("name", ""),
                    "description": snap.get("description", ""),
                    "snaptime":    self.ts_to_str(snaptime) if snaptime else "",
                    "vmstate":     "yes" if snap.get("vmstate") else "no",
                    "parent":      snap.get("parent", ""),
                })
        except Exception as exc:
            logger.debug(f"  Could not fetch snapshots for vmid={vmid}: {exc}")
        return snapshots

    def fetch_backups(self, session, base_url, node_name, vmid, backup_storages, logger):
        backups = []
        for storage_info in backup_storages:
            storage_name = storage_info.get("storage", "")
            if not storage_name:
                continue
            try:
                url = (
                    f"{base_url}/nodes/{node_name}/storage/{storage_name}"
                    f"/content?content=backup&vmid={vmid}"
                )
                resp = session.get(url, timeout=10)
                resp.raise_for_status()
                for item in resp.json().get("data") or []:
                    ctime = item.get("ctime", "")
                    backups.append({
                        "volid":   item.get("volid", ""),
                        "storage": storage_name,
                        "size":    self.format_bytes(item.get("size")),
                        "format":  item.get("format", ""),
                        "ctime":   self.ts_to_str(ctime) if ctime else "",
                        "notes":   item.get("notes", ""),
                    })
            except Exception as exc:
                logger.debug(
                    f"  Could not fetch backups from storage {storage_name} "
                    f"for vmid={vmid}: {exc}"
                )
        return backups

    def extract_lxc_details(self, config):
        ip = mac = domain = osname = ""
        for key in sorted(config):
            if not key.startswith("net"):
                continue
            parts = self.parse_net_string(config[key])
            if not mac:
                mac = parts.get("hwaddr", "")
            raw_ip = parts.get("ip", "")
            if not ip and raw_ip and raw_ip != "dhcp":
                ip = raw_ip.split("/")[0]
            if ip and mac:
                break
        domain = config.get("searchdomain", "")
        osname = config.get("ostype", "")
        return ip, mac, domain, osname

    def extract_qemu_details(self, config, agent_ifaces):
        ip = mac = domain = osname = ""

        for mac_key, iface_data in agent_ifaces.items():
            if not mac:
                mac = mac_key
            if not ip:
                ip = iface_data.get("ipv4", "")
            if ip and mac:
                break

        if not mac:
            for key in sorted(config):
                if not key.startswith("net"):
                    continue
                parts = self.parse_net_string(config[key])
                for net_type in set(_CONFIG["qemu_net_types"]):
                    if net_type in parts:
                        mac = parts[net_type].split("/")[0]
                        break
                if mac:
                    break

        domain = config.get("searchdomain", "")
        osname = config.get("ostype", "")
        return ip, mac, domain, osname

    def extract_vm_details(self, resource_type, config, agent_ifaces):
        if resource_type == "lxc":
            return self.extract_lxc_details(config)
        return self.extract_qemu_details(config, agent_ifaces)

    def build_networks(self, resource_type, config, agent_ifaces):
        networks = []

        if resource_type == "lxc":
            for key in sorted(config):
                if not key.startswith("net"):
                    continue
                parts = self.parse_net_string(config[key])
                raw_ip = parts.get("ip", "")
                ipv4 = raw_ip.split("/")[0] if raw_ip and raw_ip != "dhcp" else raw_ip
                raw_ip6 = parts.get("ip6", "")
                ipv6 = raw_ip6.split("/")[0] if raw_ip6 and raw_ip6 not in ("dhcp", "auto") else raw_ip6
                networks.append({
                    "identifier": key,
                    "name":       parts.get("name", ""),
                    "bridge":     parts.get("bridge", ""),
                    "firewall":   parts.get("firewall", ""),
                    "tag":        parts.get("tag", ""),
                    "hwaddr":     parts.get("hwaddr", ""),
                    "ipv4":       ipv4,
                    "ipv6":       ipv6,
                    "gw":         parts.get("gw", ""),
                    "mtu":        parts.get("mtu", ""),
                    "link_down":  parts.get("link_down", ""),
                })

        elif resource_type == "qemu":
            for key in sorted(config):
                if not key.startswith("net"):
                    continue
                parts = self.parse_net_string(config[key])
                mac = ""
                for net_type in set(_CONFIG["qemu_net_types"]):
                    if net_type in parts:
                        mac = parts[net_type].split("/")[0]
                        break
                agent = agent_ifaces.get(mac.lower(), {})
                networks.append({
                    "identifier": key,
                    "name":       agent.get("name", ""),
                    "bridge":     parts.get("bridge", ""),
                    "firewall":   parts.get("firewall", ""),
                    "tag":        parts.get("tag", ""),
                    "hwaddr":     mac,
                    "ipv4":       agent.get("ipv4", ""),
                    "ipv6":       agent.get("ipv6", ""),
                    "gw":         "",
                    "mtu":        parts.get("mtu", ""),
                    "link_down":  parts.get("link_down", ""),
                })

        return networks

    def build_qemu_agent_info(self, session, base_url, node_name, vmid, config, logger):
        result = {"enabled": "no", "type": ""}

        agent_raw = str(config.get("agent", "0"))
        agent_items = agent_raw.split(",")
        agent_parts = dict(
            item.split("=", 1) for item in agent_items if "=" in item
        )
        if "1" in agent_items or agent_parts.get("enabled") == "1":
            result["enabled"] = "yes"
        result["type"] = agent_parts.get("type", "virtio" if result["enabled"] == "yes" else "")

        try:
            url = f"{base_url}/nodes/{node_name}/qemu/{vmid}/agent/info"
            resp = session.get(url, timeout=5)
            if resp.status_code == 200:
                result["enabled"] = "yes"
        except Exception as exc:
            logger.debug(f"  Could not fetch QEMU agent info for vmid={vmid}: {exc}")

        return result

    def build_options(self, config):
        return {
            "onboot":     "yes" if config.get("onboot") else "no",
            "protection": "yes" if config.get("protection") else "no",
            "startup":    config.get("startup", ""),
            "tags":       config.get("tags", ""),
            "notes":      config.get("description", ""),
        }

    def build_cloud_init(self, config):
        has_cloudinit = config.get("citype") or config.get("ciuser") or any(
            isinstance(v, str) and "cloudinit" in v for v in config.values()
        )
        if not has_cloudinit:
            return None

        ipconfig_parts = [
            f"net{key[len('ipconfig'):]}: {config[key]}"
            for key in sorted(config)
            if key.startswith("ipconfig")
        ]
        return {
            "citype":       config.get("citype", ""),
            "ciuser":       config.get("ciuser", ""),
            "nameserver":   config.get("nameserver", ""),
            "searchdomain": config.get("searchdomain", ""),
            "ipconfig":     " | ".join(ipconfig_parts),
        }

    @staticmethod
    def generate_serial(server_name, asset_uuid, vmid):
        uuid_suffix = asset_uuid.split("-")[-1]
        return f"{server_name}-{uuid_suffix}-{vmid}"

    @staticmethod
    def format_bytes(value):
        if not value:
            return ""
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024:
                return f"{value:.0f} {unit}"
            value /= 1024
        return f"{value:.0f} PB"

    @staticmethod
    def ts_to_str(ts):
        try:
            return datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError, TypeError):
            return str(ts)

    def upsert_section(self, asset, template, section_name, rows, logger):
        try:
            section = Section.objects.get(name=section_name, template=template)
            field_map = {f.retrieval_value: f for f in Field.objects.filter(section=section)}
            InventorySection.objects.filter(base=asset, template_section=section).delete()
            for row in rows:
                inv_section = InventorySection.objects.create(base=asset, template_section=section)
                InventoryField.objects.bulk_create([
                    InventoryField(
                        inventory_section=inv_section,
                        template_field=field_map[k],
                        value=str(v),
                    )
                    for k, v in row.items() if k in field_map
                ])
        except Section.DoesNotExist:
            logger.debug(f"  No {section_name} section in template for asset {asset.uuid}")
        except Exception as exc:
            logger.debug(f"  Error populating {section_name} for asset {asset.uuid}: {exc}")

    def upsert_inventory_sections(
        self, asset, template, resource, resource_type,
        config, agent_ifaces, backup_storages,
        session, base_url, node_name, logger,
    ):
        if template is None:
            return

        vmid = resource["vmid"]

        stale_sections = Section.objects.filter(
            name__in=set(_CONFIG["section_names"])
        ).exclude(template=template)
        InventorySection.objects.filter(
            base=asset, template_section__in=stale_sections
        ).delete()

        self.upsert_section(asset, template, "RESOURCES", [{
            "mem":  self.format_bytes(resource.get("maxmem")),
            "swap": self.format_bytes(resource.get("maxswap")),
            "cpus": str(resource.get("cpus", "")),
            "disk": self.format_bytes(resource.get("maxdisk")),
        }], logger)

        self.upsert_section(
            asset, template, "NETWORKS",
            self.build_networks(resource_type, config, agent_ifaces),
            logger,
        )

        if resource_type == "qemu":
            self.upsert_section(
                asset, template, "QEMU_AGENT",
                [self.build_qemu_agent_info(session, base_url, node_name, vmid, config, logger)],
                logger,
            )

        self.upsert_section(asset, template, "OPTIONS", [self.build_options(config)], logger)

        self.upsert_section(
            asset, template, "SNAPSHOTS",
            self.fetch_snapshots(session, base_url, node_name, resource_type, vmid, logger),
            logger,
        )

        self.upsert_section(
            asset, template, "BACKUPS",
            self.fetch_backups(session, base_url, node_name, vmid, backup_storages, logger),
            logger,
        )

        if resource_type == "qemu":
            ci_data = self.build_cloud_init(config)
            if ci_data:
                self.upsert_section(asset, template, "CLOUD_INIT", [ci_data], logger)

    def build_asset_defaults(self, name, description, asset_uuid, server, vmid, ip, mac, domain, osname, template):
        defaults = {
            "name":        name[:50],
            "description": description[:255],
            "serial":      self.generate_serial(server.name, asset_uuid, vmid),
            "osname":      osname[:255],
            "osversion":   "",
            "agent":       f"{_MANIFEST['name']} {_MANIFEST['version']}",
            "srcip":       ip[:255],
            "srcmac":      mac[:255],
            "domain":      domain[:255],
        }
        if template is not None:
            defaults["template"] = template
            defaults["is_template_forced"] = False
        return defaults

    def upsert_asset(
        self, resource, resource_type, server, node_name,
        session, base_url, backup_storages, logger,
    ):
        vmid = resource["vmid"]
        name = resource.get("name") or f"{resource_type}-{vmid}"
        status = resource.get("status", "unknown")

        asset_uuid = str(
            uuid_module.uuid5(
                uuid_module.NAMESPACE_DNS,
                f"proxmox-{server.name}-{resource_type}-{vmid}",
            )
        )
        description = (
            f"{server.name}/{node_name} - "
            f"{resource_type.upper()} {vmid} ({status})"
        )

        config = self.fetch_config(session, base_url, node_name, resource_type, vmid, logger)
        agent_ifaces = {}
        if resource_type == "qemu":
            agent_ifaces = self.fetch_agent_ifaces(session, base_url, node_name, vmid, logger)

        ip, mac, domain, osname = self.extract_vm_details(resource_type, config, agent_ifaces)

        template_name = "Proxmox QEMU VM" if resource_type == "qemu" else "Proxmox LXC Container"
        template = Template.objects.filter(name=template_name).first()

        defaults = self.build_asset_defaults(
            name, description, asset_uuid, server, vmid, ip, mac, domain, osname, template
        )

        with transaction.atomic():
            try:
                asset = InventoryBase.objects.select_for_update().get(uuid=asset_uuid)
                created = False
            except InventoryBase.DoesNotExist:
                asset = InventoryBase(uuid=asset_uuid)
                created = True

            for field_name, value in defaults.items():
                setattr(asset, field_name, value)

            # Set before save() so the core inventory_received signal already
            # has the proxmox context when it fires.
            asset._proxmox_context_data = {
                "server":        server.name,
                "node":          node_name,
                "vmid":          vmid,
                "resource_type": resource_type,
                "status":        status,
            }
            asset.save()

        ProxmoxAsset.objects.update_or_create(
            server=server,
            vmid=vmid,
            resource_type=resource_type,
            defaults={"asset": asset, "status": status},
        )

        self.upsert_inventory_sections(
            asset, template, resource, resource_type,
            config, agent_ifaces, backup_storages,
            session, base_url, node_name, logger,
        )

        action = "created" if created else "updated"
        logger.info(f"  {action}: {name} (vmid={vmid})")

        return (1, 0) if created else (0, 1)
