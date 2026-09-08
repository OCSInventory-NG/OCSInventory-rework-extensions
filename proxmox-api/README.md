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
cp -r proxmoxapi /path/to/ocs-inventory-backend/extensions/
```

**2. Restart Django**

**3. Apply migrations**

```bash
python manage.py migrate
```

**4. Verify the extension appears as disabled in the UI**

**5. Enable the extension**

### Frontend

**1. Copy the extension files**

```bash
cp -r proxmoxapi /path/to/ocs-inventory-frontend/public/config/extensions/
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

Deploy to `ocs-inventory-backend/extensions/`.

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

Deploy to `ocs-inventory-frontend/public/config/extensions/`.

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
