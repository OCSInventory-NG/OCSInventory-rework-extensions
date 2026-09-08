window.OCS_EXTENSIONS = window.OCS_EXTENSIONS || {}

window.OCS_EXTENSIONS["proxmoxapi"] = {
	async register(api) {
		// i18n
		const fr = await fetch("/extensions/proxmoxapi/locales/fr.json").then(
			(r) => r.json(),
		)
		api.mergeI18n("fr", fr)
		const en = await fetch("/extensions/proxmoxapi/locales/en.json").then(
			(r) => r.json(),
		)
		api.mergeI18n("en", en)

		// Register route for Proxmox configuration page
		const ProxmoxConfigMod = await api.importModule(
			"/extensions/proxmoxapi/components/ProxmoxConfig.js",
		)
		const ProxmoxConfigComponent =
			await ProxmoxConfigMod.createComponent(api)

		const ProxmoxAssetsMod = await api.importModule(
			"/extensions/proxmoxapi/components/ProxmoxAssets.js",
		)
		const ProxmoxGlobalAssetsComponent = await ProxmoxAssetsMod.createComponent(api)

		const AppLayout = api.getComponent("AppLayout")

		api.addRoute({
			path: "/configurations/proxmoxapi",
			name: "ProxmoxConfig",
			component: ProxmoxConfigComponent,
			meta: { layout: AppLayout, requireAuth: true },
		})

		api.addRoute({
			path: "/inventory/proxmoxapi/assets",
			name: "ProxmoxGlobalInventory",
			component: ProxmoxGlobalAssetsComponent,
			meta: { layout: AppLayout, requireAuth: true },
		})

		// Add Proxmox page inside the configurations menu group
		api.addMenuChildItem("configurations", {
			headerKey: "proxmoxapi.title",
			link: "/configurations/proxmoxapi",
			route: "ProxmoxConfig",
			column: "inventory",
		})

		// Add global inventory page inside the inventory menu group
		api.addMenuChildItem("inventory", {
			headerKey: "proxmoxapi.global_inventory_title",
			link: "/inventory/proxmoxapi/assets",
			route: "ProxmoxGlobalInventory",
			column: "general",
		})
	}
}
