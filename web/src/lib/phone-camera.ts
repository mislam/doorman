/** Front-camera helpers for guided phone enrollment. */

const PHONE_CAMERA_UNAVAILABLE =
	"Phone camera needs HTTPS (or localhost). Use Doorbell or Upload instead."

export type CameraPermissionState = PermissionState | "unknown"

/** Browsers block getUserMedia on plain HTTP — common on homelab LAN URLs. */
export function isPhoneCameraSupported(): boolean {
	if (typeof window === "undefined") return false
	if (!window.isSecureContext) return false
	return typeof navigator.mediaDevices?.getUserMedia === "function"
}

/** Best-effort permission probe — may return `unknown` (e.g. some iOS versions). */
export async function queryCameraPermission(): Promise<CameraPermissionState> {
	if (!isPhoneCameraSupported()) return "denied"
	try {
		const result = await navigator.permissions.query({ name: "camera" as PermissionName })
		return result.state
	} catch {
		return "unknown"
	}
}

export async function startPhoneCamera(video: HTMLVideoElement): Promise<MediaStream> {
	if (!isPhoneCameraSupported()) {
		throw new Error(PHONE_CAMERA_UNAVAILABLE)
	}

	const stream = await navigator.mediaDevices.getUserMedia({
		video: {
			facingMode: "user",
			width: { ideal: 1280 },
			height: { ideal: 960 },
		},
		audio: false,
	})
	video.srcObject = stream
	await video.play()
	return stream
}

export function stopPhoneCamera(stream: MediaStream | null): void {
	if (!stream) return
	for (const track of stream.getTracks()) track.stop()
}

/** Grab the current video frame — center square crop (matches square preview). */
export function captureVideoFrame(video: HTMLVideoElement, quality = 0.85): Promise<Blob> {
	const width = video.videoWidth
	const height = video.videoHeight
	if (!width || !height) {
		return Promise.reject(new Error("Camera not ready"))
	}

	const side = Math.min(width, height)
	const sx = (width - side) / 2
	const sy = (height - side) / 2

	const canvas = document.createElement("canvas")
	canvas.width = side
	canvas.height = side
	const ctx = canvas.getContext("2d")
	if (!ctx) return Promise.reject(new Error("Could not capture frame"))
	ctx.drawImage(video, sx, sy, side, side, 0, 0, side, side)

	return new Promise((resolve, reject) => {
		canvas.toBlob(
			(blob) => {
				if (blob) resolve(blob)
				else reject(new Error("Could not encode frame"))
			},
			"image/jpeg",
			quality,
		)
	})
}
