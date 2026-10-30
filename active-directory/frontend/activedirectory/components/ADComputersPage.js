export async function createComponent(api) {
	const PageHeader = api.getComponent("PageHeader")
	const Datatable = api.getComponent("Datatable")
	const Alert = api.getComponent("Alert")
	const Loader = api.getComponent("Loader")
	const ADLinkModalComp = await api.importModule("/extensions/activedirectory/components/ADLinkModal.js")
	const ADLinkModal = ADLinkModalComp.createComponent(api)

	const LINK_MODE_VARIANTS = { auto: "info", manual: "purple" }
	const MATCH_VARIANTS = { unlinked: "secondary", ambiguous: "warning" }
	// Datatable sort keys that map to a backend ordering field; the other
	// computed columns cannot be sorted server-side.
	const ORDERING_FIELDS = { name: ["name"], ou: ["ou_path", "ou"], match_status_label: ["match_status"] }
	const NON_SORTABLE_FIELDS = ["domain_name", "in_directory_label", "assigned_user_label", "enabled_label", "asset_name"]
	const DEFAULT_ORDERING = "name,id"
	const STATUS_FILTERS = { active: "true", inactive: "false" }
	const EXPORT_PAGE_SIZE = 500

	const emptyStats = () => ({ total: 0, linked: 0, unlinked: 0, ambiguous: 0, removed: 0 })

	const toApiOrdering = (ordering) => {
		if (!ordering) return DEFAULT_ORDERING
		const desc = ordering.startsWith("-")
		const fields = ORDERING_FIELDS[desc ? ordering.slice(1) : ordering]
		if (!fields) return DEFAULT_ORDERING
		// id last: offset pagination needs a unique order
		return [...fields, "id"].map((field) => (desc ? `-${field}` : field)).join(",")
	}

	// Shared stats + filters + table block, rendered inside the active tab
	// (one tab per domain plus "all") so the b-tab carries real content
	// instead of an empty pane - b-tabs still reserves the content area otherwise.
	const ADComputersContent = {
		name: "ADComputersContent",
		components: { Datatable, ADLinkModal },
		props: {
			domainCount: { type: Number, required: true },
			stats: { type: Object, required: true },
			rowdata: { type: Array, required: true },
			rowheader: { type: Array, required: true },
			total: { type: Number, required: true },
			isbusy: { type: Boolean, required: true },
			canchange: { type: Boolean, required: true },
			candelete: { type: Boolean, required: true },
			statusFilter: { type: String, required: true },
		},
		data() {
			return { nonSortableFields: NON_SORTABLE_FIELDS }
		},
		emits: ["update:statusFilter", "reload-datatable", "change-query", "export", "export-all", "unlink"],
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

				<!-- Keyed on the status filter so a filter change remounts the
				     table on page 1, in step with the parent's reset query. -->
				<Datatable
					:key="statusFilter"
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
					:nonsortablefields="nonSortableFields"
					:server-side="true"
					:server-total-rows="total"
					sortby="name"
					@reload-datatable="$emit('reload-datatable')"
					@change-query="$emit('change-query', $event)"
					@export="$emit('export', $event)"
					@export-all="$emit('export-all', $event)"
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
				total: 0,
				stats: emptyStats(),
				query: {
					limit: Number(localStorage.getItem("perPage")) || 5,
					offset: 0,
					ordering: DEFAULT_ORDERING,
					search: null,
				},
				requestId: 0,
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

			// Filters sent to the API; "all" values are dropped by the generic service.
			filterParams() {
				return {
					domain: this.activeDomainId === "all" ? null : this.activeDomainId,
					enabled: STATUS_FILTERS[this.statusFilter] ?? null,
				}
			},

			rowdata() {
				return this.computers.map((c) => this.toRow(c))
			},

			statsView() {
				const { total, linked } = this.stats
				return {
					...this.stats,
					linkedPct: total ? ((linked / total) * 100).toFixed(1) : "0",
				}
			},
		},

		watch: {
			// The table remounts on tab/status change (see template), so its
			// page, search and sort are back to defaults: mirror that here.
			activeDomainId() {
				this.resetQuery()
				this.fetchComputers()
				this.fetchStats()
			},
			statusFilter() {
				this.resetQuery()
				this.fetchComputers()
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

			toRow(c) {
				const cellLinks = {}
				if (c.asset && c.asset_name) {
					cellLinks.asset_name = { href: api.withBase(`inventory/asset/${c.asset}`), label: c.asset_name }
				}
				const linked = c.match_status === "linked"
				const manuallyUnlinked = !linked && c.link_mode === "manual_unlinked"
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
					match_status_label: linked || manuallyUnlinked
						? this.$t(`activedirectory.link_mode_${c.link_mode || "auto"}`)
						: this.$t(`activedirectory.match_status_${c.match_status}`),
					__match_status_label_variant: linked
						? (LINK_MODE_VARIANTS[c.link_mode] || "info")
						: (MATCH_VARIANTS[c.match_status] || "secondary"),
				}
			},

			resetQuery() {
				this.query = { ...this.query, offset: 0, ordering: DEFAULT_ORDERING, search: null }
			},

			async load() {
				this.loading = true
				try {
					await Promise.all([this.fetchDomains(), this.fetchComputers(), this.fetchStats()])
				} finally {
					this.loading = false
				}
			},

			async fetchDomains() {
				const response = await this.$api.generic.get("/activedirectory/domains/")
				this.domains = response?.results ?? response ?? []
			},

			async fetchComputers() {
				// Tab/filter switches can overlap: only the latest request may
				// write the table.
				const requestId = ++this.requestId
				this.isbusy = true
				this.errored = false
				this.errormsg = null
				try {
					const { limit, offset, ordering, search } = this.query
					const response = await this.$api.generic.get(
						"/activedirectory/computers/",
						{ limit, offset, ordering, search },
						this.filterParams,
					)
					if (requestId !== this.requestId) return
					this.computers = response?.results ?? response ?? []
					this.total = typeof response?.count === "number" ? response.count : this.computers.length
				} catch (e) {
					if (requestId !== this.requestId) return
					this.errormsg = e.message
					this.errored = true
				} finally {
					if (requestId === this.requestId) this.isbusy = false
				}
			},

			async fetchStats() {
				try {
					const response = await this.$api.generic.get("/activedirectory/computers/stats/", {
						domain: this.filterParams.domain,
					})
					this.stats = { ...emptyStats(), ...response }
				} catch (e) {
					this.errormsg = e.message
					this.errored = true
				}
			},

			async reloadDatatable() {
				await Promise.all([this.fetchComputers(), this.fetchStats()])
			},

			handleQueryChange(query) {
				this.query = { ...this.query, ...query, ordering: toApiOrdering(query.ordering) }
				this.fetchComputers()
			},

			exportRows(rows, scope) {
				const columns = this.rowheader.filter((key) => key !== "actions")
				const lines = [columns.join(";")]
				rows.forEach((row) => {
					lines.push(columns.map((key) => `"${String(row[key] ?? "").replace(/"/g, '""')}"`).join(";"))
				})
				const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" })
				const url = URL.createObjectURL(blob)
				const link = document.createElement("a")
				link.href = url
				link.setAttribute("download", `activedirectory_computers_${scope}.csv`)
				document.body.appendChild(link)
				link.click()
				link.remove()
				URL.revokeObjectURL(url)
			},

			handleExport({ scope, rows }) {
				this.exportRows(rows, scope)
			},

			async handleExportAll({ filter, ordering }) {
				try {
					const computers = []
					let offset = 0
					for (;;) {
						const response = await this.$api.generic.get(
							"/activedirectory/computers/",
							{ limit: EXPORT_PAGE_SIZE, offset, search: filter, ordering: toApiOrdering(ordering) },
							this.filterParams,
						)
						const page = response?.results ?? response ?? []
						computers.push(...page)
						if (!response?.next || !page.length) break
						offset += page.length
					}
					this.exportRows(computers.map((c) => this.toRow(c)), "all")
				} catch (e) {
					this.errormsg = e.message
					this.errored = true
				}
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
					<div class="card">
						<div class="card-body">
							<Alert v-if="errored" :message="errormsg" :cols="true" variant="danger" />

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
									v-for="(tab, index) in [{ id: 'all', name: $t('activedirectory.all_domains') }, ...domains]"
									:key="tab.id"
									:title="tab.name"
									title-item-class="ocs-menu-tab"
								>
									<!-- Only the active tab holds a table: switching tabs
									     remounts it on page 1, matching the reset query. -->
									<ADComputersContent
										v-if="activeTabIndex === index"
										:domain-count="domains.length"
										:stats="statsView"
										:rowdata="rowdata"
										:rowheader="rowheader"
										:total="total"
										:isbusy="isbusy"
										:canchange="canchange"
										:candelete="candelete"
										:status-filter="statusFilter"
										@update:statusFilter="statusFilter = $event"
										@reload-datatable="reloadDatatable"
										@change-query="handleQueryChange"
										@export="handleExport"
										@export-all="handleExportAll"
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
