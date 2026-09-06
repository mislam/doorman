<script lang="ts">
	import { onMount } from "svelte";
	import {
		dataUrlToBlob,
		deletePerson,
		doorbellStreamUrl,
		enrollPerson,
		listPeople,
		previewDoorbellFrame,
		scanFootage,
		streamSnapshotUrl,
		withCacheBust,
		type PersonInfo,
		type ScanFace,
	} from "$lib/api";

	type Tab = "live" | "footage";
	type Step = { id: string; label: string; hint: string };
	type StagedPhoto = { label: string; blob: Blob; url: string };

	const steps: Step[] = [
		{ id: "front", label: "Front", hint: "Face the camera straight on" },
		{ id: "left", label: "Left", hint: "Turn slightly to your left" },
		{ id: "right", label: "Right", hint: "Turn slightly to your right" },
		{ id: "door", label: "Extra", hint: "One more angle (optional)" },
	];

	type BusyAction = "" | "capture" | "enroll" | "delete";

	let tab: Tab = $state("live");
	let name = $state("");
	let stepIndex = $state(0);
	let busyAction = $state<BusyAction>("");
	let message = $state("");
	let messageKind = $state<"ok" | "warn" | "error">("ok");
	let staged = $state<Record<string, StagedPhoto>>({});
	let enrolled = $state<PersonInfo[]>([]);
	let pendingFaces = $state<ScanFace[]>([]);
	let askingName = $state(false);
	let fileInput = $state<HTMLInputElement | null>(null);
	let nameInput = $state<HTMLInputElement | null>(null);
	let streamReady = $state(false);
	let snapshotLoaded = $state(false);
	let snapshotTick = $state(0);

	const currentStep = $derived(steps[stepIndex]);
	const busy = $derived(busyAction !== "");
	const stagedCount = $derived(Object.keys(staged).length);
	const canCapture = $derived(!busy && pendingFaces.length === 0);
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
	const captureLabel = $derived(
		busyAction === "capture" ? (tab === "live" ? "Capturing…" : "Scanning…") : "Capture",
	);
	const footageHint = $derived(
		pendingFaces.length > 0 ? "Tap the matching face" : "Choose a doorbell photo or clip",
	);
	const currentPreviewUrl = $derived(staged[currentStep.id]?.url ?? "");

	onMount(() => {
		const snapshotTimer = window.setInterval(() => {
			if (!streamReady) snapshotTick += 1;
		}, 400);
		void loadEnrolled();
		return () => {
			window.clearInterval(snapshotTimer);
			clearStaged();
		};
	});

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

	function clearStaged() {
		for (const photo of Object.values(staged)) {
			URL.revokeObjectURL(photo.url);
		}
		staged = {};
	}

	function stagePhoto(label: string, blob: Blob) {
		const existing = staged[label];
		if (existing) URL.revokeObjectURL(existing.url);
		staged = {
			...staged,
			[label]: { label, blob, url: URL.createObjectURL(blob) },
		};
		showOk(`Captured ${label}`);
		if (stepIndex < steps.length - 1) stepIndex += 1;
	}

	async function captureCurrent() {
		if (!canCapture) return;
		if (tab === "footage") {
			fileInput?.click();
			return;
		}

		busyAction = "capture";
		message = "";
		try {
			const blob = await previewDoorbellFrame();
			stagePhoto(currentStep.id, blob);
		} catch (err) {
			showError(err);
		} finally {
			busyAction = "";
		}
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
				stagePhoto(currentStep.id, dataUrlToBlob(result.faces[0].crop));
				pendingFaces = [];
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
		stagePhoto(currentStep.id, dataUrlToBlob(face.crop));
		pendingFaces = [];
	}

	async function submitEnroll() {
		if (enrollDisabled || !name.trim()) return;
		busyAction = "enroll";
		message = "";
		const person = name.trim();
		const photos = Object.fromEntries(
			Object.values(staged).map((photo) => [photo.label, photo.blob]),
		);
		try {
			const result = await enrollPerson(person, photos);
			showOk(result.message);
			clearStaged();
			stepIndex = 0;
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
			queueMicrotask(() => nameInput?.focus());
			return;
		}
		void submitEnroll();
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
</script>

<div class="app">
	<header>
		<h1>Enroll</h1>
	</header>

	<div class="card">
		<div class="tabs">
			<button type="button" class:active={tab === "live"} onclick={() => (tab = "live")}>
				Live
			</button>
			<button type="button" class:active={tab === "footage"} onclick={() => (tab = "footage")}>
				Footage
			</button>
		</div>

		<div class="steps">
			{#each steps as step, index}
				<button
					type="button"
					class="step"
					class:active={index === stepIndex}
					class:done={staged[step.id]}
					onclick={() => (stepIndex = index)}
				>
					{step.label}
				</button>
			{/each}
		</div>

		<p class="hint">
			{tab === "live" ? currentStep.hint : footageHint}
		</p>

		<input
			bind:this={fileInput}
			class="file-input-hidden"
			type="file"
			accept="image/*,video/*"
			onchange={onFootageFile}
		/>

		<div class="preview">
			{#if tab === "live"}
				{#if currentPreviewUrl}
					<img src={currentPreviewUrl} alt="Captured {currentStep.label}" />
				{:else if !streamReady && !snapshotLoaded}
					<p class="preview-placeholder">Connecting to doorbell…</p>
				{/if}
				{#if !currentPreviewUrl}
					{#if streamReady}
						<img src={streamUrl} alt="Doorbell camera" />
					{:else}
						<img
							src={snapshotUrl}
							alt="Doorbell camera"
							onload={() => (snapshotLoaded = true)}
							onerror={() => (snapshotLoaded = false)}
						/>
						<img
							class="stream-preload"
							src={streamUrl}
							alt=""
							onload={() => (streamReady = true)}
						/>
					{/if}
				{/if}
			{:else if pendingFaces.length > 0}
				<div class="face-grid face-grid--preview">
					{#each pendingFaces as face}
						<button type="button" disabled={busy} onclick={() => pickFootageFace(face)}>
							<img src={face.thumbnail} alt="Detected face" />
						</button>
					{/each}
				</div>
			{:else if currentPreviewUrl}
				<img src={currentPreviewUrl} alt="Captured {currentStep.label}" />
			{:else}
				<p class="preview-placeholder">Tap Capture below</p>
			{/if}
		</div>

		<button class="capture-btn" disabled={!canCapture} onclick={captureCurrent}>
			{captureLabel}
		</button>

		{#if askingName}
			<input
				id="name"
				class="enroll-name-input"
				bind:this={nameInput}
				bind:value={name}
				placeholder="Who is this?"
				autocomplete="off"
			/>
		{/if}

		<button class="capture-btn enroll-btn" disabled={enrollDisabled} onclick={handleEnrollClick}>
			{enrollLabel}
		</button>

		{#if message}
			<div class="message {messageKind}">{message}</div>
		{/if}
	</div>

	{#if enrolled.length > 0}
		<div class="card card--compact">
			<p class="section-label">Enrolled</p>
			<ul class="people-list">
				{#each enrolled as person}
					<li>
						<span>{person.name}</span>
						<button class="secondary" disabled={busy} onclick={() => removeEnrolled(person)}>
							Remove
						</button>
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</div>
