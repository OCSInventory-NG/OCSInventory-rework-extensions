export async function createComponent(api) {
	const PageHeader = api.getComponent("PageHeader")
	const ProxmoxPanelMod = await api.importModule(
		"/extensions/proxmoxapi/components/ProxmoxPanel.js",
	)
	const ProxmoxPanel = await ProxmoxPanelMod.createComponent(api)

	return {
		name: "ProxmoxConfig",
		components: { PageHeader, ProxmoxPanel },

		data() {
			return { loadError: null }
		},

		errorCaptured(err, vm, info) {
			console.error("ProxmoxConfig errorCaptured:", err, info)
			this.loadError = err?.message || String(err)
			return false
		},

		template: `
			<div id="proxmoxapi-config" class="container-xl">
				<PageHeader :page-title="$t('proxmoxapi.title')" />
				<div class="page-body">
					<div v-if="loadError" class="alert alert-danger">
						Erreur lors du chargement : {{ loadError }}
					</div>
					<ProxmoxPanel v-else />
				</div>
			</div>
		`,
	}
}
