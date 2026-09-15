export async function createComponent(api) {
	const Datatable = api.getComponent("Datatable");
	const Alert = api.getComponent("Alert");
	const Loader = api.getComponent("Loader");
	const ProxmoxModalComp = await api.importModule(
		"/extensions/proxmoxapi/components/ProxmoxModal.js",
	);
	const ProxmoxModal = ProxmoxModalComp.createComponent(api);

	return {
		name: "ProxmoxPanel",
		components: {
			Datatable,
			Alert,
			Loader,
			ProxmoxModal,
		},

		data() {
			return {
				loading: false,
				isbusy: false,
				rowdata: [],
				rowheader: [
					"name",
					"description",
					"ip_address",
					"port",
					"node_names",
					"username",
					"request_delay",
					"is_active",
					"actions",
				],
				errored: false,
				errormsg: null,
				deletingId: null,
				deleteerror: false,
				deleteerrormsg: null,
				canview: false,
				canadd: false,
				canedit: false,
				candelete: false,
			};
		},

		methods: {
			checkPermissions() {
				const rawPermissions = localStorage.getItem("permissions");
				const permissions = rawPermissions ? rawPermissions.split(",") : [];

				if (permissions.includes("proxmoxapi_view_proxmoxserver")) {
					this.canview = true;
					this.canadd = permissions.includes("proxmoxapi_add_proxmoxserver");
					this.canedit = permissions.includes("proxmoxapi_change_proxmoxserver");
					this.candelete = permissions.includes("proxmoxapi_delete_proxmoxserver");
				} else {
					this.errormsg = this.$t("message.dont_have_right_to_see");
					this.errored = true;
				}
			},

			async load() {
				this.loading = true;
				try {
					await this.fetchServers();
				} finally {
					this.loading = false;
				}
			},

			async fetchServers() {
				this.isbusy = true;
				try {
					const response = await this.$api.generic.get("/proxmoxapi/servers/");
					const results = response?.results || response || [];
					this.rowdata = results.map((server) => ({
						...server,
						node_names: Array.isArray(server.node_names)
							? server.node_names.join(", ")
							: server.node_names,
					}));
				} catch (e) {
					this.errormsg = e.message;
					this.errored = true;
				} finally {
					this.isbusy = false;
				}
			},

			async reloadDatatable() {
				await this.fetchServers();
			},

			async deleteServer(serverId) {
				if (!confirm(this.$t("proxmoxapi.confirm_delete"))) {
					return;
				}

				this.deletingId = serverId;
				try {
					await this.$api.generic.delete(`/proxmoxapi/servers/${serverId}/`);
					await this.load();
				} catch (e) {
					this.deleteerrormsg = e.message;
					this.deleteerror = true;
				} finally {
					this.deletingId = null;
				}
			},

			getIsActiveLabel(isActive) {
				return isActive ? this.$t("generic.yes") : this.$t("generic.no");
			},
		},

		async mounted() {
			this.checkPermissions();
			if (!this.canview) return;
			await this.load();
		},

		template: `
            <div id="proxmoxapi">
                <div class="card">
                    <div class="card-body">
                        <div v-if="errored">
                            <Alert
                                :message="errormsg"
                                :cols="true"
                                variant="danger"
                            />
                        </div>

                        <div v-if="loading" class="ocs-loader">
                            <Loader />
                        </div>

                        <div v-else-if="canview">
                            <ProxmoxModal
                                v-if="canadd"
                                @reloadDatatable="reloadDatatable"
                            />

                            <Datatable
                                id="proxmox-datatable"
                                :rowdata="rowdata"
                                :rowheader="rowheader"
                                :isbusy="isbusy"
                                title="proxmoxapi/servers"
                                translationkey="proxmoxapi."
                                :candelete="candelete"
                                @reload-datatable="reloadDatatable"
                            >
                                <template v-slot:cell(firstActions)="slotProps">
                                    <router-link
                                        :to="{ path: '/inventory/proxmoxapi/assets', query: { server: slotProps.row.item.id } }"
                                        class="btn btn-ghost-info"
                                        :title="$t('proxmoxapi.view_assets')"
                                    >
                                        <font-awesome-icon :icon="['fas', 'desktop']" />
                                    </router-link>
                                    <ProxmoxModal
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
	};
}
