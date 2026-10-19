# Active Directory

Read-only synchronization of Active Directory computer objects into OCS
Inventory, via LDAP. Each AD computer is linked to the core asset
(`InventoryBase`) that shares its normalized name, and the link can be
corrected by hand when the automatic match is wrong or ambiguous.

This is the backend half of the extension. There is no frontend package yet:
the asset detail widget described in the functional specification
(domain/OU/assigned user) is not implemented here.

## Features

- One or more configured AD domains (`ADDomain`), each with its own LDAP
  connection settings (server, port, LDAPS/StartTLS, certificate
  verification, bind credentials, base DN, configurable "assigned user"
  attribute - `managedBy` by default)
- `bind_password` stored encrypted at rest, reusing the core's own
  `ocs_framework.crypto` (the same mechanism as `AuthConfig`); never
  returned by the API
- Paginated, read-only LDAP sync of computer objects (`ADComputer`) per
  domain, via `python-ldap` (already a dependency through
  `django-auth-ldap`, see `auth/auth_backend/ldap_backend.py`) - no new
  external dependency
- Conservative name-based matching to a core asset: a computer links
  automatically only when exactly one `InventoryBase` matches its name
  (case-insensitive, NetBIOS `$` suffix stripped); zero or several
  candidates are left `unlinked`/`ambiguous` for manual resolution
  (`POST .../link/`, `POST .../unlink/`)
- A `SyncReport` per sync run (counts, status, error) for auditability
- A REST API (`/activedirectory/domains/`, `/computers/`, `/reports/`),
  gated by the standard Django model permissions
  (`permission.permissions.DefaultModelPermissions`)
- A daily scheduled sync, registered with the core's scheduler
  (`automation.scheduler`) without modifying it
- A hook into the automation engine: wraps the `inventory_received`
  resolver to expose `activedirectory.{domain, ou, enabled, assigned_user}`
  when the asset has a linked AD computer, stacking on top of any other
  extension already hooked on the same trigger instead of overwriting it

## Requirements

- OCS Inventory 3.0.0+ (Server Backend Rework)
- Network access from the backend to the configured domain controller(s)
- No new external dependency (`python-ldap` ships with `django-auth-ldap`,
  already a core requirement)

## Installation

**1. Copy the extension files**

```bash
cp -r activedirectory /path/to/ocsinventory-backend/extensions/
```

The folder must be named `activedirectory` once deployed: it must match the
`django_app` declared in `extension.json` and is what Django uses as the
app label.

**2. Install the extension**

```bash
python manage.py extensions install activedirectory
```

This registers the extension and applies its migrations (including the
`ad_sync_task.ADSync` daily scheduler entry). A plain `python manage.py
migrate` does **not** do this on its own: an extension's migrations are
only picked up once it has been installed.

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

## Usage

### Configure a domain

Create an `ADDomain` via the REST API (`POST /activedirectory/domains/`),
then verify connectivity:

```bash
POST /activedirectory/domains/42/test/
```

### Synchronize

On demand:

```bash
POST /activedirectory/domains/42/sync/
```

Or from the CLI, for all active domains or a single one:

```bash
python manage.py ad_sync
python manage.py ad_sync --domain 42
```

The scheduler also runs it once a day (see `python manage.py automation`).

## REST API

See the functional specification for the full contract
(`/activedirectory/domains/`, `/computers/`, `/reports/`). Summary:

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/activedirectory/domains/` | List / create domains |
| GET/PUT/PATCH/DELETE | `/activedirectory/domains/{id}/` | Retrieve / update / delete a domain |
| POST | `/activedirectory/domains/{id}/test/` | Test the LDAP connection |
| POST | `/activedirectory/domains/{id}/sync/` | Trigger a synchronization (409 if already running) |
| GET | `/activedirectory/computers/` | List computers (filter/search) |
| GET | `/activedirectory/computers/{id}/` | Retrieve a computer |
| POST | `/activedirectory/computers/{id}/link/` | Manually link to an asset |
| POST | `/activedirectory/computers/{id}/unlink/` | Remove the link |
| GET | `/activedirectory/reports/` | List sync reports (filter by `domain`) |
| GET | `/activedirectory/reports/{id}/` | Retrieve a sync report |

## Automation context

The `inventory_received` trigger receives, when the asset has a linked AD
computer:

```json
"activedirectory": {
    "domain": "CORP",
    "ou": "OU=Laptops,OU=Paris,DC=corp,DC=local",
    "enabled": true,
    "assigned_user": "jdoe"
}
```

Absent when the asset has no linked AD computer.

## Structure

Deploy to `ocsinventory-backend/extensions/`.

```
activedirectory/
├── apps.py                 # Django config, scheduler registration, automation hook
├── models.py                # ADDomain, ADComputer, SyncReport
├── ldap_client.py            # Read-only, paginated LDAP access
├── matching.py                # Name-based asset matching
├── serializers.py
├── views.py                   # ADDomainViewSet, ADComputerViewSet, SyncReportViewSet
├── urls.py
├── extension.json
├── config.json                # Extension's own static settings (page size, timeouts)
├── tests.py
├── management/
│   ├── ad_sync_task.py        # AbstractTask wrapper, registered into automation.tasks
│   └── commands/
│       └── ad_sync.py          # The actual sync logic
└── migrations/
    └── 0001_initial.py         # Models + daily scheduler entry
```
