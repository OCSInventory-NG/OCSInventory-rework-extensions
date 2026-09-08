# Sample Extension

Minimal reference extension for developers. It is not a real business
feature, it's a small comment-on-an-asset feature used as a pretext to
demonstrate every extension point currently supported by the OCS Inventory
3.0 extension engine. Every file starts with an `Example: ...` comment
explaining what it demonstrates.

## Features

- Attach free-text comments to an inventory asset
- A model owned by the extension (`SampleComment`), related to a core asset via a `ForeignKey` (the only supported way to attach data to a core object, an extension can never add a field directly to a core model)
- A REST API (CRUD) plus a custom action beyond plain CRUD (`GET /comments/count/`)
- A hook into the automation engine: wraps the `inventory_received` resolver to expose `sample.comments_count`, stacking on top of any other extension already hooked on the same trigger instead of overwriting it
- A `manage.py` command, auto-discovered, reading the extension's own static `config.json`
- A page with its own top-level menu entry, reusing the core `PageHeader` and `Datatable` components
- Injecting a widget into an existing core page (the asset detail page) via a UI slot, without modifying that page
- Gating UI by permission (`hasPermissions`)

## Requirements

- OCS Inventory 3.0.0+ (Server Backend Rework + Server Frontend Rework)
- Extension frontend and backend files
- No external dependency

## Installation

### Backend

**1. Copy the extension files**

```bash
cp -r backend/sampleextension /path/to/ocsinventory-backend/extensions/
```

The folder must be named `sampleextension` once deployed: it must match the
`django_app` declared in `extension.json` and is what Django uses as the app
label.

**2. Install the extension**

```bash
python manage.py extensions install sampleextension
```

This registers the extension and applies its migrations. A plain
`python manage.py migrate` does **not** do this on its own: an extension's
migrations are only picked up once it has been installed, so simply copying
the folder into `extensions/` has no effect until this command runs. The
command marks the extension installed and restarts itself (a short
confirmation is asked first) so Django loads it.

Add `--enable` to enable it in the same step, or enable it separately:

```bash
python manage.py extensions enable sampleextension
```

**3. Restart the application server**

Enabling the extension only takes effect in the database; the running
application server(s) must be restarted for its API routes to be mounted.
Disabling it takes effect immediately.

**4. Verify the extension appears as enabled**

```bash
python manage.py extensions list
```

### Frontend

**1. Copy the extension files**

```bash
cp -r frontend/sampleextension /path/to/ocsinventory-frontend/public/extensions/
```

**2. Enable the backend if not already done**

**3. Refresh the frontend**, then enable "Sample Extension" from the Extensions page (`/configurations/extensions`).

## Usage

### Web interface

The extension adds one entry to the OCS menu:

- **Inventory > Sample Extension**: list of all comments across assets

It also injects a "Comments" widget into any asset's detail page, to add/view/delete comments for that asset.

### CLI command

```bash
python manage.py sample_comment_stats
```

Prints how many comments exist and how many assets have at least one.

## REST API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/sampleextension/comments/` | List comments (filter with `?asset=<id>`) |
| POST | `/sampleextension/comments/` | Create a comment |
| GET | `/sampleextension/comments/{id}/` | Get comment details |
| PUT | `/sampleextension/comments/{id}/` | Update a comment |
| DELETE | `/sampleextension/comments/{id}/` | Delete a comment |
| GET | `/sampleextension/comments/count/` | Count all comments |

## Structure

### Backend

Deploy to `ocsinventory-backend/extensions/`.

```
backend/
└── sampleextension/
    ├── apps.py                       # Django config + automation hook
    ├── models.py                     # SampleComment
    ├── serializer.py
    ├── views.py                      # SampleCommentViewSet
    ├── urls.py
    ├── extension.json
    ├── config.json                   # Extension's own static settings
    ├── management/
    │   └── commands/
    │       └── sample_comment_stats.py
    └── migrations/
```

### Frontend

Deploy to `ocsinventory-frontend/public/extensions/`.

```
frontend/
└── sampleextension/
    ├── plugin.js                     # Entry point, routes, menu, i18n, slot
    ├── components/
    │   ├── SampleCommentsPage.js     # Comments list page
    │   └── SampleCommentSlot.js      # Widget injected into the asset detail page
    └── locales/
        ├── en.json
        └── fr.json
```
