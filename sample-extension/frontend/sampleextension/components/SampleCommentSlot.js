// Example: injecting into an existing core page.
// Registered on a slot that Detail.vue already renders (see plugin.js),
// so an extension can add a feature to the asset page without touching it.
// Reuses the core Datatable (api.getComponent) and follows the same
// title > create button > datatable layout as core sections (e.g. Notes.vue).
export function createComponent(api) {
	const Datatable = api.getComponent("Datatable");
	const Alert = api.getComponent("Alert");

	return {
		name: "SampleCommentSlot",
		components: { Datatable, Alert },
		props: { assetId: { type: [String, Number], default: null } },

		data() {
			return {
				comments: [],
				message: "",
				rowheader: ["message", "created_at"],
				showcreatemodal: false,
				loadingcreate: false,
				createwithsuccess: false,
				createerror: false,
				createerrormsg: null,
			};
		},

		computed: {
			// Example: gating a UI element by permission. Checks against the
			// user's own permission list (Django's app_action_model format).
			canDelete() {
				return api.hasPermissions(["sampleextension_delete_samplecomment"]);
			},
		},

		watch: {
			// assetId changes when navigating between two assets' pages without a
			// full reload, so reload the list whenever it does.
			assetId: { immediate: true, handler: "load" },

			createwithsuccess: function () {
				if (!this.createwithsuccess) return
				setTimeout(() => {
					this.showcreatemodal = false;
					this.createwithsuccess = false;
					this.message = "";
					this.load();
				}, 500);
			},
		},

		methods: {
			async load() {
				const { data } = await api.http.get("/sampleextension/comments/", {
					params: { asset: this.assetId },
				});
				this.comments = data.results || data;
			},

			openCreateModal() {
				this.message = "";
				this.createerror = false;
				this.createerrormsg = null;
				this.createwithsuccess = false;
				this.showcreatemodal = true;
			},

			async addComment(event) {
				event.preventDefault();
				this.loadingcreate = true;
				this.createwithsuccess = false;
				this.createerror = false;
				this.createerrormsg = null;

				try {
					await api.http.post("/sampleextension/comments/", { asset: this.assetId, message: this.message });
					this.createwithsuccess = true;
				} catch (e) {
					this.createerrormsg = e?.response?.data?.error || e?.message;
					this.createerror = true;
				} finally {
					this.loadingcreate = false;
				}
			},

			async deleteComment(id) {
				await api.http.delete(`/sampleextension/comments/${id}/`);
				await this.load();
			},
		},

		template: `
            <div class="mt-3">
                <div align="center">
                    <h2>{{ $t('sampleextension.comments_title') }}</h2>
                </div>

                <div class="row">
                    <div class="col-auto ms-auto">
                        <b-button
                            :title="$t('sampleextension.add_comment')"
                            variant="primary"
                            class="d-sm-inline-block btn-modal"
                            @click="openCreateModal"
                        >
                            <font-awesome-icon :icon="['fas', 'plus']" />
                            {{ $t('sampleextension.add_comment') }}
                        </b-button>
                    </div>
                </div>

                <Datatable
                    :rowdata="comments"
                    :rowheader="rowheader"
					:candelete="canDelete"
					:candeletemultiple="false"
					:usecheckbox="false"
                    title="sampleextension/comments"
                    translationkey="sampleextension."
                    :hascustomactions="canDelete"
                    @reload-datatable="load"
                />

                <b-modal
                    v-model="showcreatemodal"
                    :title="$t('sampleextension.add_comment')"
                    hide-footer
                    modal-class="custom-modal"
                >
                    <template #header="{ close }">
                        <h5 class="modal-title">
                            {{ $t('sampleextension.add_comment') }}
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
                        v-if="createerror"
                        :message="createerrormsg"
                        variant="danger"
                    />

                    <b-form @submit="addComment">
                        <b-form-group :label="$t('sampleextension.message')" label-for="sampleextension-message">
                            <b-form-textarea
                                id="sampleextension-message"
                                v-model="message"
                                rows="6"
                                required
                            />
                        </b-form-group>

                        <div class="text-center">
                            <b-button type="submit" variant="success">
                                {{ $t('generic.save') }}
                            </b-button>
                        </div>
                    </b-form>
                </b-modal>
            </div>
        `,
	};
}
