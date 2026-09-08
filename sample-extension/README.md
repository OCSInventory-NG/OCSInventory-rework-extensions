# Sample Extension

Minimal reference extension for developers. It is not a real business
feature — it's a small comment-on-an-asset feature used as a pretext to
demonstrate every extension point currently supported by the OCS Inventory
3.0 extension engine. Every file starts with an `Example: ...` comment
explaining what it demonstrates.

## What it does

Lets a user attach free-text comments to an inventory asset.

## What it demonstrates

**Backend**
- A model owned by the extension (`SampleComment`), related to a core asset via a `ForeignKey` (the only supported way to attach data to a core object — an extension can never add a field directly to a core model)
- A REST API (CRUD) plus a custom action beyond plain CRUD (`GET /comments/count/`)
- A hook into the automation engine: wraps the `inventory_received` resolver to expose `sample.comments_count`, stacking on top of any other extension already hooked on the same trigger instead of overwriting it
- A `manage.py` command, auto-discovered, reading the extension's own static `config.json`

**Frontend**
- A page with its own top-level menu entry, reusing the core `PageHeader` and `Datatable` components
- A form
- Injecting a widget into an existing core page (the asset detail page) via a UI slot, without modifying that page
- Gating UI by permission (`hasPermissions`)
- Translations (English/French)

## Requirements

OCS Inventory 3.0 (Server Backend Rework + Server Frontend Rework). No external dependency.

## Installation

1. Copy `backend/sampleextension/` into `<backend>/extensions/sampleextension/`.
2. Restart the backend and run `python manage.py migrate`.
3. Copy `frontend/sampleextension/` into `<frontend>/public/extensions/sampleextension/`.
4. Refresh the frontend, then enable "Sample Extension" from the Extensions page (`/configurations/extensions`).
5. Restart the backend once more — enabling an extension only mounts its REST routes at startup (disabling takes effect immediately).

## Usage

- "Sample Extension" menu entry → list of all comments across assets.
- Any asset's detail page → a "Comments" widget to add/view/delete comments for that asset.
- `python manage.py sample_comment_stats` → prints how many comments exist.
