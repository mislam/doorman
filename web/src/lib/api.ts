export const base = "/enroll"

const TOKEN_KEY = "doorface-enroll-token"

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
		if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join(", ")
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

export type ScanFace = { id: string; thumbnail: string }

export type ScanResult = { session_id: string; faces: ScanFace[] }

export type RebuildResult = { embeddings: number; people: number; message: string }

export type RecognizeResult = {
	event: string
	names: string[]
	unknown: number
	ts: string
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

export async function captureFromStream(name: string, label: string): Promise<CaptureResult> {
	const form = new FormData()
	form.append("name", name)
	form.append("label", label)

	const response = await fetch(apiUrl("/api/capture/doorbell"), {
		method: "POST",
		headers: authHeaders(),
		body: form,
	})
	if (!response.ok) throw new Error(await parseError(response))
	return response.json()
}

/** @deprecated Use captureFromStream — uploads a JPEG from the browser */
export async function capturePhoto(
	name: string,
	label: string,
	blob: Blob,
): Promise<CaptureResult> {
	const form = new FormData()
	form.append("name", name)
	form.append("label", label)
	form.append("image", blob, `${label}.jpg`)

	const response = await fetch(apiUrl("/api/capture"), {
		method: "POST",
		headers: authHeaders(),
		body: form,
	})
	if (!response.ok) throw new Error(await parseError(response))
	return response.json()
}

/** @deprecated Use captureFromStream */
export async function captureDoorbell(name: string, label = "door"): Promise<CaptureResult> {
	return captureFromStream(name, label)
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

export async function saveCrops(
	sessionId: string,
	name: string,
	faceIds: string[],
): Promise<{ saved: string[]; message: string }> {
	const response = await fetch(apiUrl("/api/save-crops"), {
		method: "POST",
		headers: { ...authHeaders(), "Content-Type": "application/json" },
		body: JSON.stringify({ session_id: sessionId, name, face_ids: faceIds }),
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
