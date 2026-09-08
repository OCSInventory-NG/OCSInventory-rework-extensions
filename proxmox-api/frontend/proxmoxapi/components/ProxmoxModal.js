export function createComponent(api) {
	const Alert = api.getComponent("Alert");
	const Loader = api.getComponent("Loader");

	return {
		name: "ProxmoxModal",
		components: { Alert, Loader },

		props: {
			id: { type: [String, Number], default: null },
			serverId: { type: [String, Number], default: null },
			update: { type: Boolean, default: false },
		},

		data() {
			return {
				row: {
					name: null,
					description: null,
					ip_address: null,
					port: 8006,
					node_names: [""],
					username: null,
					token_id: null,
					token_secret: null,
					request_delay: 3000,
					is_active: true,
				},
				errormsg: null,
				errored: false,
				loading: true,
				loadingcreate: false,
				createerror: false,
				createerrormsg: null,
				createwithsuccess: false,
				servermodal: false,
				isEditMode: false,
			};
		},

		watch: {
			createwithsuccess: function () {
				setTimeout(() => {
					this.servermodal = false;
					this.createwithsuccess = false;
					this.resetForm();
					this.$emit("reloadDatatable");
				}, 500);
			},
		},

		mounted() {
			this.loading = false;
		},

		methods: {
			resetForm() {
				this.row = {
					name: null,
					description: null,
					ip_address: null,
					port: 8006,
					node_names: [""],
					username: null,
					token_id: null,
					token_secret: null,
					request_delay: 3000,
					is_active: true,
				};
				this.isEditMode = false;
			},

			addNodeField() {
				this.row.node_names.push("");
			},

			removeNodeField(index) {
				this.row.node_names.splice(index, 1);
				if (!this.row.node_names.length) {
					this.row.node_names.push("");
				}
			},

			loadData(serverId = null) {
				this.errormsg = null;
				this.errored = false;
				this.createerror = false;
				this.createerrormsg = null;

				if (this.update || serverId) {
					this.loadServerData(serverId);
					return;
				}

				this.servermodal = true;
				this.resetForm();
			},

			async loadServerData(serverId = null) {
				const id = serverId || this.serverId || this.id;
				if (!id) return;

				try {
					this.loading = true;
					const { data } = await api.http.get(
						`/proxmoxapi/servers/${id}/`,
					);
					this.row = {
						...data,
						node_names: Array.isArray(data.node_names) && data.node_names.length
							? data.node_names
							: [""],
					};
					this.isEditMode = true;
					this.servermodal = true;
				} catch (e) {
					this.errormsg = e.response?.data?.error
						? e.response.data.error
						: e.message;
					this.errored = true;
				} finally {
					this.loading = false;
				}
			},

			onSubmit(event) {
				event.preventDefault();
				this.loadingcreate = true;

				const url = this.isEditMode
					? `/proxmoxapi/servers/${this.row.id}/`
					: "/proxmoxapi/servers/";
				const method = this.isEditMode ? "put" : "post";

				const payload = {
					...this.row,
					node_names: this.row.node_names
						.map((name) => name.trim())
						.filter((name) => name.length > 0),
				};

				api.http[method](url, payload)
					.then(() => {
						this.createwithsuccess = true;
						this.createerrormsg = null;
						this.createerror = false;
					})
					.catch((e) => {
						this.createerrormsg = e.response?.data?.error
							? e.response.data.error
							: e.message;
						this.createerror = true;
						this.createwithsuccess = false;
					})
					.finally(() => {
						this.loadingcreate = false;
					});
			},
		},

		template: `
            <div id="proxmox-modal">
                <div v-if="!update" class="page-header d-print-none">
                    <div class="row">
                        <div class="col-auto ms-auto">
                            <button
                                type="button"
                                class="btn btn-primary d-sm-inline-block btn-modal"
                                :title="$t('proxmoxapi.add_server')"
                                @click="loadData()"
                            >
                                <font-awesome-icon :icon="['fas', 'plus']" />
                                {{ $t('proxmoxapi.add_server') }}
                            </button>
                        </div>
                    </div>
                </div>
                <div v-else>
                    <button
                        type="button"
                        :title="$t('proxmoxapi.edit_server')"
                        class="btn btn-ghost-dark"
                        @click="loadData(id)"
                    >
                        <font-awesome-icon :icon="['fas', 'pencil']" />
                    </button>
                </div>

                <div v-if="servermodal" class="modal-backdrop fade show"></div>
                <div v-if="servermodal" class="modal d-block" tabindex="-1" role="dialog">
                    <div class="modal-dialog modal-lg modal-dialog-centered" role="document">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">
                                    {{ isEditMode ? $t('proxmoxapi.edit_server') : $t('proxmoxapi.add_server') }}
                                    <span
                                        v-if="loadingcreate"
                                        class="spinner-border spinner-border-sm ms-2"
                                        role="status"
                                        aria-hidden="true"
                                    ></span>
                                    <font-awesome-icon
                                        v-if="createwithsuccess"
                                        :icon="['fas', 'check']"
                                        color="green"
                                        class="ms-2"
                                    />
                                    <font-awesome-icon
                                        v-if="createerror"
                                        :icon="['fas', 'xmark']"
                                        color="red"
                                        class="ms-2"
                                    />
                                </h5>
                                <button
                                    type="button"
                                    class="btn-close"
                                    aria-label="Close"
                                    @click="servermodal = false"
                                ></button>
                            </div>
                            <div class="modal-body">
                                <Alert
                                    v-if="createerror || errored"
                                    :message="createerror ? createerrormsg : errormsg"
                                    variant="danger"
                                />

                                <form @submit="onSubmit">
                                    <div class="row">
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label" for="name">{{ $t('proxmoxapi.server_name') }}</label>
                                            <input
                                                id="name"
                                                class="form-control"
                                                v-model="row.name"
                                                type="text"
                                                required
                                            />
                                        </div>
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label" for="description">
                                                {{ $t('proxmoxapi.description') }}
                                            </label>
                                            <input
                                                id="description"
                                                class="form-control"
                                                v-model="row.description"
                                                type="text"
                                            />
                                        </div>
                                    </div>

                                    <div class="row">
                                        <div class="col-md-8 mb-3">
                                            <label
                                                class="form-label"
                                                for="ip_address"
                                            >
                                                {{ $t('proxmoxapi.ip_address') }}
                                            </label>
                                            <input
                                                id="ip_address"
                                                class="form-control"
                                                v-model="row.ip_address"
                                                type="text"
                                                placeholder="192.168.1.100 or hostname.com"
                                                required
                                            />
                                        </div>
                                        <div class="col-md-4 mb-3">
                                            <label class="form-label" for="port">{{ $t('proxmoxapi.port') }}</label>
                                            <input
                                                id="port"
                                                class="form-control"
                                                v-model.number="row.port"
                                                type="number"
                                                required
                                            />
                                        </div>
                                    </div>

                                    <div class="row">
                                        <div class="col mb-3">
                                            <label class="form-label">{{ $t('proxmoxapi.node_names') }}</label>
                                            <div
                                                v-for="(node, index) in row.node_names"
                                                :key="index"
                                                class="d-flex align-items-center gap-2 mb-2"
                                            >
                                                <input
                                                    class="form-control"
                                                    style="height: 2.25rem;"
                                                    v-model="row.node_names[index]"
                                                    type="text"
                                                    :placeholder="$t('proxmoxapi.node_names')"
                                                    required
                                                />
                                                <button
                                                    v-if="index === row.node_names.length - 1"
                                                    type="button"
                                                    class="btn btn-outline-secondary"
                                                    style="height: 2.25rem; padding-top: 0; padding-bottom: 0;"
                                                    :title="$t('proxmoxapi.add_node')"
                                                    @click="addNodeField"
                                                >
                                                    <font-awesome-icon :icon="['fas', 'plus']" />
                                                </button>
                                                <button
                                                    v-if="row.node_names.length > 1"
                                                    type="button"
                                                    class="btn btn-outline-danger"
                                                    style="height: 2.25rem; padding-top: 0; padding-bottom: 0;"
                                                    :title="$t('proxmoxapi.remove_node')"
                                                    @click="removeNodeField(index)"
                                                >
                                                    <font-awesome-icon :icon="['fas', 'xmark']" />
                                                </button>
                                            </div>
                                        </div>
                                    </div>

                                    <div class="row">
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label" for="username">{{ $t('proxmoxapi.username') }}</label>
                                            <input
                                                id="username"
                                                class="form-control"
                                                v-model="row.username"
                                                type="text"
                                                placeholder="user@pam"
                                                required
                                            />
                                        </div>
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label" for="token_id">{{ $t('proxmoxapi.token_id') }}</label>
                                            <input
                                                id="token_id"
                                                class="form-control"
                                                v-model="row.token_id"
                                                type="text"
                                                placeholder="tokenid"
                                                required
                                            />
                                        </div>
                                    </div>

                                    <div class="row">
                                        <div class="col mb-3">
                                            <label
                                                class="form-label"
                                                for="token_secret"
                                            >
                                                {{ $t('proxmoxapi.token_secret') }}
                                            </label>
                                            <input
                                                id="token_secret"
                                                class="form-control"
                                                v-model="row.token_secret"
                                                type="password"
                                                required
                                            />
                                        </div>
                                    </div>

                                    <div class="row">
                                        <div class="col-md-6 mb-3">
                                            <label class="form-label" for="request_delay">
                                                {{ $t('proxmoxapi.request_delay') }}
                                            </label>
                                            <input
                                                id="request_delay"
                                                class="form-control"
                                                v-model.number="row.request_delay"
                                                type="number"
                                                min="0"
                                            />
                                        </div>
                                    </div>

                                    <div class="row mb-3">
                                        <div class="col">
                                            <label class="form-label">
                                                {{ $t('proxmoxapi.is_active') }}
                                            </label>
                                            <div>
                                                <label class="form-check form-switch">
                                                    <input
                                                        id="is_active"
                                                        class="form-check-input"
                                                        type="checkbox"
                                                        v-model="row.is_active"
                                                    />
                                                </label>
                                            </div>
                                        </div>
                                    </div>

                                    <div class="d-flex justify-content-center gap-2">
                                        <button type="submit" class="btn btn-success">
                                            {{ isEditMode ? $t('generic.save') : $t('generic.add') }}
                                        </button>
                                    </div>
                                </form>

                                <div v-if="loading" class="ocs-loader mt-3">
                                    <Loader />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `,
	};
}
