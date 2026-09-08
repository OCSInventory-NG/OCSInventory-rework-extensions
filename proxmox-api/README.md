# Proxmox API Extension for OCS Inventory

OCS Inventory extension that integrates Proxmox VE hypervisors. It allows configuring connections to Proxmox servers and synchronizing the inventory of VMs and LXC containers as OCS assets.

## Features

- Manage multiple Proxmox servers (add, edit, delete)
- Synchronization of QEMU VMs and LXC containers as OCS Inventory assets
- Metadata collection: CPU, memory, disks, network interfaces, snapshots, backups
- Asset inventory view (per server or global)
- Dashboard with machine counts and running/stopped server status
- Automation trigger `proxmox_asset_synced` for OCS rules

## Requirements

- OCS Inventory 3.0.0+
- Extension frontend and backend files
- Python 3.8+
- Django REST Framework

## Installation

### Backend

**1. Copy the extension files**

```bash
cp -r backend/proxmoxapi /path/to/ocsinventory-backend/extensions/
```

The folder must be named `proxmoxapi` once deployed: it must match the
`django_app` declared in `extension.json` and is what Django uses as the app
label.

**2. Install the extension**

```bash
python manage.py extensions install proxmoxapi
```

This registers the extension and applies its migrations. A plain
`python manage.py migrate` does **not** do this on its own: an extension's
migrations are only picked up once it has been installed, so simply copying
the folder into `extensions/` has no effect until this command runs. The
command marks the extension installed and restarts itself (a short
confirmation is asked first) so Django loads it.

Add `--enable` to enable it in the same step, or enable it separately:

```bash
python manage.py extensions enable proxmoxapi
```

**3. Restart the application server**

Enabling the extension only takes effect in the database; the running
application server(s) must be restarted for its API routes to be mounted.

**4. Verify the extension appears as enabled**

```bash
python manage.py extensions list
```

### Frontend

**1. Copy the extension files**

```bash
cp -r frontend/proxmoxapi /path/to/ocsinventory-frontend/public/extensions/
```

**2. Enable the backend if not already done**

**3. Refresh the frontend**

## Usage

### Web interface

The extension adds two entries to the OCS menu:

- **Configurations > Proxmox Hypervisors**: server management (add, edit, delete)
- **Inventory > Proxmox Inventory**: global dashboard and synchronized assets view

For each server, a link gives access to its associated assets.

### Inventory synchronization

The synchronization is an automated action that fetches VMs and containers from the Proxmox API and creates or updates them as OCS assets.

```bash
python manage.py automation --force proxmoxInventory.ProxmoxInventory
```

The schedule and settings for this action can be configured from the application frontend.

## REST API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/proxmoxapi/servers/` | List all servers |
| POST | `/proxmoxapi/servers/` | Create a server |
| GET | `/proxmoxapi/servers/{id}/` | Get server details |
| PUT | `/proxmoxapi/servers/{id}/` | Update a server |
| DELETE | `/proxmoxapi/servers/{id}/` | Delete a server |
| GET | `/proxmoxapi/servers/{id}/assets/` | List assets linked to a server |

## Structure

### Backend

Deploy to `ocsinventory-backend/extensions/`.

```
backend/
└── proxmoxapi/
    ├── apps.py                       # Django config + automation
    ├── models.py                     # ProxmoxServer, ProxmoxAsset
    ├── serializer.py
    ├── views.py                      # ProxmoxServerViewSet
    ├── urls.py
    ├── extension.json
    ├── management/
    │   └── commands/
    │       └── proxmox_inventory.py  # Sync command
    └── migrations/
```

### Frontend

Deploy to `ocsinventory-frontend/public/extensions/`.

```
frontend/
└── proxmoxapi/
    ├── plugin.js                     # Entry point, routes, i18n
    ├── components/
    │   ├── ProxmoxPanel.js           # Server list and management
    │   ├── ProxmoxModal.js           # Add / edit form
    │   └── ProxmoxAssets.js          # Synchronized assets view
    └── locales/
        ├── en.json
        └── fr.json
```
