let counter = 0

/** Unique id for staged blobs — works on HTTP LAN (no secure-context crypto). */
export function newId(): string {
	if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
		return crypto.randomUUID()
	}
	counter += 1
	return `staged-${Date.now()}-${counter}`
}
