export function createComponent(api) {
	const Alert = api.getComponent("Alert")

	return {
		name: "ADLinkModal",
		components: { Alert },
		props: {
			computerId: { type: [String, Number], required: true },
			computerName: { type: String, default: "" },
		},

		data() {
			return {
				linkmodal: false,
				search: "",
				options: [],
				searching: false,
				selected: null,
				saving: false,
				errored: false,
				errormsg: null,
			}
		},

		watch: {
			async search(value) {
				if (!value || value.trim().length < 2) {
					this.options = []
					return
				}
				this.searching = true
				try {
					const response = await this.$api.generic.get("asset/bases/", { search: value, limit: 20 })
					this.options = response?.results ?? response ?? []
				} finally {
					this.searching = false
				}
			},
		},

		methods: {
			openModal() {
				this.search = ""
				this.options = []
				this.selected = null
				this.errored = false
				this.errormsg = null
				this.linkmodal = true
			},

			async confirmLink() {
				if (!this.selected) return
				this.saving = true
				this.errored = false
				this.errormsg = null
				try {
					await api.http.post(`/activedirectory/computers/${this.computerId}/link/`, {
						asset: this.selected.id,
					})
					this.linkmodal = false
					this.$emit("reloadDatatable")
				} catch (e) {
					this.errormsg = e.response?.data?.asset || e.response?.data?.error || e.message
					this.errored = true
				} finally {
					this.saving = false
				}
			},
		},

		template: `
            <div id="activedirectory-link-modal">
                <button
                    type="button"
                    class="btn btn-ghost-info"
                    :title="$t('activedirectory.link_to_asset')"
                    @click="openModal"
                >
                    <font-awesome-icon :icon="['fas', 'link']" />
                </button>

                <b-modal
                    v-model="linkmodal"
                    :title="$t('activedirectory.link_to_asset')"
                    hide-footer
                    modal-class="custom-modal"
                >
                    <template #header="{ close }">
                        <h5 class="modal-title">
                            {{ $t('activedirectory.link_modal_title', { name: computerName }) }}
                        </h5>
                        <b-button size="sm" variant="outline-danger" @click="close()">
                            <font-awesome-icon :icon="['fas', 'xmark']" size="1x" />
                        </b-button>
                    </template>

                    <Alert v-if="errored" :message="errormsg" variant="danger" />

                    <div class="mb-3">
                        <label class="form-label">{{ $t('activedirectory.search_asset') }}</label>
                        <input
                            v-model="search"
                            type="search"
                            class="form-control"
                            :placeholder="$t('activedirectory.search_asset_placeholder')"
                        />
                    </div>

                    <div class="list-group mb-3" style="max-height: 260px; overflow-y: auto;">
                        <button
                            v-for="opt in options"
                            :key="opt.id"
                            type="button"
                            class="list-group-item list-group-item-action"
                            :class="{ active: selected && selected.id === opt.id }"
                            @click="selected = opt"
                        >
                            {{ opt.name }}
                        </button>
                        <div v-if="!searching && search.trim().length >= 2 && !options.length" class="list-group-item text-secondary">
                            {{ $t('generic.no_data') }}
                        </div>
                    </div>

                    <div class="d-flex justify-content-center">
                        <b-button
                            variant="success"
                            :disabled="!selected || saving"
                            @click="confirmLink"
                        >
                            <b-spinner v-if="saving" small />
                            {{ $t('activedirectory.link_now') }}
                        </b-button>
                    </div>
                </b-modal>
            </div>
        `,
	}
}
