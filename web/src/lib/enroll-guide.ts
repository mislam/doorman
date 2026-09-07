import type { PoseStep } from "$lib/api"

export type GuideCue =
	| "step-center"
	| "step-left"
	| "step-right"
	| "step-up"
	| "step-down"
	| "adjust-left"
	| "adjust-right"
	| "adjust-up"
	| "adjust-down"
	| "less-left"
	| "less-right"
	| "less-up"
	| "less-down"
	| "center-yaw"
	| "center-pitch"
	| "closer"
	| "frame"
	| "still"
	| "none"

export type GuideDirection = "left" | "right" | "up" | "down"

const HOLD = "hold"

const QUALITY_HINTS = new Set(["Show your full face", "Move closer"])
const WAITING_HINTS = new Set(["Hold still", "Hold still — finding your face"])

/** True when the face is visible enough to show pose arrows (not only after pose passes). */
export function faceGuidesReady(result: {
	ok: boolean
	hint: string | null
	face_count: number
}): boolean {
	if (result.face_count === 0) return false
	if (result.ok) return true
	const hint = result.hint ?? ""
	if (!hint || QUALITY_HINTS.has(hint) || WAITING_HINTS.has(hint)) return false
	return true
}

/** True when we can anchor baseline yaw/pitch from this poll. */
export function canSetBaseline(hint: string | null): boolean {
	const text = hint ?? ""
	return text !== "Show your full face" && text !== "Move closer"
}

const GUIDANCE_CUE: Record<string, GuideCue> = {
	"Face the camera straight on": "center-yaw",
	"Look straight at the camera": "center-pitch",
	"Turn more left": "adjust-left",
	"A bit less left": "less-left",
	"Turn more right": "adjust-right",
	"A bit less right": "less-right",
	"Look up more": "adjust-up",
	"A bit less up": "less-up",
	"Look down more": "adjust-down",
	"A bit less down": "less-down",
	"Show your full face": "frame",
	"Move closer": "closer",
	"Look straight ahead": "center-pitch",
	"Face straight on": "center-yaw",
}

const STEP_CUE: Record<PoseStep, GuideCue> = {
	center: "step-center",
	left: "step-left",
	right: "step-right",
	up: "step-up",
	down: "step-down",
}

/** Map server / step guidance to an on-screen guide cue. */
export function guideCueFrom(guidance: string, step: PoseStep): GuideCue {
	if (
		guidance === "still" ||
		guidance === "Hold still" ||
		guidance === "Hold still — finding your face"
	) {
		return STEP_CUE[step]
	}
	if (guidance === HOLD) return STEP_CUE[step]
	return GUIDANCE_CUE[guidance] ?? "none"
}

/** Brief on-screen hint while the arrow guide is visible. */
export function guideHint(cue: GuideCue): string {
	const hints: Record<GuideCue, string> = {
		"step-center": "Look straight ahead",
		"step-left": "Turn left",
		"step-right": "Turn right",
		"step-up": "Look up",
		"step-down": "Look down",
		"adjust-left": "Turn left",
		"adjust-right": "Turn right",
		"adjust-up": "Look up",
		"adjust-down": "Look down",
		"less-left": "A bit less left",
		"less-right": "A bit less right",
		"less-up": "A bit less up",
		"less-down": "A bit less down",
		"center-yaw": "Face straight on",
		"center-pitch": "Look straight ahead",
		closer: "Move closer",
		frame: "Show your full face",
		still: "Hold still…",
		none: "",
	}
	return hints[cue]
}

/** Screen-reader label for the active cue. */
export function guideAriaLabel(cue: GuideCue): string {
	const labels: Record<GuideCue, string> = {
		"step-center": "Look straight ahead at the camera",
		"step-left": "Turn slightly to your left",
		"step-right": "Turn slightly to your right",
		"step-up": "Look up slightly",
		"step-down": "Look down slightly",
		"adjust-left": "Turn more to your left",
		"adjust-right": "Turn more to your right",
		"adjust-up": "Look up more",
		"adjust-down": "Look down more",
		"less-left": "Turn a bit less to your left",
		"less-right": "Turn a bit less to your right",
		"less-up": "Look up a bit less",
		"less-down": "Look down a bit less",
		"center-yaw": "Face straight on",
		"center-pitch": "Look straight ahead at the camera",
		closer: "Move closer",
		frame: "Show your full face",
		still: "Hold still",
		none: "",
	}
	return labels[cue]
}

/** Arrow direction for directional cues — only when the cue matches the active step. */
export function cueDirection(cue: GuideCue, step: PoseStep): GuideDirection | null {
	if (step === "center") {
		if (cue === "step-center" || cue === "center-yaw" || cue === "center-pitch") {
			return "up"
		}
		return null
	}

	switch (cue) {
		case "step-left":
		case "adjust-left":
			return step === "left" ? "left" : null
		case "less-left":
			return step === "left" ? "right" : null
		case "step-right":
		case "adjust-right":
			return step === "right" ? "right" : null
		case "less-right":
			return step === "right" ? "left" : null
		case "step-up":
		case "adjust-up":
			return step === "up" ? "up" : null
		case "less-up":
			return step === "up" ? "down" : null
		case "step-down":
		case "adjust-down":
			return step === "down" ? "down" : null
		case "less-down":
			return step === "down" ? "up" : null
		default:
			return null
	}
}

const YAW_CUES = new Set<GuideCue>([
	"step-left",
	"adjust-left",
	"less-left",
	"step-right",
	"adjust-right",
	"less-right",
])
const PITCH_CUES = new Set<GuideCue>([
	"step-up",
	"adjust-up",
	"less-up",
	"step-down",
	"adjust-down",
	"less-down",
])

/** Normalize a cue for the active step (e.g. drop stale pitch hints on center). */
export function guideCueForStep(cue: GuideCue, step: PoseStep): GuideCue {
	if (cue === "none") return cue
	if (step === "center") {
		if (cue === "step-center" || cue === "center-yaw" || cue === "center-pitch") {
			return cue
		}
		return "step-center"
	}
	if (step === "left" || step === "right") {
		return YAW_CUES.has(cue) ? cue : STEP_CUE[step]
	}
	if (step === "up" || step === "down") {
		return PITCH_CUES.has(cue) ? cue : STEP_CUE[step]
	}
	return cue
}

/** Map any guidance string to a cue for the active step (handles brief display strings). */
export function guideCueFromGuidance(guidance: string, step: PoseStep): GuideCue {
	return guideCueForStep(guideCueFrom(guidance, step), step)
}
