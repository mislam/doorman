<script lang="ts">
	import { onMount, tick } from "svelte";
	import {
		checkDoorbellPose,
		checkPhonePose,
		dataUrlToBlob,
		deletePerson,
		doorbellStreamUrl,
		enrollPerson,
		listPeople,
		previewDoorbellFrame,
		previewPhoneFrame,
		scanFootage,
		streamSnapshotUrl,
		withCacheBust,
		type PersonInfo,
		type PoseStep,
		type ScanFace,
	} from "$lib/api";
	import CameraSheet, { type CameraSource } from "$lib/CameraSheet.svelte";
	import EnrollCompleteOverlay from "$lib/EnrollCompleteOverlay.svelte";
	import FaceGuideOverlay from "$lib/FaceGuideOverlay.svelte";
	import {
		canSetBaseline,
		cueDirection,
		faceGuidesReady,
		guideCueForStep,
		guideCueFrom,
		guideCueFromGuidance,
		guideHint,
	} from "$lib/enroll-guide";
	import { newId } from "$lib/id";
	import {
		captureVideoFrame,
		isPhoneCameraSupported,
		queryCameraPermission,
		startPhoneCamera,
		stopPhoneCamera,
	} from "$lib/phone-camera";

	const POLL_MS = 1000;
	const PREFLIGHT_TIMEOUT_MS = 30_000;
	const STEP_TIMEOUT_MS = 30_000;
	const OK_STREAK = 2;
	const CAMERA_KEY = "doorman-enroll-camera";

	type LiveStep = { pose: PoseStep; hint: string };
	type StagedPhoto = { id: string; blob: Blob; url: string };

	const liveSteps: LiveStep[] = [
		{ pose: "left", hint: "Turn slightly to your left" },
		{ pose: "right", hint: "Turn slightly to your right" },
		{ pose: "up", hint: "Look up slightly" },
		{ pose: "down", hint: "Look down slightly" },
		{ pose: "center", hint: "Look straight ahead" },
	];

	type BusyAction = "" | "capture" | "enroll" | "delete";

	let cameraSource = $state<CameraSource>("doorbell");
	let cameraSheetOpen = $state(false);
	let name = $state("");
	let busyAction = $state<BusyAction>("");
	let message = $state("");
	let messageKind = $state<"ok" | "warn" | "error">("ok");
	let liveStaged = $state<Record<number, StagedPhoto>>({});
	let footageStaged = $state<StagedPhoto[]>([]);
	let enrolled = $state<PersonInfo[]>([]);
	let pendingFaces = $state<ScanFace[]>([]);
	let askingName = $state(false);
	let fileInput = $state<HTMLInputElement | null>(null);
	let nameInput = $state<HTMLInputElement | null>(null);
	let phoneVideo = $state<HTMLVideoElement | null>(null);
	let phoneStream: MediaStream | null = null;
	let phoneReady = $state(false);
	let phoneError = $state("");
	let phoneEnableNeeded = $state(false);
	let streamReady = $state(false);
	let snapshotLoaded = $state(false);
	let snapshotTick = $state(0);
	let baselineYaw = $state<number | null>(null);
	let baselinePitch = $state<number | null>(null);
	let poseGuidance = $state("hold");
	let poseHintKey = $state("hold");
	let faceReady = $state(false);
	let envReady = $state(false);
	let stepTimedOut = $state(false);
	let capturing = $state(false);
	let enrollSuccessName = $state("");

	let pollTimer: number | null = null;
	let stepStartedAt = 0;
	let okStreak = 0;

	const activeLiveStepIndex = $derived.by(() => {
		for (let index = 0; index < liveSteps.length; index += 1) {
			if (liveStaged[index] === undefined) return index;
		}
		return -1;
	});
	const liveCaptureComplete = $derived(activeLiveStepIndex === -1);
	const currentLiveStep = $derived(
		liveCaptureComplete ? liveSteps[liveSteps.length - 1] : liveSteps[activeLiveStepIndex],
	);
	const busy = $derived(busyAction !== "");
	const liveStagedCount = $derived(Object.keys(liveStaged).length);
	const footageStagedCount = $derived(footageStaged.length);
	const usingGuidedPhotos = $derived(liveStagedCount > 0);
	const stagedCount = $derived(
		usingGuidedPhotos ? liveStagedCount : footageStagedCount,
	);
	const previewStepIndex = $derived(
		activeLiveStepIndex >= 0 ? activeLiveStepIndex : liveSteps.length - 1,
	);
	const canUpload = $derived(!busy && !capturing && pendingFaces.length === 0);
	const showEnrollButton = $derived(footageStagedCount > 0 && liveStagedCount === 0);
	const HOLD_STILL = "hold";
	const usePhoneCamera = $derived(cameraSource === "phone");

	function briefPoseHint(hint: string): string {
		const short: Record<string, string> = {
			"Face the camera straight on": "Face straight on",
			"Look straight at the camera": "Look straight ahead",
			"Turn more left": "Turn more left",
			"A bit less left": "A bit less left",
			"Turn more right": "Turn more right",
			"A bit less right": "A bit less right",
			"Look up more": "Look up more",
			"A bit less up": "A bit less up",
			"Look down more": "Look down more",
			"A bit less down": "A bit less down",
			"Need better lighting": "Need better lighting",
			"Image is too blurry": "Too blurry — hold still",
			"Use a plain background": "Use a plain background",
			"No face visible": "No face visible",
			"One person only": "One person only",
			"Try another angle": "Try another angle",
			"Hold still — finding your face": "Hold still",
			"Show your full face": "Show your full face",
			"Move closer": "Move closer",
			"Need exactly one person at the door": "One person only",
			"Connecting to doorbell…": "Connecting…",
		};
		return short[hint] ?? hint;
	}

	const guidedNameStep = $derived(
		liveCaptureComplete && liveStagedCount === liveSteps.length,
	);
	const showGuidedNameForm = $derived(guidedNameStep && busyAction !== "enroll");
	const showFootageNameForm = $derived(askingName && !guidedNameStep);
	const doneDisabled = $derived(!name.trim() || busy);
	const enrollJustFinished = $derived(enrollSuccessName !== "");

	function poseQuery() {
		return {
			baselineYaw: baselineYaw ?? undefined,
			baselinePitch: baselinePitch ?? undefined,
		};
	}

	const showLiveStream = $derived(
		!enrollJustFinished &&
			!liveCaptureComplete &&
			liveStaged[activeLiveStepIndex] === undefined,
	);
	const cameraReady = $derived(
		usePhoneCamera ? phoneReady && !phoneError : streamReady || snapshotLoaded,
	);
	const showPhoneEnableButton = $derived(
		usePhoneCamera && showLiveStream && phoneEnableNeeded && !phoneReady && !phoneError,
	);
	const inGuidedCapture = $derived(
		cameraReady &&
			showLiveStream &&
			!stepTimedOut &&
			!capturing &&
			pendingFaces.length === 0 &&
			!liveCaptureComplete,
	);
	const guideCue = $derived(
		inGuidedCapture ? guideCueFromGuidance(poseHintKey, currentLiveStep.pose) : "none",
	);
	const guideDirection = $derived.by(() => {
		if (!envReady || !faceReady || !inGuidedCapture) return null;
		// Step 5: always top up-arrow — raise head to straight (not bottom down-arrow from step 4).
		if (currentLiveStep.pose === "center") return "up";
		if (guideCue === "none") return null;
		return cueDirection(guideCue, currentLiveStep.pose);
	});
	const showGuideOverlay = $derived(guideDirection !== null);
	const showFaceGuide = $derived(inGuidedCapture);
	const statusLine = $derived.by(() => {
		if (pendingFaces.length > 0) return "Tap the matching face";
		if (busyAction === "enroll") return "Enrolling…";
		if (usingGuidedPhotos && liveCaptureComplete) return "";
		if (!usingGuidedPhotos && footageStagedCount > 0) {
			return `${footageStagedCount} upload${footageStagedCount === 1 ? "" : "s"} ready — tap Enroll`;
		}
		if (capturing) return "Capturing…";
		if (stepTimedOut) return "Timed out — tap Retry";
		if (showPhoneEnableButton) return "";
		if (usePhoneCamera && showLiveStream && !phoneReady && !phoneError) {
			return "Starting camera…";
		}
		if (!usePhoneCamera && showLiveStream && !cameraReady) return "Connecting to doorbell…";
		if (!cameraReady) return "";
		if (inGuidedCapture && !envReady) {
			if (poseGuidance !== HOLD_STILL && poseGuidance !== "still") {
				return briefPoseHint(poseGuidance);
			}
			return "Face the camera — get ready";
		}
		if (inGuidedCapture && !faceReady) return "Hold still";
		if (currentLiveStep.pose === "center" && faceReady) return "Look straight ahead";
		if (showGuideOverlay) return guideHint(guideCue);
		if (poseGuidance === "still") return "Hold still…";
		if (poseGuidance !== HOLD_STILL) return briefPoseHint(poseGuidance);
		if (!envReady) return "Face the camera — get ready";
		return currentLiveStep.hint;
	});
	const showActionSlot = $derived(
		enrollJustFinished ||
			footageStagedCount === 0 ||
			showEnrollButton ||
			stepTimedOut ||
			showGuidedNameForm ||
			showFootageNameForm ||
			(guidedNameStep && busyAction === "enroll") ||
			showPhoneEnableButton ||
			pendingFaces.length > 0,
	);
	const enrollDisabled = $derived(
		stagedCount === 0 || busy || (askingName && !name.trim()),
	);
	const enrollLabel = $derived(
		busyAction === "enroll"
			? "Enrolling…"
			: askingName
				? "Enroll"
				: stagedCount > 0
					? `Enroll (${stagedCount})`
					: "Enroll",
	);
	const streamUrl = $derived(doorbellStreamUrl());
	const snapshotUrl = $derived(withCacheBust(streamSnapshotUrl(), snapshotTick));
	const stagedPreviewUrl = $derived(liveStaged[previewStepIndex]?.url ?? "");

	onMount(() => {
		const saved = localStorage.getItem(CAMERA_KEY);
		if (saved === "doorbell") {
			cameraSource = "doorbell";
		} else if (saved === "phone" && isPhoneCameraSupported()) {
			cameraSource = "phone";
		}

		const snapshotTimer = window.setInterval(() => {
			if (cameraSource === "doorbell" && !streamReady) snapshotTick += 1;
		}, 400);

		void loadEnrolled();
		return () => {
			window.clearInterval(snapshotTimer);
			stopPosePolling();
			stopPhoneStream();
			clearStaged();
		};
	});

	$effect(() => {
		if (!usePhoneCamera) {
			stopPhoneStream();
			phoneEnableNeeded = false;
			return;
		}
		if (!phoneVideo || askingName || liveCaptureComplete || enrollJustFinished) return;

		let cancelled = false;
		phoneError = "";
		phoneReady = false;
		phoneEnableNeeded = false;

		void (async () => {
			const permission = await queryCameraPermission();
			if (cancelled) return;

			if (permission === "denied") {
				phoneError =
					"Camera access denied — allow camera in browser settings or use Doorbell";
				return;
			}

			if (permission === "granted") {
				await beginPhoneCamera();
				return;
			}

			phoneEnableNeeded = true;
		})();

		return () => {
			cancelled = true;
			stopPhoneStream();
		};
	});

	$effect(() => {
		if (
			askingName ||
			busy ||
			capturing ||
			liveCaptureComplete ||
			enrollJustFinished ||
			pendingFaces.length > 0
		) {
			stopPosePolling();
			return;
		}
		if (liveStaged[activeLiveStepIndex]) {
			stopPosePolling();
			return;
		}
		if (stepTimedOut) {
			stopPosePolling();
			return;
		}
		if (usePhoneCamera && (!phoneReady || phoneError)) {
			stopPosePolling();
			return;
		}
		startPosePolling();
		return () => stopPosePolling();
	});

	$effect(() => {
		if (!guidedNameStep || busyAction === "enroll") {
			return;
		}
		askingName = true;
		const focusFallback = window.setTimeout(() => focusNameInput(), 1900);
		return () => window.clearTimeout(focusFallback);
	});

	function beginStepTimer() {
		stepStartedAt = Date.now();
		stepTimedOut = false;
		okStreak = 0;
	}

	function resetStepTimer() {
		beginStepTimer();
		poseHintKey = HOLD_STILL;
		poseGuidance = HOLD_STILL;
	}

	function startPosePolling() {
		if (pollTimer !== null) return;
		resetStepTimer();
		pollTimer = window.setInterval(() => {
			void pollPoseOnce();
		}, POLL_MS);
		void pollPoseOnce();
	}

	function stopPosePolling() {
		if (pollTimer !== null) {
			window.clearInterval(pollTimer);
			pollTimer = null;
		}
		okStreak = 0;
	}

	function stopPhoneStream() {
		stopPhoneCamera(phoneStream);
		phoneStream = null;
		phoneReady = false;
		phoneEnableNeeded = false;
	}

	async function beginPhoneCamera() {
		if (!phoneVideo || phoneReady) return;
		phoneError = "";
		try {
			const stream = await startPhoneCamera(phoneVideo);
			phoneStream = stream;
			phoneReady = true;
			phoneEnableNeeded = false;
		} catch (err) {
			phoneError = err instanceof Error ? err.message : String(err);
			phoneEnableNeeded = true;
		}
	}

	function enablePhoneCamera() {
		void beginPhoneCamera();
	}

	function focusNameInput() {
		void tick().then(() => {
			requestAnimationFrame(() => {
				nameInput?.focus({ preventScroll: true });
			});
		});
	}

	async function pollPoseOnce() {
		if (capturing || stepTimedOut || liveCaptureComplete) return;
		if (liveStaged[activeLiveStepIndex]) return;
		const stepIndex = activeLiveStepIndex;
		const stepPose = currentLiveStep.pose;
		const preflight = !envReady;
		const stepTimeoutMs = preflight ? PREFLIGHT_TIMEOUT_MS : STEP_TIMEOUT_MS;
		if (Date.now() - stepStartedAt > stepTimeoutMs) {
			stepTimedOut = true;
			stopPosePolling();
			poseGuidance = "Timed out — tap Retry";
			return;
		}

		try {
			let result;
			if (usePhoneCamera) {
				if (!phoneVideo || !phoneReady) {
					poseGuidance = "Starting camera…";
					return;
				}
				const frame = await captureVideoFrame(phoneVideo);
				result = await checkPhonePose(stepPose, frame, {
					...poseQuery(),
					preflight,
				});
			} else {
				result = await checkDoorbellPose(stepPose, { ...poseQuery(), preflight });
			}
			if (stepIndex !== activeLiveStepIndex) return;

			const raw = result.hint ?? "";

			if (preflight) {
				faceReady = false;
				if (!result.ok) {
					okStreak = 0;
					poseHintKey = raw || "Adjust setup";
					poseGuidance = briefPoseHint(poseHintKey);
					return;
				}
				okStreak += 1;
				poseHintKey = HOLD_STILL;
				poseGuidance = HOLD_STILL;
				if (okStreak >= OK_STREAK) {
					envReady = true;
					baselineYaw = result.yaw;
					baselinePitch = result.pitch;
					beginStepTimer();
				}
				return;
			}

			if (result.face_count > 0 && baselineYaw === null && canSetBaseline(raw)) {
				baselineYaw = result.yaw;
				baselinePitch = result.pitch;
			}

			if (faceGuidesReady(result)) {
				faceReady = true;
			}

			if (!result.ok) {
				okStreak = 0;
				poseHintKey = raw || "Adjust pose";
				poseGuidance = briefPoseHint(poseHintKey);
				return;
			}

			faceReady = true;
			okStreak += 1;
			poseHintKey = "still";
			poseGuidance = "still";
			if (baselineYaw === null) {
				baselineYaw = result.yaw;
				baselinePitch = result.pitch;
			}
			if (okStreak >= OK_STREAK) {
				await autoCaptureStep();
			}
		} catch (err) {
			okStreak = 0;
			poseGuidance = err instanceof Error ? err.message : String(err);
		}
	}

	async function autoCaptureStep() {
		stopPosePolling();
		capturing = true;
		message = "";
		try {
			let blob: Blob;
			if (usePhoneCamera) {
				if (!phoneVideo) throw new Error("Camera not ready");
				const frame = await captureVideoFrame(phoneVideo);
				blob = await previewPhoneFrame(currentLiveStep.pose, frame, poseQuery());
			} else {
				blob = await previewDoorbellFrame(currentLiveStep.pose, poseQuery());
			}
			stageLivePhoto(blob);
		} catch (err) {
			showError(err);
			startPosePolling();
		} finally {
			capturing = false;
		}
	}

	function retryCurrentStep() {
		message = "";
		resetStepTimer();
		startPosePolling();
	}

	async function loadEnrolled() {
		try {
			enrolled = await listPeople();
		} catch (err) {
			showError(err);
		}
	}

	function showOk(text: string) {
		message = text;
		messageKind = "ok";
	}

	function showWarn(text: string) {
		message = text;
		messageKind = "warn";
	}

	function showError(err: unknown) {
		message = err instanceof Error ? err.message : String(err);
		messageKind = "error";
	}

	function revokePhoto(photo: StagedPhoto) {
		URL.revokeObjectURL(photo.url);
	}

	function clearStaged() {
		for (const photo of Object.values(liveStaged)) revokePhoto(photo);
		for (const photo of footageStaged) revokePhoto(photo);
		liveStaged = {};
		footageStaged = [];
		baselineYaw = null;
		baselinePitch = null;
		envReady = false;
		faceReady = false;
		poseHintKey = HOLD_STILL;
		poseGuidance = HOLD_STILL;
	}

	function stageLivePhoto(blob: Blob) {
		const step = activeLiveStepIndex;
		if (step < 0) return;
		const existing = liveStaged[step];
		if (existing) revokePhoto(existing);
		liveStaged = {
			...liveStaged,
			[step]: {
				id: newId(),
				blob,
				url: URL.createObjectURL(blob),
			},
		};
		resetStepTimer();
	}

	function stageFootagePhoto(blob: Blob) {
		footageStaged = [
			...footageStaged,
			{
				id: newId(),
				blob,
				url: URL.createObjectURL(blob),
			},
		];
		showOk(`Added photo ${footageStaged.length}`);
		pendingFaces = [];
	}

	function removeFootagePhoto(id: string) {
		const photo = footageStaged.find((entry) => entry.id === id);
		if (photo) revokePhoto(photo);
		footageStaged = footageStaged.filter((entry) => entry.id !== id);
	}

	function openUpload() {
		if (!canUpload) return;
		enrollSuccessName = "";
		message = "";
		fileInput?.click();
	}

	async function onFootageFile(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = "";
		if (!file) return;

		busyAction = "capture";
		message = "";
		pendingFaces = [];
		try {
			const result = await scanFootage(file);
			if (result.faces.length === 0) {
				showWarn("No face found — try another photo or clip");
				return;
			}
			if (result.faces.length === 1) {
				stageFootagePhoto(dataUrlToBlob(result.faces[0].crop));
				return;
			}
			pendingFaces = result.faces;
		} catch (err) {
			showError(err);
		} finally {
			busyAction = "";
		}
	}

	function pickFootageFace(face: ScanFace) {
		stageFootagePhoto(dataUrlToBlob(face.crop));
	}

	function findEnrolledMatch(typed: string): PersonInfo | undefined {
		const key = typed.trim().toLowerCase();
		return enrolled.find((person) => person.name.toLowerCase() === key);
	}

	async function submitEnroll() {
		if (enrollDisabled || !name.trim()) return;
		const typed = name.trim();
		const existing = findEnrolledMatch(typed);
		if (existing) {
			const confirmed = confirm(
				`Update ${existing.name}? This replaces their enrollment photos.`,
			);
			if (!confirmed) return;
		}
		busyAction = "enroll";
		message = "";
		const enrollName = existing?.name ?? typed;
		const source = usingGuidedPhotos ? "live" : "footage";
		const photos = usingGuidedPhotos
			? liveSteps
					.map((_, index) => liveStaged[index])
					.filter((photo): photo is StagedPhoto => photo !== undefined)
					.map((photo) => photo.blob)
			: footageStaged.map((photo) => photo.blob);
		try {
			await enrollPerson(enrollName, photos, source, { replace: Boolean(existing) });
			enrollSuccessName = enrollName;
			clearStaged();
			name = "";
			askingName = false;
			enrolled = await listPeople();
		} catch (err) {
			showError(err);
		} finally {
			busyAction = "";
		}
	}

	function handleEnrollClick() {
		if (stagedCount === 0 || busy) return;
		if (!askingName) {
			askingName = true;
			message = "";
			void tick().then(() => focusNameInput());
			return;
		}
		void submitEnroll();
	}

	function handleDoneClick() {
		if (doneDisabled) return;
		void submitEnroll();
	}

	function startAnotherEnroll() {
		enrollSuccessName = "";
		message = "";
		stepTimedOut = false;
		faceReady = false;
		envReady = false;
		poseHintKey = HOLD_STILL;
		poseGuidance = HOLD_STILL;
		baselineYaw = null;
		baselinePitch = null;
	}

	async function removeEnrolled(person: PersonInfo) {
		if (!confirm(`Remove ${person.name} from recognition?`)) return;
		busyAction = "delete";
		try {
			await deletePerson(person.id);
			enrolled = await listPeople();
			showOk(`Removed ${person.name}`);
		} catch (err) {
			showError(err);
		} finally {
			busyAction = "";
		}
	}

	function switchCameraSource(next: CameraSource) {
		if (next === cameraSource) return;
		if (next === "phone" && !isPhoneCameraSupported()) return;
		cameraSource = next;
		localStorage.setItem(CAMERA_KEY, next);
		message = "";
		stopPosePolling();
		stepTimedOut = false;
		faceReady = false;
		envReady = false;
		poseHintKey = HOLD_STILL;
		poseGuidance = HOLD_STILL;
		baselineYaw = null;
		baselinePitch = null;
		for (const photo of Object.values(liveStaged)) revokePhoto(photo);
		liveStaged = {};
		enrollSuccessName = "";
	}
