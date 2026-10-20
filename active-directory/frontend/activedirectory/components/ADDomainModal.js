export function createComponent(api) {
	const Alert = api.getComponent("Alert")
	const Loader = api.getComponent("Loader")

	const emptyRow = () => ({
		name: "",
		server: "",
		port: 636,
		security: "ldaps",
		verify_certificate: true,
		bind_dn: "",
		bind_password: "",
		base_dn: "",
		assigned_user_attribute: "managedBy",
		is_active: true,
	})

	return {
		name: "ADDomainModal",
		components: { Alert, Loader },

		props: {
			id: { type: [String, Number], default: null },
			update: { type: Boolean, default: false },
		},

		data() {
			return {
				row: emptyRow(),
				hasPassword: false,
				errormsg: null,
				errored: false,
				loading: true,
				loadingcreate: false,
				createerror: false,
				createerrormsg: null,
				createwithsuccess: false,
				domainmodal: false,
				isEditMode: false,
				testing: false,
				testResult: null,
			}
		},

		computed: {
			securityOptions() {
				return ["ldaps", "starttls", "none"].map((value) => ({
					value,
					text: this.$t("activedirectory.security_" + value),
				}))
			},
		},

		watch: {
			createwithsuccess: function () {
				if (!this.createwithsuccess) return
				setTimeout(() => {
					this.domainmodal = false
					this.createwithsuccess = false
					this.resetForm()
					this.$emit("reloadDatatable")
				}, 500)
			},
		},

		mounted() {
			this.loading = false
		},

		methods: {
			resetForm() {
				this.row = emptyRow()
				this.hasPassword = false
				this.isEditMode = false
				this.testResult = null
			},

			loadData(domainId = null) {
				this.errormsg = null
				this.errored = false
				this.createerror = false
				this.createerrormsg = null
				this.testResult = null

				if (this.update || domainId) {
					this.loadDomainData(domainId)
					return
				}

				this.resetForm()
				this.domainmodal = true
			},

			async loadDomainData(domainId = null) {
				const id = domainId || this.id
				if (!id) return

				try {
					this.loading = true
					const { data } = await api.http.get(`/activedirectory/domains/${id}/`)
					this.hasPassword = !!data.has_password
					this.row = { ...data, bind_password: "" }
					this.isEditMode = true
					this.domainmodal = true
				} catch (e) {
					this.errormsg = e.response?.data?.error || e.message
					this.errored = true
				} finally {
					this.loading = false
				}
			},

			async testConnection() {
				const id = this.isEditMode ? (this.row.id || this.id) : null
				this.testing = true
				this.testResult = null
				try {
					if (id) {
						const { data } = await api.http.post(`/activedirectory/domains/${id}/test/`)
						this.testResult = data
					} else {
						this.testResult = { ok: false, error: this.$t("activedirectory.save_before_test") }
					}
				} catch (e) {
					this.testResult = { ok: false, error: e.response?.data?.error || e.message }
				} finally {
					this.testing = false
				}
			},

			onSubmit(event) {
				event.preventDefault()
				this.loadingcreate = true

				const url = this.isEditMode
					? `/activedirectory/domains/${this.row.id}/`
					: "/activedirectory/domains/"
				const method = this.isEditMode ? "patch" : "post"

				const payload = { ...this.row }
				if (this.isEditMode && !payload.bind_password) {
					delete payload.bind_password
				}

				api.http[method](url, payload)
					.then(() => {
						this.createwithsuccess = true
						this.createerrormsg = null
						this.createerror = false
					})
					.catch((e) => {
						this.createerrormsg = e.response?.data?.error
							|| (e.response?.data && JSON.stringify(e.response.data))
							|| e.message
						this.createerror = true
						this.createwithsuccess = false
					})
					.finally(() => {
						this.loadingcreate = false
					})
			},
		},

		template: `
            <div id="activedirectory-domain-modal">
                <div v-if="!update" class="page-header d-print-none">
                    <div class="row">
                        <div class="col-auto ms-auto">
                            <button
                                type="button"
                                class="btn btn-primary d-sm-inline-block btn-modal"
                                :title="$t('activedirectory.add_domain')"
                                @click="loadData()"
                            >
                                <font-awesome-icon :icon="['fas', 'plus']" />
                                {{ $t('activedirectory.add_domain') }}
                            </button>
                        </div>
                    </div>
                </div>
                <div v-else>
                    <button
                        type="button"
                        :title="$t('activedirectory.edit_domain')"
                        class="btn btn-ghost-dark"
                        @click="loadData(id)"
                    >
                        <font-awesome-icon :icon="['fas', 'pencil']" />
                    </button>
                </div>

                <b-modal
                    v-model="domainmodal"
                    :title="isEditMode ? $t('activedirectory.edit_domain_title', { name: row.name }) : $t('activedirectory.add_domain')"
                    hide-footer
                    modal-class="custom-modal"
                    size="lg"
                >
                    <template #header="{ close }">
                        <h5 class="modal-title">
                            {{ isEditMode ? $t('activedirectory.edit_domain_title', { name: row.name }) : $t('activedirectory.add_domain') }}
                            <b-spinner
                                v-if="loadingcreate"
                                variant="success"
                            />
                            <font-awesome-icon
                                v-if="createwithsuccess"
                                :icon="['fas', 'check']"
                                color="green"
                            />
                            <font-awesome-icon
                                v-if="createerror"
                                :icon="['fas', 'xmark']"
                                color="red"
                            />
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

                    <Alert
                        v-if="createerror || errored"
                        :message="createerror ? createerrormsg : errormsg"
                        variant="danger"
                    />

                    <form @submit="onSubmit">
                        <div class="row">
                            <div class="col-md-8 mb-3">
                                <label class="form-label" for="ad-name">{{ $t('activedirectory.domain_name_label') }}</label>
                                <input id="ad-name" class="form-control" v-model="row.name" type="text" required />
                            </div>
                            <div class="col-md-4 mb-3">
                                <label class="form-label d-block">{{ $t('activedirectory.is_active') }}</label>
                                <label class="form-check form-switch">
                                    <input id="ad-is-active" class="form-check-input" type="checkbox" v-model="row.is_active" />
                                </label>
                            </div>
                        </div>

                        <div class="row">
                            <div class="col-md-8 mb-3">
                                <label class="form-label" for="ad-server">{{ $t('activedirectory.server') }}</label>
                                <input id="ad-server" class="form-control" v-model="row.server" type="text" required />
                            </div>
                            <div class="col-md-4 mb-3">
                                <label class="form-label" for="ad-port">{{ $t('activedirectory.port') }}</label>
                                <input id="ad-port" class="form-control" v-model.number="row.port" type="number" min="1" max="65535" required />
                            </div>
                        </div>

                        <div class="row">
                            <div class="col-md-8 mb-3">
                                <label class="form-label" for="ad-security">{{ $t('activedirectory.security') }}</label>
                                <v-select
                                    id="ad-security"
                                    v-model="row.security"
                                    :options="securityOptions"
                                    :reduce="opt => opt.value"
                                    :clearable="false"
                                    label="text"
                                />
                            </div>
                            <div class="col-md-4 mb-3 d-flex align-items-end">
                                <label class="form-check">
                                    <input class="form-check-input" type="checkbox" v-model="row.verify_certificate" />
                                    <span class="form-check-label">{{ $t('activedirectory.verify_certificate') }}</span>
                                </label>
                            </div>
                        </div>

                        <div class="row">
                            <div class="col-md-6 mb-3">
                                <label class="form-label" for="ad-bind-dn">{{ $t('activedirectory.bind_dn') }}</label>
                                <input id="ad-bind-dn" class="form-control" v-model="row.bind_dn" type="text" required />
                            </div>
                            <div class="col-md-6 mb-3">
                                <label class="form-label" for="ad-bind-password">{{ $t('activedirectory.bind_password') }}</label>
                                <input
                                    id="ad-bind-password"
                                    class="form-control"
                                    v-model="row.bind_password"
                                    type="password"
                                    :placeholder="isEditMode && hasPassword ? $t('activedirectory.password_unchanged') : ''"
                                    :required="!isEditMode"
                                />
                                <small v-if="isEditMode" class="form-hint">{{ $t('activedirectory.password_hint') }}</small>
                            </div>
                        </div>

                        <div class="row">
                            <div class="col-md-8 mb-3">
                                <label class="form-label" for="ad-base-dn">{{ $t('activedirectory.base_dn') }}</label>
                                <input id="ad-base-dn" class="form-control" v-model="row.base_dn" type="text" required />
                            </div>
                            <div class="col-md-4 mb-3">
                                <label class="form-label" for="ad-attribute">{{ $t('activedirectory.assigned_user_attribute') }}</label>
                                <input id="ad-attribute" class="form-control" v-model="row.assigned_user_attribute" type="text" required />
                                <small class="form-hint">{{ $t('activedirectory.assigned_user_attribute_hint') }}</small>
                            </div>
                        </div>

                        <Alert
                            v-if="testResult"
                            :message="testResult.ok
                                ? $t('activedirectory.test_success', { server: testResult.server })
                                : testResult.error"
                            :variant="testResult.ok ? 'success' : 'danger'"
                        />

                        <div class="d-flex justify-content-center gap-2">
                            <b-button
                                v-if="isEditMode"
                                variant="secondary"
                                :disabled="testing"
                                type="button"
                                @click="testConnection"
                            >
                                <b-spinner v-if="testing" small />
                                {{ $t('activedirectory.test_connection') }}
                            </b-button>
                            <button type="submit" class="btn btn-success">
                                {{ isEditMode ? $t('generic.save') : $t('generic.add') }}
                            </button>
                        </div>
                    </form>

                    <div v-if="loading" class="ocs-loader mt-3">
                        <Loader />
                    </div>
                </b-modal>
            </div>
        `,
	}
}
