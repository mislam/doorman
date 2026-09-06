<script lang="ts">
	import { onMount } from "svelte";
	import {
		captureFromStream,
		capturePhoto,
		dataUrlToBlob,
		deletePerson,
		doorbellStreamUrl,
		listPeople,
		rebuildGallery,
		scanFootage,
		streamSnapshotUrl,
		withCacheBust,
		type CaptureResult,
		type PersonInfo,
		type ScanFace,
	} from "$lib/api";

	type Tab = "live" | "footage";
	type Step = { id: string; label: string; hint: string };

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
	let captures = $state<Record<string, string>>({});
	let people = $state<PersonInfo[]>([]);
	let pendingFaces = $state<ScanFace[]>([]);
	let fileInput = $state<HTMLInputElement | null>(null);
	let streamReady = $state(false);
	let snapshotLoaded = $state(false);
	let snapshotTick = $state(0);

	const currentStep = $derived(steps[stepIndex]);
	const busy = $derived(busyAction !== "");
	const canCapture = $derived(name.trim().length > 0 && !busy && pendingFaces.length === 0);
	const streamUrl = $derived(doorbellStreamUrl());
	const snapshotUrl = $derived(withCacheBust(streamSnapshotUrl(), snapshotTick));
	const captureLabel = $derived(
		busyAction === "capture" ? (tab === "live" ? "Capturing…" : "Scanning…") : "Capture",
	);
	const footageHint = $derived(
		pendingFaces.length > 0 ? "Tap the matching face" : "Choose a doorbell photo or clip",
	);

	onMount(() => {
		const snapshotTimer = window.setInterval(() => {
			if (!streamReady) snapshotTick += 1;
		}, 400);
		void loadPeople();
		return () => window.clearInterval(snapshotTimer);
	});

	async function loadPeople() {
		try {
			people = await listPeople();
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

	function handleCaptureResult(result: CaptureResult) {
		if (result.ok) {
			captures = { ...captures, [result.label]: result.filename };
			showOk(`Saved ${result.label}`);
			if (stepIndex < steps.length - 1) stepIndex += 1;
		} else {
			showWarn(result.message);
		}
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
			const result = await captureFromStream(name.trim(), currentStep.id);
			handleCaptureResult(result);
			people = await listPeople();
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
		if (!file || !name.trim()) return;

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
				await saveFootageFace(result.faces[0]);
				return;
			}
			pendingFaces = result.faces;
		} catch (err) {
			showError(err);
		} finally {
			busyAction = "";
		}
	}

	async function saveFootageFace(face: ScanFace) {
		busyAction = "capture";
		try {
			const result = await capturePhoto(name.trim(), currentStep.id, dataUrlToBlob(face.crop));
			handleCaptureResult(result);
			people = await listPeople();
			pendingFaces = [];
		} catch (err) {
			showError(err);
		} finally {
			busyAction = "";
		}
	}

	async function enrollNow() {
		busyAction = "enroll";
		message = "";
		try {
			const result = await rebuildGallery();
			showOk(result.message);
		} catch (err) {
			showError(err);
		} finally {
			busyAction = "";
		}
	}

	async function removePerson(person: PersonInfo) {
		if (!confirm(`Delete ${person.name} and all their photos?`)) return;
		busyAction = "delete";
		try {
			await deletePerson(person.id);
			people = await listPeople();
			showOk(`Deleted ${person.name}`);
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
		<label for="name">Name</label>
		<input id="name" bind:value={name} placeholder="Who is this?" autocomplete="off" />

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
					class:done={captures[step.id]}
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
				{#if !streamReady && !snapshotLoaded}
					<p class="preview-placeholder">Connecting to doorbell…</p>
				{/if}
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
			{:else if pendingFaces.length > 0}
				<div class="face-grid face-grid--preview">
					{#each pendingFaces as face}
						<button type="button" disabled={busy} onclick={() => saveFootageFace(face)}>
							<img src={face.thumbnail} alt="Detected face" />
						</button>
					{/each}
				</div>
			{:else}
				<p class="preview-placeholder">
					{Object.keys(captures).length > 0 ? "Next angle" : "Tap Capture below"}
				</p>
			{/if}
		</div>

		<button class="capture-btn" disabled={!canCapture} onclick={captureCurrent}>
			{captureLabel}
		</button>

		{#if message}
			<div class="message {messageKind}">{message}</div>
		{/if}
	</div>

	<div class="card card--compact">
		<button class="capture-btn" disabled={busy} onclick={enrollNow}>
			{busyAction === "enroll" ? "Enrolling…" : "Enroll"}
		</button>
		<p class="hint hint--tight">Rebuild recognition after adding photos.</p>
	</div>

	{#if people.length > 0}
		<div class="card card--compact">
			<ul class="people-list">
				{#each people as person}
					<li>
						<span>{person.name} <small>({person.photos.length})</small></span>
						<button class="secondary" disabled={busy} onclick={() => removePerson(person)}>
							Delete
						</button>
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</div>
