// The sync endpoint answers 202 right away and runs in the background: the
// returned report stays "running" until the sync ends, so callers poll it.
const POLL_INTERVAL_MS = 3000

export async function startDomainSync(api, domainId) {
	const { data } = await api.http.post(`/activedirectory/domains/${domainId}/sync/`)
	return data?.report ?? null
}

export async function waitForReport(api, reportId) {
	for (;;) {
		await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS))
		const { data } = await api.http.get(`/activedirectory/reports/${reportId}/`)
		if (data.status !== "running") return data
	}
}
