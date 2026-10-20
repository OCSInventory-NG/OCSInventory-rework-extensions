export function createComponent(api) {
	const Loader = api.getComponent("Loader")

	return {
		name: "ADAssetSlot",
		components: { Loader },
		props: { assetId: { type: [String, Number], default: null } },

		data() {
			return {
				loading: false,
				computer: null,
				notFound: false,
			}
		},

		computed: {
			assignedUserLabel() {
				const user = this.computer?.assigned_user
				return user?.name || user?.login || null
			},
			lastSeenLabel() {
				if (!this.computer?.last_seen_at) return "-"
				return new Date(this.computer.last_seen_at).toLocaleString(this.$i18n.locale)
			},
		},

		watch: {
			// assetId changes when navigating between two assets' pages without a
			// full reload, so reload whenever it does.
			assetId: { immediate: true, handler: "load" },
		},

		methods: {
			async load() {
				if (!this.assetId) return
				this.loading = true
				this.notFound = false
				this.computer = null
				try {
					const { data } = await api.http.get("/activedirectory/computers/", {
						params: { asset: this.assetId },
					})
					const results = data?.results ?? data ?? []
					this.computer = results[0] || null
					this.notFound = !this.computer
				} catch {
					this.notFound = true
				} finally {
					this.loading = false
				}
			},
		},

		template: `
            <div v-if="loading" class="ocs-loader mt-3">
                <Loader />
            </div>
            <div v-else-if="computer" class="mt-3">
                <div align="center">
                    <h2>{{ $t('activedirectory.asset_section_title') }}</h2>
                </div>

                <div class="card">
                    <div class="card-status-start" :class="computer.enabled ? 'bg-success' : 'bg-danger'"></div>
                    <div class="card-body">
                        <div class="row align-items-center mb-3">
                            <div class="col-auto">
                                <span
                                    class="avatar"
                                    :class="computer.enabled ? 'bg-success-lt' : 'bg-danger-lt'"
                                >
                                    <font-awesome-icon :icon="['fas', 'desktop']" size="lg" />
                                </span>
                            </div>
                            <div class="col">
                                <div class="h3 mb-0">{{ computer.name }}</div>
                                <div class="text-secondary">{{ computer.dns_hostname || '-' }}</div>
                            </div>
                            <div class="col-auto">
                                <span class="badge" :class="computer.enabled ? 'bg-success' : 'bg-danger'">
                                    <font-awesome-icon
                                        :icon="['fas', computer.enabled ? 'circle-check' : 'circle-xmark']"
                                        class="me-1"
                                    />
                                    {{ computer.enabled ? $t('activedirectory.enabled_true') : $t('activedirectory.enabled_false') }}
                                </span>
                            </div>
                        </div>

                        <div class="divide-y">
                            <div class="row py-2">
                                <div class="col-md-6 d-flex align-items-center gap-2">
                                    <font-awesome-icon :icon="['fas', 'building']" class="text-secondary" fixed-width />
                                    <div>
                                        <div class="subheader mb-0">{{ $t('activedirectory.domain') }}</div>
                                        <div>{{ computer.domain_name }}</div>
                                    </div>
                                </div>
                                <div class="col-md-6 d-flex align-items-center gap-2">
                                    <font-awesome-icon :icon="['fas', 'user']" class="text-secondary" fixed-width />
                                    <div>
                                        <div class="subheader mb-0">{{ $t('activedirectory.assigned_user') }}</div>
                                        <div v-if="assignedUserLabel">
                                            {{ assignedUserLabel }}
                                            <span v-if="computer.assigned_user.email" class="text-secondary">
                                                ({{ computer.assigned_user.email }})
                                            </span>
                                        </div>
                                        <div v-else>-</div>
                                    </div>
                                </div>
                            </div>

                            <div class="row py-2">
                                <div class="col-12 d-flex align-items-center gap-2">
                                    <font-awesome-icon :icon="['fas', 'location-dot']" class="text-secondary" fixed-width />
                                    <div>
                                        <div class="subheader mb-0">{{ $t('activedirectory.ou') }}</div>
                                        <div>{{ computer.ou_path || computer.ou || '-' }}</div>
                                    </div>
                                </div>
                            </div>

                            <div class="row py-2">
                                <div class="col-12 d-flex align-items-center gap-2">
                                    <font-awesome-icon :icon="['fas', 'clock-rotate-left']" class="text-secondary" fixed-width />
                                    <div>
                                        <div class="subheader mb-0">{{ $t('activedirectory.last_seen_at') }}</div>
                                        <div>{{ lastSeenLabel }}</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `,
	}
}
