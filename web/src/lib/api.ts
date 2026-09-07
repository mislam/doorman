export const base = "/enroll"

const TOKEN_KEY = "doorman-enroll-token"

export function getToken(): string {
	if (typeof window === "undefined") return ""
	const params = new URLSearchParams(window.location.search)
	const fromUrl = params.get("token")
	if (fromUrl) {
		sessionStorage.setItem(TOKEN_KEY, fromUrl)
		return fromUrl
	}
	return sessionStorage.getItem(TOKEN_KEY) ?? ""
}

function apiUrl(path: string): string {
	const token = getToken()
	const url = `${base}${path}`
	if (!token) return url
	const separator = path.includes("?") ? "&" : "?"
	return `${url}${separator}token=${encodeURIComponent(token)}`
}

function authHeaders(): HeadersInit {
	const token = getToken()
	return token ? { Authorization: `Bearer ${token}` } : {}
}

async function parseError(response: Response): Promise<string> {
	try {
		const data = await response.json()
		if (typeof data.detail === "string") return data.detail
		if (Array.isArray(data.detail)) return data.detail.map((d: { msg: string }) => d.msg).join(", ")
	} catch {
		// ignore
	}
	return response.statusText || "Request failed"
}

export type PersonInfo = { id: string; name: string; photos: string[] }

export type CaptureResult = {
	ok: boolean
	label: string
	filename: string
	face_count: number
	message: string
}

export type ScanFace = { id: string; thumbnail: string; crop: string }

export type ScanResult = { faces: ScanFace[] }

export type RebuildResult = { embeddings: number; people: number; message: string }

export type RecognizeResult = {
	event: string
	names: string[]
	unknown: number
	ts: string
}

export type PoseStep = "center" | "left" | "right" | "up" | "down"

export type EnrollSource = "live" | "footage"

export type PoseCheckResult = {
	ok: boolean
	hint: string | null
	yaw: number
	pitch: number
	face_count: number
}

type PoseQuery = { baselineYaw?: number; baselinePitch?: number }

function poseQueryParams(step: PoseStep, opts?: PoseQuery): URLSearchParams {
	const params = new URLSearchParams({ step })
	if (opts?.baselineYaw !== undefined) params.set("baseline_yaw", String(opts.baselineYaw))
	if (opts?.baselinePitch !== undefined) params.set("baseline_pitch", String(opts.baselinePitch))
	return params
}

/** Poll head pose for guided live enrollment (lightweight — no JPEG). */
export async function checkDoorbellPose(
	step: PoseStep,
	opts?: PoseQuery,
): Promise<PoseCheckResult> {
	const response = await fetch(
		apiUrl(`/api/capture/doorbell/pose?${poseQueryParams(step, opts)}`),
		{
			headers: authHeaders(),
		},
	)
	if (!response.ok) throw new Error(await parseError(response))
	return response.json()
}

/** Poll head pose from a phone camera frame (uploads JPEG). */
export async function checkPhonePose(
	step: PoseStep,
	frame: Blob,
	opts?: PoseQuery,
): Promise<PoseCheckResult> {
	const params = poseQueryParams(step, opts)
	params.set("mirror_yaw", "true")
	const form = new FormData()
	form.append("image", frame, "frame.jpg")

	const response = await fetch(apiUrl(`/api/capture/phone/pose?${params}`), {
		method: "POST",
		headers: authHeaders(),
		body: form,
	})
	if (!response.ok) throw new Error(await parseError(response))
	return response.json()
}

export async function testRecognize(): Promise<RecognizeResult> {
	const response = await fetch("/recognize", {
		method: "POST",
		signal: AbortSignal.timeout(120_000),
	})
	if (!response.ok) throw new Error(await parseError(response))
	return response.json()
}

export async function listPeople(): Promise<PersonInfo[]> {
	const response = await fetch(apiUrl("/api/people"), { headers: authHeaders() })
	if (!response.ok) throw new Error(await parseError(response))
	return response.json()
}

export async function deletePerson(personId: string): Promise<void> {
	const response = await fetch(apiUrl(`/api/people/${encodeURIComponent(personId)}`), {
		method: "DELETE",
		headers: authHeaders(),
	})
	if (!response.ok) throw new Error(await parseError(response))
}

/** Grab a doorbell JPEG for client-side staging (no disk write). */
export async function previewDoorbellFrame(step: PoseStep, opts?: PoseQuery): Promise<Blob> {
	const response = await fetch(
		apiUrl(`/api/capture/doorbell/preview?${poseQueryParams(step, opts)}`),
		{
			method: "POST",
			headers: authHeaders(),
		},
	)
	if (!response.ok) throw new Error(await parseError(response))
	return response.blob()
}

/** Validate pose on a phone frame and return JPEG for staging. */
export async function previewPhoneFrame(
	step: PoseStep,
	frame: Blob,
	opts?: PoseQuery,
): Promise<Blob> {
	const params = poseQueryParams(step, opts)
	params.set("mirror_yaw", "true")
	const form = new FormData()
	form.append("image", frame, "frame.jpg")

	const response = await fetch(apiUrl(`/api/capture/phone/preview?${params}`), {
		method: "POST",
		headers: authHeaders(),
		body: form,
	})
	if (!response.ok) throw new Error(await parseError(response))
	return response.blob()
}

export type EnrollResult = RebuildResult

export async function enrollPerson(
	name: string,
	photos: Blob[],
	source: EnrollSource,
): Promise<EnrollResult> {
	const form = new FormData()
	form.append("name", name)
	form.append("source", source)
	for (const blob of photos) {
		form.append("images", blob, "photo.jpg")
	}

	const response = await fetch(apiUrl("/api/enroll"), {
		method: "POST",
		headers: authHeaders(),
		body: form,
	})
	if (!response.ok) throw new Error(await parseError(response))
	return response.json()
}

export function doorbellStreamUrl(): string {
	return apiUrl("/stream")
}

export function streamSnapshotUrl(): string {
	return apiUrl("/api/snapshot.jpg")
}

/** Append a cache-busting query param without breaking token URLs. */
export function withCacheBust(url: string, tick: number): string {
	const separator = url.includes("?") ? "&" : "?"
	return `${url}${separator}_=${tick}`
}

/** Decode a data URL (from scan crop) into a JPEG blob for upload. */
export function dataUrlToBlob(dataUrl: string): Blob {
	const comma = dataUrl.indexOf(",")
	if (comma === -1) throw new Error("Invalid image data")
	const binary = atob(dataUrl.slice(comma + 1))
	const bytes = new Uint8Array(binary.length)
	for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
	return new Blob([bytes], { type: "image/jpeg" })
}

export async function scanFootage(file: File): Promise<ScanResult> {
	const form = new FormData()
	form.append("file", file)

	const response = await fetch(apiUrl("/api/scan"), {
		method: "POST",
		headers: authHeaders(),
		body: form,
	})
	if (!response.ok) throw new Error(await parseError(response))
	return response.json()
}

export async function rebuildGallery(): Promise<RebuildResult> {
	const response = await fetch(apiUrl("/api/rebuild"), {
		method: "POST",
		headers: authHeaders(),
	})
	if (!response.ok) throw new Error(await parseError(response))
	return response.json()
}
