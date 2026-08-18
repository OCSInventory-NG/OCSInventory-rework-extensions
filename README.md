# OCSInventory Rework Extensions

This repository hosts community and official extensions for **OCS Inventory 3.0**.

OCS Inventory 3.0 introduces a modular architecture that allows the core product to be extended without modifying its source code. This repository is the central place where those extensions live, so they can be discovered, shared, reviewed, and maintained by the community.

## What is an extension?

An extension is a self-contained add-on that adds or enhances a feature of OCS Inventory 3.0. It can target the backend engine, the web console, or both, and can range from a small integration to a full-featured module.

## Repository structure

Each extension lives in its own top-level folder. Inside that folder, the extension is split into two possible parts, matching the two components of OCS Inventory 3.0:

```
<extension-name>/
├── README.md      # Description, purpose and documentation of the extension
├── backend/       # Extension code for the backend engine
└── frontend/      # Extension code for the web console
```

- **backend/**: code that extends or interacts with the OCS Inventory backend engine (data processing, agents, APIs, jobs, etc.).
- **frontend/**: code that extends or interacts with the OCS Inventory web console (UI components, pages, integrations, etc.).

An extension does not necessarily need both folders. A backend-only or frontend-only extension is perfectly valid; it simply omits the folder it does not need.

Every extension include its own `README.md` describing:

- What the extension does and why it is useful
- Requirements and compatibility (OCS Inventory version, dependencies, etc.)
- Installation and configuration instructions
- Usage examples, if relevant
- Known limitations, if any

## Adding a new extension

To contribute a new extension:

1. Create a new top-level folder named after your extension (use a short, descriptive, kebab-case name).
2. Add a `backend/` and/or `frontend/` folder depending on what your extension touches.
3. Add a `README.md` at the root of your extension folder following the guidelines above.
4. Open a pull request describing your extension and its purpose.

## Contributing

Contributions are welcome, whether they are new extensions, improvements to existing ones, bug fixes, or documentation updates. Please open an issue or a pull request to discuss significant changes before submitting them.

## License

See the [LICENSE](LICENSE) file for license information. Unless stated otherwise in an extension's own `README.md`, the license of this repository applies.
