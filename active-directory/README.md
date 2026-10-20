# Active Directory Extension for OCS Inventory

OCS Inventory extension that reads computer objects from one or more Active
Directory domains over LDAP (read-only), links each one to the core asset
(`InventoryBase`) sharing its normalized name, and surfaces the domain, OU
and assigned user on that asset's detail page.

## Features

- Manage multiple AD domains (add, edit, delete), each with its own LDAP
  connection settings (server, port, LDAPS/StartTLS, certificate
  verification, bind credentials, base DN, configurable "assigned user"
  attribute - `managedBy` by default)
- Test the LDAP connection before relying on it
- Paginated, read-only synchronization of computer objects per domain, run
  daily by the core scheduler, on demand from the configuration page, or via
  `python manage.py ad_sync`
- Conservative name-based matching to a core asset, with manual relink for
  ambiguous or unmatched computers (via the REST API)
- A sync report per run (counts, status, error) kept for auditability
- A widget injected into the core asset detail page: domain, organizational
  unit, assigned user (name/login/email) and whether the object is still
  enabled in the directory - shown only when the asset has a linked AD
  computer
- Automation trigger: `inventory_received` is enriched with
  `activedirectory.{domain, ou, enabled, assigned_user}` for assets with a
  linked AD computer

## Requirements

- OCS Inventory 3.0.0+ (Server Backend Rework + Server Frontend Rework)
- Network access from the backend to the configured domain controller(s)
- Extension frontend and backend files
- No new external dependency (`python-ldap` ships with `django-auth-ldap`,
  already a core requirement)

## Installation

### Backend

**1. Copy the extension files**

```bash
cp -r backend/activedirectory /path/to/ocsinventory-backend/extensions/
```

The folder must be named `activedirectory` once deployed: it must match the
`django_app` declared in `extension.json` and is what Django uses as the app
label.

**2. Install the extension**

```bash
python manage.py extensions install activedirectory
```

This registers the extension and applies its migrations (including the
daily sync scheduler entry). A plain `python manage.py migrate` does **not**
do this on its own: an extension's migrations are only picked up once it has
been installed.

Add `--enable` to enable it in the same step, or enable it separately:

```bash
python manage.py extensions enable activedirectory
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
cp -r frontend/activedirectory /path/to/ocsinventory-frontend/public/extensions/
```

**2. Enable the backend if not already done**

**3. Refresh the frontend**, then enable "Active Directory" from the
Extensions page (`/configurations/extensions`).

## Usage

### Web interface

The extension adds one entry to the OCS menu:

- **Configurations > Active Directory**: manage domains (add, edit, test,
  synchronize, view sync history, delete)

It also injects an "Active Directory" widget into any linked asset's detail
page: domain, organizational unit, assigned user and directory status.

### Synchronize

From the configuration page, via the per-domain "Synchronize" action or
from its sync history view, or from the CLI:

```bash
python manage.py ad_sync
python manage.py ad_sync --domain 42
```

The core scheduler also runs it once a day.

## REST API

See `backend/activedirectory/README.md` for the full contract
(`/activedirectory/domains/`, `/computers/`, `/reports/`).

## Structure

### Backend

Deploy to `ocsinventory-backend/extensions/`.

```
backend/
└── activedirectory/
    ├── apps.py                 # Django config, scheduler registration, automation hook
    ├── models.py                # ADDomain, ADComputer, SyncReport
    ├── ldap_client.py            # Read-only, paginated LDAP access
    ├── matching.py                # Name-based asset matching
    ├── serializers.py
    ├── views.py                   # ADDomainViewSet, ADComputerViewSet, SyncReportViewSet
    ├── urls.py
    ├── extension.json
    ├── config.json
    ├── management/
    │   ├── ad_sync_task.py        # Scheduler task wrapper
    │   └── commands/
    │       └── ad_sync.py          # Sync logic
    └── migrations/
```

### Frontend

Deploy to `ocsinventory-frontend/public/extensions/`.

```
frontend/
└── activedirectory/
    ├── plugin.js                 # Entry point, route, menu, i18n, asset-detail slot
    ├── components/
    │   ├── ADConfig.js              # Configuration page wrapper
    │   ├── ADDomainsPanel.js        # Domain list and actions
    │   ├── ADDomainModal.js         # Add / edit domain modal, test connection
    │   ├── ADSyncReportsModal.js    # Sync history modal for one domain
    │   └── ADAssetSlot.js           # Widget injected into the asset detail page
    └── locales/
        ├── en.json
        └── fr.json
```
