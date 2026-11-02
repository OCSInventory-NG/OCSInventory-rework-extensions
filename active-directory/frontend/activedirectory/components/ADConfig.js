export async function createComponent(api) {
	const PageHeader = api.getComponent("PageHeader")
	const ADDomainsPanelMod = await api.importModule("/extensions/activedirectory/components/ADDomainsPanel.js")
	const ADDomainsPanel = await ADDomainsPanelMod.createComponent(api)

	return {
		name: "ADConfig",
		components: { PageHeader, ADDomainsPanel },

		data() {
			return { loadError: null }
		},

		errorCaptured(err, vm, info) {
			console.error("ADConfig errorCaptured:", err, info)
			this.loadError = err?.message || String(err)
			return false
		},

		template: `
			<div id="activedirectory-config" class="container-xl">
				<PageHeader :page-title="$t('activedirectory.title')" />
				<div class="page-body">
					<div v-if="loadError" class="alert alert-danger">
						{{ loadError }}
					</div>
					<ADDomainsPanel v-else />
				</div>
			</div>
		`,
	}
}
