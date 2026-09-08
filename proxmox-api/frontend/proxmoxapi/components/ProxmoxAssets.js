export async function createComponent(api) {
	const Datatable = api.getComponent("Datatable");
	const Alert = api.getComponent("Alert");
	const Loader = api.getComponent("Loader");
	const PageHeader = api.getComponent("PageHeader");

	return {
		name: "ProxmoxAssets",
		components: { Datatable, Alert, Loader, PageHeader },

		data() {
			return {
				loading: false,
				isbusy: false,
				servers: [],
				activeServerId: "all",
				rowdata: [],
				errored: false,
				errormsg: null,
				canview: false,
				candelete: false,
			};
		},

		computed: {
			today() {
				const d = new Date();
				const mm = String(d.getMonth() + 1).padStart(2, "0");
				const dd = String(d.getDate()).padStart(2, "0");
				return `${d.getFullYear()}-${mm}-${dd}`;
			},
			requestedServerId() {
				const raw = this.$route.query.server;
				return raw ? Number(raw) : null;
			},
			pageTitle() {
				return this.$t("proxmoxapi.global_inventory_title");
			},
			activeTabIndex: {
				get() {
					if (this.activeServerId === "all") return 0;
					const idx = this.servers.findIndex((s) => s.id === this.activeServerId);
					return idx >= 0 ? idx + 1 : 0;
				},
				set(index) {
					this.activeServerId = index === 0 ? "all" : (this.servers[index - 1]?.id ?? "all");
				},
			},
		},

		methods: {
			checkPermissions() {
				const rawPermissions = localStorage.getItem("permissions");
				const permissions = rawPermissions ? rawPermissions.split(",") : [];

				if (permissions.includes("proxmoxapi_view_proxmoxasset")) {
					this.canview = true;
					this.candelete = permissions.includes("proxmoxapi_delete_proxmoxasset");
				} else {
					this.errormsg = this.$t("message.dont_have_right_to_see");
					this.errored = true;
				}
			},

			rowsForServer(serverId) {
				if (serverId === "all") return this.rowdata;
				return this.rowdata.filter((r) => r.server === serverId);
			},
			rowheaderForServer(serverId) {
				if (serverId === "all") {
					return ["server_name", "name", "vmid", "resource_type", "status", "last_update"];
				}
				return ["name", "vmid", "resource_type", "status", "last_update"];
			},
			statsForServer(serverId) {
				const rows = this.rowsForServer(serverId);
				const vms = rows.filter((r) => r.resource_type === "qemu");
				const containers = rows.filter((r) => r.resource_type === "lxc");
				const vmsContacted = vms.filter((r) => r.last_update?.startsWith(this.today)).length;
				const containersContacted = containers.filter((r) => r.last_update?.startsWith(this.today)).length;
				return {
					total: vms.length + containers.length,
					totalContacted: vmsContacted + containersContacted,
					vms: vms.length,
					vmsContacted,
					containers: containers.length,
					containersContacted,
					running: rows.filter((r) => r.status === "running").length,
					stopped: rows.filter((r) => r.status === "stopped").length,
				};
			},

			async load() {
				this.loading = true;
				try {
					await this.fetchAssets();

					const requested = this.requestedServerId;
					if (requested !== null && this.servers.some((server) => server.id === requested)) {
						this.activeServerId = requested;
					}
				} finally {
					this.loading = false;
				}
			},

			async fetchAssets() {
				this.isbusy = true;
				this.errored = false;
				this.errormsg = null;
				try {
					const serversResponse = await this.$api.generic.get("/proxmoxapi/servers/");
					const servers = serversResponse?.results ?? serversResponse ?? [];
					this.servers = servers;

					if (
						this.activeServerId !== "all"
						&& !servers.some((server) => server.id === this.activeServerId)
					) {
						this.activeServerId = "all";
					}

					const assetsByServer = await Promise.all(
						servers.map(async (server) => {
							try {
								const response = await this.$api.generic.get(
									`/proxmoxapi/servers/${server.id}/assets/`,
								);
								const results = response?.results ?? response ?? [];
								return results.map((item) => ({
									...item,
									id: item.asset,
									name: item.asset_name,
									server_name: server.name,
								}));
							} catch {
								return [];
							}
						}),
					);
					this.rowdata = assetsByServer.flat();
				} catch (e) {
					this.errormsg = e.message;
					this.errored = true;
				} finally {
					this.isbusy = false;
				}
			},

			async reloadDatatable() {
				await this.fetchAssets();
			},

		},

		beforeRouteUpdate(to) {
			const raw = to.query.server;
			if (!raw) {
				this.activeServerId = "all";
				return;
			}
			const requested = Number(raw);
			if (this.servers.some((server) => server.id === requested)) {
				this.activeServerId = requested;
			}
		},

		async mounted() {
			this.checkPermissions();
			if (!this.canview) return;
			await this.load();
		},

		template: `
			<div id="proxmox-assets" class="container-xl">
				<PageHeader :page-title="pageTitle" />
				<div class="page-body">
					<div class="card">
						<div class="card-body">
							<Alert
								v-if="errored"
								:message="errormsg"
								:cols="true"
								variant="danger"
							/>

							<div v-if="loading" class="ocs-loader">
								<Loader />
							</div>

							<b-tabs
								v-else-if="canview"
								v-model="activeTabIndex"
								vertical
								pills
								card
								content-class="col-10 sticky-tabs"
							>
								<b-tab
									:title="$t('proxmoxapi.all_servers')"
									title-item-class="ocs-menu-tab"
								>
									<div class="row row-deck row-cards mb-4 mt-3">
										<div class="col-sm-6 col-lg">
											<div class="card h-100">
												<div class="card-body">
													<div class="subheader">
														{{ $t('proxmoxapi.stat_total') }}
													</div>
													<div class="h1 mb-3">{{ statsForServer('all').total }}</div>
													<div class="d-flex mb-2">
														<div>{{ $t('dashboard.contacted') }}</div>
														<div class="ms-auto">
															<span class="badge bg-purple">
																{{ statsForServer('all').totalContacted }}
															</span>
														</div>
													</div>
												</div>
											</div>
										</div>
										<div class="col-sm-6 col-lg">
											<div class="card h-100">
												<div class="card-body">
													<div class="subheader">
														{{ $t('proxmoxapi.stat_vms') }}
													</div>
													<div class="h1 mb-3">{{ statsForServer('all').vms }}</div>
													<div class="d-flex mb-2">
														<div>{{ $t('dashboard.contacted') }}</div>
														<div class="ms-auto">
															<span class="badge bg-purple">
																{{ statsForServer('all').vmsContacted }}
															</span>
														</div>
													</div>
												</div>
											</div>
										</div>
										<div class="col-sm-6 col-lg">
											<div class="card h-100">
												<div class="card-body">
													<div class="subheader">
														{{ $t('proxmoxapi.stat_containers') }}
													</div>
													<div class="h1 mb-3">{{ statsForServer('all').containers }}</div>
													<div class="d-flex mb-2">
														<div>{{ $t('dashboard.contacted') }}</div>
														<div class="ms-auto">
															<span class="badge bg-purple">
																{{ statsForServer('all').containersContacted }}
															</span>
														</div>
													</div>
												</div>
											</div>
										</div>
										<div class="col-sm-6 col-lg">
											<div class="card h-100">
												<div class="card-body">
													<div class="subheader">
														{{ $t('proxmoxapi.stat_running') }}
													</div>
													<div class="h1 mb-3">{{ statsForServer('all').running }}</div>
												</div>
											</div>
										</div>
										<div class="col-sm-6 col-lg">
											<div class="card h-100">
												<div class="card-body">
													<div class="subheader">
														{{ $t('proxmoxapi.stat_stopped') }}
													</div>
													<div class="h1 mb-3">{{ statsForServer('all').stopped }}</div>
												</div>
											</div>
										</div>
									</div>

									<Datatable
										id="proxmox-assets-datatable-all"
										:rowdata="rowsForServer('all')"
										:rowheader="rowheaderForServer('all')"
										:isbusy="isbusy"
										title="asset/bases"
										translationkey="proxmoxapi.asset_"
										:canaccessdetails="true"
										:candelete="candelete"
										sortby="last_update"
										sortdesc="true"
										@reload-datatable="reloadDatatable"
									/>
								</b-tab>

								<b-tab
									v-for="serverItem in servers"
									:key="serverItem.id"
									:title="serverItem.name"
									title-item-class="ocs-menu-tab"
								>
									<div class="row row-deck row-cards mb-4 mt-3">
										<div class="col-sm-6 col-lg">
											<div class="card h-100">
												<div class="card-body">
													<div class="subheader">
														{{ $t('proxmoxapi.stat_total') }}
													</div>
													<div class="h1 mb-3">{{ statsForServer(serverItem.id).total }}</div>
													<div class="d-flex mb-2">
														<div>{{ $t('dashboard.contacted') }}</div>
														<div class="ms-auto">
															<span class="badge bg-purple">
																{{ statsForServer(serverItem.id).totalContacted }}
															</span>
														</div>
													</div>
												</div>
											</div>
										</div>
										<div class="col-sm-6 col-lg">
											<div class="card h-100">
												<div class="card-body">
													<div class="subheader">
														{{ $t('proxmoxapi.stat_vms') }}
													</div>
													<div class="h1 mb-3">{{ statsForServer(serverItem.id).vms }}</div>
													<div class="d-flex mb-2">
														<div>{{ $t('dashboard.contacted') }}</div>
														<div class="ms-auto">
															<span class="badge bg-purple">
																{{ statsForServer(serverItem.id).vmsContacted }}
															</span>
														</div>
													</div>
												</div>
											</div>
										</div>
										<div class="col-sm-6 col-lg">
											<div class="card h-100">
												<div class="card-body">
													<div class="subheader">
														{{ $t('proxmoxapi.stat_containers') }}
													</div>
													<div class="h1 mb-3">{{ statsForServer(serverItem.id).containers }}</div>
													<div class="d-flex mb-2">
														<div>{{ $t('dashboard.contacted') }}</div>
														<div class="ms-auto">
															<span class="badge bg-purple">
																{{ statsForServer(serverItem.id).containersContacted }}
															</span>
														</div>
													</div>
												</div>
											</div>
										</div>
										<div class="col-sm-6 col-lg">
											<div class="card h-100">
												<div class="card-body">
													<div class="subheader">
														{{ $t('proxmoxapi.stat_running') }}
													</div>
													<div class="h1 mb-3">{{ statsForServer(serverItem.id).running }}</div>
												</div>
											</div>
										</div>
										<div class="col-sm-6 col-lg">
											<div class="card h-100">
												<div class="card-body">
													<div class="subheader">
														{{ $t('proxmoxapi.stat_stopped') }}
													</div>
													<div class="h1 mb-3">{{ statsForServer(serverItem.id).stopped }}</div>
												</div>
											</div>
										</div>
									</div>

									<Datatable
										:id="'proxmox-assets-datatable-' + serverItem.id"
										:rowdata="rowsForServer(serverItem.id)"
										:rowheader="rowheaderForServer(serverItem.id)"
										:isbusy="isbusy"
										title="asset/bases"
										translationkey="proxmoxapi.asset_"
										:canaccessdetails="true"
										:candelete="candelete"
										sortby="last_update"
										sortdesc="true"
										@reload-datatable="reloadDatatable"
									/>
								</b-tab>
							</b-tabs>
						</div>
					</div>
				</div>
			</div>
		`,
	};
}