</script>

<CameraSheet
	open={cameraSheetOpen}
	current={cameraSource}
	uploadActive={footageStagedCount > 0 && liveStagedCount === 0}
	uploadDisabled={!canUpload}
	onselect={switchCameraSource}
	onupload={openUpload}
	onclose={() => (cameraSheetOpen = false)}
/>

<div class="mx-auto max-w-xl pb-8">
	<header class="relative flex items-center justify-center px-4 pb-5 pt-6">
		<h1 class="text-2xl font-semibold">Add your face</h1>
		<button
			type="button"
			class="absolute right-4 flex h-11 w-11 items-center justify-center text-text transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
			disabled={busy && busyAction === "capture"}
			aria-label="Choose source"
			onclick={() => (cameraSheetOpen = true)}
		>
			<svg class="h-8 w-8" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
				<path
					d="M20 5h-3.17L15 3H9L7.17 5H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm-8 13c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5z"
				/>
			</svg>
		</button>
	</header>

	<div class="px-4">
		<input
			bind:this={fileInput}
			class="sr-only"
			type="file"
			accept="image/*,video/*"
			onchange={onFootageFile}
		/>

		<div
			class="relative mx-auto mt-6 mb-6 aspect-square w-full overflow-hidden rounded-full bg-black ring-1 ring-white/10"
		>
			{#if enrollJustFinished}
				<div class="enroll-success">
					<div class="enroll-success-tick" aria-hidden="true">
						<svg
							class="h-10 w-10"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="2.5"
							stroke-linecap="round"
							stroke-linejoin="round"
						>
							<path d="M5 13l4 4L19 7" />
						</svg>
					</div>
					<div class="enroll-success-text">
						<p class="text-xl font-semibold text-text">Added {enrollSuccessName}</p>
						<p class="mt-2 text-muted">You're all set.</p>
					</div>
				</div>
			{:else if showLiveStream}
				{#if usePhoneCamera}
					<video
						bind:this={phoneVideo}
						class="absolute inset-0 h-full w-full -scale-x-100 object-cover"
						playsinline
						muted
					></video>
					{#if phoneError}
						<div class="absolute inset-0 flex items-center justify-center bg-black/80 p-4">
							<p class="text-center text-danger">{phoneError}</p>
						</div>
					{:else if phoneEnableNeeded}
						<div class="absolute inset-0 flex items-center justify-center bg-black">
							<p class="px-4 text-center text-muted">Camera access needed</p>
						</div>
					{:else if !phoneReady}
						<div class="absolute inset-0 flex items-center justify-center bg-black">
							<p class="px-4 text-center text-muted">Starting camera…</p>
						</div>
					{/if}
				{:else if streamReady}
					<img
						src={streamUrl}
						alt="Doorbell camera"
						class="absolute inset-0 h-full w-full object-cover"
					/>
				{:else}
					<img
						src={snapshotUrl}
						alt=""
						class="absolute inset-0 h-full w-full object-cover transition-opacity duration-300 {snapshotLoaded
							? 'opacity-100'
							: 'opacity-0'}"
						onload={() => (snapshotLoaded = true)}
						onerror={() => (snapshotLoaded = false)}
					/>
					{#if !streamReady && !snapshotLoaded}
						<div class="absolute inset-0 flex items-center justify-center bg-black">
							<p class="px-4 text-center text-muted">Connecting to doorbell…</p>
						</div>
					{:else if !streamReady}
						<div
							class="absolute inset-x-0 bottom-0 bg-black/70 px-3 py-2 text-center text-muted"
						>
							Starting live stream…
						</div>
					{/if}
					<img class="sr-only" src={streamUrl} alt="" onload={() => (streamReady = true)} />
				{/if}
			{:else if stagedPreviewUrl}
				<img
					src={stagedPreviewUrl}
					alt="Captured step {previewStepIndex + 1}"
					class="absolute inset-0 h-full w-full object-cover {usePhoneCamera ? '-scale-x-100' : ''}"
				/>
			{/if}

			{#if pendingFaces.length > 0}
				<div
					class="absolute inset-0 z-10 grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] content-center gap-2 bg-black/90 p-2"
				>
					{#each pendingFaces as face}
						<button
							type="button"
							class="overflow-hidden rounded-xl border-2 border-border p-0 disabled:opacity-50"
							disabled={busy}
							onclick={() => pickFootageFace(face)}
						>
							<img src={face.thumbnail} alt="Detected face" class="aspect-square w-full object-cover" />
						</button>
					{/each}
				</div>
			{/if}

			{#if showFaceGuide && guideDirection}
				{#key activeLiveStepIndex}
					<FaceGuideOverlay direction={guideDirection} />
				{/key}
			{/if}

			{#if liveCaptureComplete && liveStagedCount === liveSteps.length}
				<EnrollCompleteOverlay onfinished={focusNameInput} />
			{/if}
		</div>

		{#if footageStaged.length > 0}
			<div class="mb-4 flex flex-wrap gap-2">
				{#each footageStaged as photo, index}
					<div class="relative">
						<img
							src={photo.url}
							alt="Upload {index + 1}"
							class="h-16 w-16 rounded-lg border border-border object-cover"
						/>
						<button
							type="button"
							class="absolute -right-1 -top-1 flex h-7 w-7 items-center justify-center rounded-full bg-danger text-white"
							disabled={busy}
							onclick={() => removeFootagePhoto(photo.id)}
							aria-label="Remove upload {index + 1}"
						>
							×
						</button>
					</div>
				{/each}
			</div>
		{/if}

		{#if showActionSlot}
			<div class="action-slot">
				{#if enrollJustFinished}
					<button
						type="button"
						class="action-slot-control bg-accent font-medium text-white hover:bg-accent-hover"
						onclick={startAnotherEnroll}
					>
						Add another
					</button>
				{:else if stepTimedOut}
					<button
						type="button"
						class="action-slot-control bg-accent font-medium text-white hover:bg-accent-hover"
						onclick={retryCurrentStep}
					>
						Retry step
					</button>
				{:else if showGuidedNameForm}
					<div class="action-slot-row">
						<input
							id="name"
							class="action-slot-control action-slot-input border border-border bg-bg text-text outline-none focus:border-accent"
							bind:this={nameInput}
							bind:value={name}
							placeholder="Who is this?"
							autocomplete="name"
							enterkeyhint="done"
							onkeydown={(event) => {
								if (event.key === "Enter" && !doneDisabled) {
									event.preventDefault();
									handleDoneClick();
								}
							}}
						/>
						<button
							type="button"
							class="action-slot-control action-slot-done bg-ok font-medium text-bg hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
							disabled={doneDisabled}
							onclick={handleDoneClick}
						>
							Done
						</button>
					</div>
				{:else if guidedNameStep && busyAction === "enroll"}
					<p class="action-slot-hint">Enrolling…</p>
				{:else if showFootageNameForm}
					<div class="action-slot-row">
						<input
							id="name"
							class="action-slot-control action-slot-input border border-border bg-bg text-text outline-none focus:border-accent"
							bind:this={nameInput}
							bind:value={name}
							placeholder="Who is this?"
							autocomplete="name"
							enterkeyhint="done"
							onkeydown={(event) => {
								if (event.key === "Enter" && !enrollDisabled) {
									event.preventDefault();
									void submitEnroll();
								}
							}}
						/>
						<button
							type="button"
							class="action-slot-control action-slot-done bg-ok font-medium text-bg hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
							disabled={enrollDisabled}
							onclick={handleEnrollClick}
						>
							{enrollLabel}
						</button>
					</div>
				{:else if showEnrollButton}
					<button
						type="button"
						class="action-slot-control bg-ok font-medium text-bg hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
						disabled={enrollDisabled}
						onclick={handleEnrollClick}
					>
						{enrollLabel}
					</button>
				{:else if showPhoneEnableButton}
					<button
						type="button"
						class="action-slot-control bg-accent font-medium text-white hover:bg-accent-hover"
						onclick={enablePhoneCamera}
					>
						Enable camera
					</button>
				{:else}
					<p class="action-slot-hint">
						{statusLine}
					</p>
				{/if}
			</div>
		{/if}

		{#if message}
			<div
				class="mt-3 rounded-xl px-3 py-2.5 {messageKind === 'ok'
					? 'bg-ok/20 text-ok'
					: messageKind === 'warn'
						? 'bg-warn/20 text-warn'
						: 'bg-danger/20 text-danger'}"
			>
				{message}
			</div>
		{/if}

		{#if enrolled.length > 0}
		<div class="mt-8 rounded-2xl border border-border bg-surface px-4 py-3">
			<p class="mb-2 text-muted">Enrolled</p>
			<ul class="divide-y divide-border">
				{#each enrolled as person}
					<li class="flex items-center justify-between gap-3 py-2.5">
						<span>{person.name}</span>
						<button
							type="button"
							class="rounded-xl border border-border bg-transparent px-3 py-1.5 text-text hover:bg-bg disabled:opacity-50"
							disabled={busy}
							onclick={() => removeEnrolled(person)}
						>
							Remove
						</button>
					</li>
				{/each}
			</ul>
		</div>
		{/if}
	</div>
</div>

<style>
	.action-slot {
		min-height: 3.25rem;
	}

	.action-slot-hint,
	.action-slot-control {
		box-sizing: border-box;
		width: 100%;
		min-height: 3.25rem;
		border-radius: 0.75rem;
		padding-inline: 1rem;
	}

	.action-slot-hint {
		display: flex;
		align-items: center;
		justify-content: center;
		margin: 0;
		text-align: center;
		font-weight: 500;
		line-height: 1.35;
		color: var(--color-text);
	}

	button.action-slot-control {
		display: flex;
		align-items: center;
		justify-content: center;
		padding-block: 0;
	}

	input.action-slot-control {
		display: block;
		padding-block: 0.625rem;
	}

	.action-slot-row {
		display: flex;
		gap: 0.5rem;
		width: 100%;
	}

	.action-slot-input {
		flex: 1;
		min-width: 0;
	}

	.action-slot-done {
		flex-shrink: 0;
		width: auto;
		min-width: 5.5rem;
		padding-inline: 1.25rem;
	}

	.enroll-success {
		position: absolute;
		inset: 0;
	}

	.enroll-success-tick {
		position: absolute;
		top: 50%;
		left: 50%;
		display: flex;
		height: 5rem;
		width: 5rem;
		align-items: center;
		justify-content: center;
		border-radius: 9999px;
		background: rgb(62 207 142 / 0.2);
		color: var(--color-ok);
		transform: translate(-50%, -50%);
	}

	.enroll-success-text {
		position: absolute;
		inset-inline: 0;
		top: calc(50% + 3.75rem);
		padding-inline: 1.5rem;
		text-align: center;
	}
</style>
