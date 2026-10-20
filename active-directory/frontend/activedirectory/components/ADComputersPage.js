export async function createComponent(api) {
	const PageHeader = api.getComponent("PageHeader")
	const Datatable = api.getComponent("Datatable")
	const Alert = api.getComponent("Alert")
	const Loader = api.getComponent("Loader")
	const ADLinkModalComp = await api.importModule("/extensions/activedirectory/components/ADLinkModal.js")
	const ADLinkModal = ADLinkModalComp.createComponent(api)

	const LINK_MODE_VARIANTS = { auto: "info", manual: "purple" }
	const MATCH_VARIANTS = { unlinked: "secondary", ambiguous: "warning" }

	// Shared stats + filters + table block, rendered once per tab (one per
	// domain plus "all") so each b-tab carries real content instead of an
	// empty pane - b-tabs still reserves the content area otherwise.
	const ADComputersContent = {
		name: "ADComputersContent",
		components: { Datatable, ADLinkModal },
		props: {
			domainCount: { type: Number, required: true },
			stats: { type: Object, required: true },
			rowdata: { type: Array, required: true },
			rowheader: { type: Array, required: true },
			isbusy: { type: Boolean, required: true },
			canchange: { type: Boolean, required: true },
			candelete: { type: Boolean, required: true },
			statusFilter: { type: String, required: true },
		},
		emits: ["update:statusFilter", "reload-datatable", "unlink"],
		template: `
			<div>
				<div class="row row-deck row-cards mb-4 mt-3">
					<div class="col-sm-6 col-lg">
						<div class="card h-100">
							<div class="card-body">
								<div class="subheader">{{ $t('activedirectory.stat_total') }}</div>
								<div class="h1 mb-1">{{ stats.total }}</div>
								<div class="text-secondary">{{ $t('activedirectory.stat_total_sub', { count: domainCount }) }}</div>
							</div>
						</div>
					</div>
					<div class="col-sm-6 col-lg">
						<div class="card h-100">
							<div class="card-body">
								<div class="subheader">{{ $t('activedirectory.stat_linked') }}</div>
								<div class="h1 mb-1 text-success">{{ stats.linked }}</div>
								<div class="text-secondary">{{ stats.linkedPct }} %</div>
							</div>
						</div>
					</div>
					<div class="col-sm-6 col-lg">
						<div class="card h-100">
							<div class="card-body">
								<div class="subheader">{{ $t('activedirectory.stat_unlinked') }}</div>
								<div class="h1 mb-1">{{ stats.unlinked }}</div>
								<div class="text-secondary">{{ $t('activedirectory.stat_unlinked_sub') }}</div>
							</div>
						</div>
					</div>
					<div class="col-sm-6 col-lg">
						<div class="card h-100">
							<div class="card-body">
								<div class="subheader">{{ $t('activedirectory.stat_ambiguous') }}</div>
								<div class="h1 mb-1 text-warning">{{ stats.ambiguous }}</div>
								<div class="text-secondary">{{ $t('activedirectory.stat_ambiguous_sub') }}</div>
							</div>
						</div>
					</div>
					<div class="col-sm-6 col-lg">
						<div class="card h-100">
							<div class="card-body">
								<div class="subheader">{{ $t('activedirectory.stat_removed') }}</div>
								<div class="h1 mb-1 text-danger">{{ stats.removed }}</div>
								<div class="text-secondary">{{ $t('activedirectory.stat_removed_sub') }}</div>
							</div>
						</div>
					</div>
				</div>

				<div class="row mb-3 g-2 align-items-center">
					<div class="col-md-3">
						<select
							:value="statusFilter"
							class="form-select"
							@change="$emit('update:statusFilter', $event.target.value)"
						>
							<option value="all">{{ $t('activedirectory.status_all') }}</option>
							<option value="active">{{ $t('activedirectory.status_active') }}</option>
							<option value="inactive">{{ $t('activedirectory.status_inactive') }}</option>
						</select>
					</div>
				</div>

				<Datatable
					id="activedirectory-computers-datatable"
					:rowdata="rowdata"
					:rowheader="rowheader"
					:isbusy="isbusy"
					title="activedirectory/computers"
					translationkey="activedirectory."
					:badgecells="['enabled_label', 'match_status_label', 'in_directory_label']"
					:candelete="candelete"
					:candeletemultiple="false"
					:canedit="false"
					:hascustomactions="canchange"
					sortby="name"
					@reload-datatable="$emit('reload-datatable')"
				>
					<template v-slot:cell(firstActions)="slotProps">
						<template v-if="canchange">
							<ADLinkModal
								v-if="slotProps.row.item.match_status !== 'linked'"
								:computer-id="slotProps.row.item.id"
								:computer-name="slotProps.row.item.name"
								@reload-datatable="$emit('reload-datatable')"
							/>
							<button
								v-else
								type="button"
								class="btn btn-ghost-dark"
								:title="$t('activedirectory.unlink')"
								@click="$emit('unlink', slotProps.row.item.id)"
							>
								<font-awesome-icon :icon="['fas', 'link-slash']" />
							</button>
						</template>
					</template>
				</Datatable>
			</div>
		`,
	}

	return {
		name: "ADComputersPage",
		components: { PageHeader, Datatable, Alert, Loader, ADLinkModal, ADComputersContent },

		data() {
			return {
				loading: false,
				isbusy: false,
				domains: [],
				computers: [],
				activeDomainId: "all",
				statusFilter: "all",
				rowheader: [
					"domain_name",
					"name",
					"in_directory_label",
					"ou",
					"assigned_user_label",
					"enabled_label",
					"asset_name",
					"match_status_label",
					"actions",
				],
				errored: false,
				errormsg: null,
				canview: false,
				canchange: false,
				candelete: false,
			}
		},

		computed: {
			activeTabIndex: {
				get() {
					if (this.activeDomainId === "all") return 0
					const idx = this.domains.findIndex((d) => d.id === this.activeDomainId)
					return idx >= 0 ? idx + 1 : 0
				},
				set(index) {
					this.activeDomainId = index === 0 ? "all" : (this.domains[index - 1]?.id ?? "all")
				},
			},

			filteredComputers() {
				let rows = this.computers
				if (this.activeDomainId !== "all") {
					rows = rows.filter((c) => c.domain === this.activeDomainId)
				}
				if (this.statusFilter === "active") {
					rows = rows.filter((c) => c.enabled)
				} else if (this.statusFilter === "inactive") {
					rows = rows.filter((c) => !c.enabled)
				}
				return rows
			},

			rowdata() {
				return this.filteredComputers.map((c) => {
					const cellLinks = {}
					if (c.asset && c.asset_name) {
						cellLinks.asset_name = { href: api.withBase(`inventory/asset/${c.asset}`), label: c.asset_name }
					}
					return {
						...c,
						ou: c.ou_path || c.ou || "-",
						in_directory_label: c.in_directory
							? this.$t("activedirectory.in_directory_present")
							: this.$t("activedirectory.in_directory_removed"),
						__in_directory_label_variant: c.in_directory ? "success" : "danger",
						assigned_user_label: c.assigned_user?.name || c.assigned_user?.login || "-",
						enabled_label: c.enabled ? this.$t("generic.yes") : this.$t("generic.no"),
						__enabled_label_variant: c.enabled ? "success" : "secondary",
						asset_name: c.asset_name || "-",
						__cellLinks: cellLinks,
						match_status_label: c.match_status === "linked"
							? this.$t(`activedirectory.link_mode_${c.link_mode || "auto"}`)
							: this.$t(`activedirectory.match_status_${c.match_status}`),
						__match_status_label_variant: c.match_status === "linked"
							? (LINK_MODE_VARIANTS[c.link_mode] || "info")
							: (MATCH_VARIANTS[c.match_status] || "secondary"),
					}
				})
			},

			stats() {
				const rows = this.activeDomainId === "all"
					? this.computers
					: this.computers.filter((c) => c.domain === this.activeDomainId)
				const inDirectory = rows.filter((c) => c.in_directory)
				const linked = inDirectory.filter((c) => c.match_status === "linked")
				const unlinked = inDirectory.filter((c) => c.match_status === "unlinked")
				const ambiguous = inDirectory.filter((c) => c.match_status === "ambiguous")
				const removed = rows.filter((c) => !c.in_directory)
				return {
					total: inDirectory.length,
					linked: linked.length,
					linkedPct: inDirectory.length ? ((linked.length / inDirectory.length) * 100).toFixed(1) : "0",
					unlinked: unlinked.length,
					ambiguous: ambiguous.length,
					removed: removed.length,
				}
			},
		},

		methods: {
			checkPermissions() {
				const rawPermissions = localStorage.getItem("permissions")
				const permissions = rawPermissions ? rawPermissions.split(",") : []

				if (permissions.includes("activedirectory_view_adcomputer")) {
					this.canview = true
					this.canchange = permissions.includes("activedirectory_change_adcomputer")
					this.candelete = permissions.includes("activedirectory_delete_adcomputer")
				} else {
					this.errormsg = this.$t("message.dont_have_right_to_see")
					this.errored = true
				}
			},

			async load() {
				this.loading = true
				try {
					await Promise.all([this.fetchDomains(), this.fetchComputers()])
				} finally {
					this.loading = false
				}
			},

			async fetchDomains() {
				const response = await this.$api.generic.get("/activedirectory/domains/")
				this.domains = response?.results ?? response ?? []
			},

			async fetchComputers() {
				this.isbusy = true
				this.errored = false
				this.errormsg = null
				try {
					const response = await this.$api.generic.get("/activedirectory/computers/", { limit: 2000 })
					this.computers = response?.results ?? response ?? []
				} catch (e) {
					this.errormsg = e.message
					this.errored = true
				} finally {
					this.isbusy = false
				}
			},

			async reloadDatatable() {
				await this.fetchComputers()
			},

			async unlinkComputer(computerId) {
				if (!confirm(this.$t("activedirectory.confirm_unlink"))) return
				try {
					await api.http.post(`/activedirectory/computers/${computerId}/unlink/`)
					await this.reloadDatatable()
				} catch (e) {
					this.errormsg = e.response?.data?.error || e.message
					this.errored = true
				}
			},
		},

		async mounted() {
			this.checkPermissions()
			if (!this.canview) return
			await this.load()
		},

		template: `
			<div id="activedirectory-computers" class="container-xl">
				<PageHeader :page-title="$t('activedirectory.computers_title')" />
				<div class="page-body">
					<Alert v-if="errored" :message="errormsg" :cols="true" variant="danger" />

					<div v-if="loading" class="ocs-loader">
						<Loader />
					</div>

					<div v-else-if="canview" class="card">
						<div class="card-body">
							<b-tabs
								v-model="activeTabIndex"
								vertical
								pills
								card
								content-class="col-10 sticky-tabs"
							>
								<b-tab :title="$t('activedirectory.all_domains')" title-item-class="ocs-menu-tab">
									<ADComputersContent
										:domain-count="domains.length"
										:stats="stats"
										:rowdata="rowdata"
										:rowheader="rowheader"
										:isbusy="isbusy"
										:canchange="canchange"
										:candelete="candelete"
										:status-filter="statusFilter"
										@update:statusFilter="statusFilter = $event"
										@reload-datatable="reloadDatatable"
										@unlink="unlinkComputer"
									/>
								</b-tab>
								<b-tab
									v-for="d in domains"
									:key="d.id"
									:title="d.name"
									title-item-class="ocs-menu-tab"
								>
									<ADComputersContent
										:domain-count="domains.length"
										:stats="stats"
										:rowdata="rowdata"
										:rowheader="rowheader"
										:isbusy="isbusy"
										:canchange="canchange"
										:candelete="candelete"
										:status-filter="statusFilter"
										@update:statusFilter="statusFilter = $event"
										@reload-datatable="reloadDatatable"
										@unlink="unlinkComputer"
									/>
								</b-tab>
							</b-tabs>
						</div>
					</div>
				</div>
			</div>
		`,
	}
}
