export function createComponent(api) {
	const Datatable = api.getComponent("Datatable")
	const Alert = api.getComponent("Alert")
	const Loader = api.getComponent("Loader")

	const STATUS_VARIANTS = { success: "success", error: "danger", running: "info" }

	return {
		name: "ADSyncReportsModal",
		components: { Datatable, Alert, Loader },
		props: {
			domainId: { type: [String, Number], required: true },
			domainName: { type: String, default: "" },
		},

		data() {
			return {
				reportsmodal: false,
				loading: false,
				isbusy: false,
				syncing: false,
				rowdata: [],
				rowheader: ["started_at", "status", "created_count", "linked_count", "missing_count", "error_message"],
				errored: false,
				errormsg: null,
			}
		},

		methods: {
			openModal() {
				this.reportsmodal = true
				this.load()
			},

			async load() {
				this.loading = true
				try {
					await this.fetchReports()
				} finally {
					this.loading = false
				}
			},

			async fetchReports() {
				this.isbusy = true
				this.errored = false
				this.errormsg = null
				try {
					const response = await this.$api.generic.get("/activedirectory/reports/", { domain: this.domainId })
					const results = response?.results ?? response ?? []
					this.rowdata = results.map((report) => ({
						...report,
						started_at: new Date(report.started_at).toLocaleString(this.$i18n.locale),
						__status_variant: STATUS_VARIANTS[report.status] || "secondary",
						status: this.$t(`activedirectory.sync_status_${report.status}`),
					}))
				} catch (e) {
					this.errormsg = e.message
					this.errored = true
				} finally {
					this.isbusy = false
				}
			},

			async syncNow() {
				this.syncing = true
				try {
					await api.http.post(`/activedirectory/domains/${this.domainId}/sync/`)
					await this.load()
					this.$emit("reloadDatatable")
				} catch (e) {
					this.errormsg = e.response?.data?.detail || e.response?.data?.error || e.message
					this.errored = true
				} finally {
					this.syncing = false
				}
			},
		},

		template: `
            <div id="activedirectory-reports-modal">
                <button
                    type="button"
                    class="btn btn-ghost-info"
                    :title="$t('activedirectory.view_reports')"
                    @click="openModal"
                >
                    <font-awesome-icon :icon="['fas', 'clock-rotate-left']" />
                </button>

                <b-modal
                    v-model="reportsmodal"
                    :title="$t('activedirectory.reports_title', { name: domainName })"
                    hide-footer
                    modal-class="custom-modal"
                    size="xl"
                >
                    <template #header="{ close }">
                        <h5 class="modal-title">
                            {{ $t('activedirectory.reports_title', { name: domainName }) }}
                        </h5>
                        <b-button
                            size="sm"
                            variant="outline-danger"
                            @click="close()"
                        >
                            <font-awesome-icon
                                :icon="['fas', 'xmark']"
                                size="1x"
                            />
                        </b-button>
                    </template>

                    <div class="row align-items-center mb-2">
                        <div class="col-auto ms-auto">
                            <b-button variant="primary" :disabled="syncing" @click="syncNow">
                                <b-spinner v-if="syncing" small class="me-1" />
                                <font-awesome-icon v-else :icon="['fas', 'arrows-rotate']" class="me-1" />
                                {{ $t('activedirectory.sync_now') }}
                            </b-button>
                        </div>
                    </div>

                    <Alert v-if="errored" :message="errormsg" variant="danger" />

                    <div v-if="loading" class="ocs-loader">
                        <Loader />
                    </div>

                    <Datatable
                        v-else
                        id="activedirectory-reports-datatable"
                        :rowdata="rowdata"
                        :rowheader="rowheader"
                        :isbusy="isbusy"
                        title="activedirectory/reports"
                        translationkey="activedirectory."
                        :badgecells="['status']"
                        :candelete="false"
                        :candeletemultiple="false"
                        :canedit="false"
                        sortby="started_at"
                        sortdesc="true"
                        @reload-datatable="fetchReports"
                    />
                </b-modal>
            </div>
        `,
	}
}
