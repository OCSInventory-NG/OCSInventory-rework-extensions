export async function createComponent(api) {
	const Datatable = api.getComponent("Datatable")
	const Alert = api.getComponent("Alert")
	const Loader = api.getComponent("Loader")
	const ADDomainModalComp = await api.importModule("/extensions/activedirectory/components/ADDomainModal.js")
	const ADDomainModal = ADDomainModalComp.createComponent(api)
	const ADSyncReportsModalComp = await api.importModule("/extensions/activedirectory/components/ADSyncReportsModal.js")
	const ADSyncReportsModal = await ADSyncReportsModalComp.createComponent(api)
	const { startDomainSync, waitForReport } = await api.importModule("/extensions/activedirectory/components/adSync.js")

	const SECURITY_VARIANTS = { ldaps: "success", starttls: "info", none: "warning" }
	const SYNC_STATUS_VARIANTS = { success: "success", error: "danger", running: "info" }

	return {
		name: "ADDomainsPanel",
		components: { Datatable, Alert, Loader, ADDomainModal, ADSyncReportsModal },

		data() {
			return {
				loading: false,
				isbusy: false,
				rowdata: [],
				rowheader: [
					"name",
					"server",
					"security",
					"base_dn",
					"assigned_user_attribute",
					"computers_count",
					"last_sync_at",
					"last_sync_status",
					"is_active",
					"actions",
				],
				errored: false,
				errormsg: null,
				canview: false,
				canadd: false,
				canedit: false,
				candelete: false,
				syncingId: null,
			}
		},

		methods: {
			checkPermissions() {
				const rawPermissions = localStorage.getItem("permissions")
				const permissions = rawPermissions ? rawPermissions.split(",") : []

				if (permissions.includes("activedirectory_view_addomain")) {
					this.canview = true
					this.canadd = permissions.includes("activedirectory_add_addomain")
					this.canedit = permissions.includes("activedirectory_change_addomain")
					this.candelete = permissions.includes("activedirectory_delete_addomain")
				} else {
					this.errormsg = this.$t("message.dont_have_right_to_see")
					this.errored = true
				}
			},

			async load() {
				this.loading = true
				try {
					await this.fetchDomains()
				} finally {
					this.loading = false
				}
			},

			async fetchDomains() {
				this.isbusy = true
				this.errored = false
				this.errormsg = null
				try {
					const response = await this.$api.generic.get("/activedirectory/domains/")
					const results = response?.results ?? response ?? []
					this.rowdata = results.map((domain) => ({
						...domain,
						server: `${domain.server}:${domain.port}`,
						__security_variant: SECURITY_VARIANTS[domain.security] || "secondary",
						security: this.$t(`activedirectory.security_${domain.security}`),
						last_sync_at: domain.last_sync_at
							? new Date(domain.last_sync_at).toLocaleString(this.$i18n.locale)
							: "",
						__last_sync_status_variant: SYNC_STATUS_VARIANTS[domain.last_sync_status] || "secondary",
						last_sync_status: domain.last_sync_status
							? this.$t(`activedirectory.sync_status_${domain.last_sync_status}`)
							: "",
						is_active: domain.is_active ? this.$t("generic.yes") : this.$t("generic.no"),
					}))
				} catch (e) {
					this.errormsg = e.message
					this.errored = true
				} finally {
					this.isbusy = false
				}
			},

			async reloadDatatable() {
				await this.fetchDomains()
			},

			async deleteDomain(domainId) {
				if (!confirm(this.$t("activedirectory.confirm_delete"))) return
				try {
					await this.$api.generic.delete(`/activedirectory/domains/${domainId}/`)
					await this.load()
				} catch (e) {
					this.errormsg = e.response?.data?.error || e.message
					this.errored = true
				}
			},

			async syncDomain(domainId) {
				this.syncingId = domainId
				this.errored = false
				this.errormsg = null
				try {
					const reportId = await startDomainSync(api, domainId)
					const report = reportId ? await waitForReport(api, reportId) : null
					await this.fetchDomains()
					if (report?.status === "error") {
						this.errormsg = this.$t("activedirectory.sync_failed", { error: report.error_message })
						this.errored = true
					}
				} catch (e) {
					this.errormsg = e.response?.data?.detail || e.response?.data?.error || e.message
					this.errored = true
				} finally {
					this.syncingId = null
				}
			},
		},

		async mounted() {
			this.checkPermissions()
			if (!this.canview) return
			await this.load()
		},

		template: `
			<div id="activedirectory-panel">
				<div class="card">
					<div class="card-body">
						<Alert v-if="errored" :message="errormsg" :cols="true" variant="danger" />

						<div v-if="loading" class="ocs-loader">
							<Loader />
						</div>

						<div v-else-if="canview">
							<ADDomainModal
								v-if="canadd"
								@reload-datatable="reloadDatatable"
							/>

							<Datatable
								id="activedirectory-domains-datatable"
								:rowdata="rowdata"
								:rowheader="rowheader"
								:isbusy="isbusy"
								title="activedirectory/domains"
								translationkey="activedirectory."
								:badgecells="['security', 'last_sync_status']"
								:candelete="candelete"
								:candeletemultiple="false"
								:hascustomactions="true"
								@reload-datatable="reloadDatatable"
							>
								<template v-slot:cell(firstActions)="slotProps">
									<ADSyncReportsModal
										:domain-id="slotProps.row.item.id"
										:domain-name="slotProps.row.item.name"
										@reload-datatable="reloadDatatable"
									/>
									<button
										v-if="canedit"
										type="button"
										class="btn btn-ghost-dark"
										:title="$t('activedirectory.sync_now')"
										:disabled="syncingId === slotProps.row.item.id"
										@click="syncDomain(slotProps.row.item.id)"
									>
										<font-awesome-icon
											:icon="['fas', 'arrows-rotate']"
											:class="{ loading: syncingId === slotProps.row.item.id }"
										/>
									</button>
									<ADDomainModal
										v-if="canedit"
										:id="slotProps.row.item.id"
										:update="true"
										@reload-datatable="reloadDatatable"
									/>
								</template>
							</Datatable>
						</div>
					</div>
				</div>
			</div>
		`,
	}
}
