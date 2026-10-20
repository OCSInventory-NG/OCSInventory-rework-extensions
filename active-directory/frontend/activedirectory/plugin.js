// Entry point. The frontend loader fetches this file and calls register()
// once the extension is enabled (see src/extensions/loader.js in the core).
window.OCS_EXTENSIONS = window.OCS_EXTENSIONS || {}

window.OCS_EXTENSIONS["activedirectory"] = {
	async register(api) {
		const fr = await fetch(api.withBase("extensions/activedirectory/locales/fr.json")).then((r) => r.json())
		api.mergeI18n("fr", fr)
		const en = await fetch(api.withBase("extensions/activedirectory/locales/en.json")).then((r) => r.json())
		api.mergeI18n("en", en)

		const ADConfigMod = await api.importModule("/extensions/activedirectory/components/ADConfig.js")
		const AppLayout = api.getComponent("AppLayout")

		api.addRoute({
			path: "/configurations/activedirectory",
			name: "ActiveDirectoryConfig",
			component: await ADConfigMod.createComponent(api),
			meta: { layout: AppLayout, requireAuth: true },
		})

		// Nested inside the existing "configurations" menu group, next to the
		// other directory/network configuration pages.
		api.addMenuChildItem("configurations", {
			headerKey: "activedirectory.title",
			link: "/configurations/activedirectory",
			route: "ActiveDirectoryConfig",
			column: "inventory",
		})

		// Inventory page listing synchronized AD computers and their link status.
		const ADComputersPageMod = await api.importModule("/extensions/activedirectory/components/ADComputersPage.js")

		api.addRoute({
			path: "/inventory/activedirectory",
			name: "ActiveDirectoryComputers",
			component: await ADComputersPageMod.createComponent(api),
			meta: { layout: AppLayout, requireAuth: true },
		})

		api.addMenuChildItem("inventory", {
			headerKey: "activedirectory.computers_title",
			link: "/inventory/activedirectory",
			route: "ActiveDirectoryComputers",
			column: "general",
		})

		// Widget injected into the core asset detail page (domain, OU,
		// assigned user), only rendered when the asset has a linked AD computer.
		api.registerSlot("inventory.asset.detail.afterAccountInfo", {
			component: async () => {
				const mod = await api.importModule("/extensions/activedirectory/components/ADAssetSlot.js")
				return mod.createComponent(api)
			},
		})
	},
}
