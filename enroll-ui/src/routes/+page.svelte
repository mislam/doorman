<script lang="ts">
	import { onMount } from "svelte";
	import {
		captureFromStream,
		deletePerson,
		doorbellStreamUrl,
		listPeople,
		rebuildGallery,
		saveCrops,
		scanFootage,
		streamSnapshotUrl,
		testRecognize,
		withCacheBust,
		type CaptureResult,
		type PersonInfo,
		type RecognizeResult,
		type ScanFace,
	} from "$lib/api";

	type Tab = "live" | "footage";
	type Step = { id: string; label: string; hint: string };

	const steps: Step[] = [
		{ id: "front", label: "Front", hint: "Stand at the door — look straight at the camera" },
		{ id: "left", label: "Left", hint: "Turn slightly to your left" },
		{ id: "right", label: "Right", hint: "Turn slightly to your right" },
		{ id: "door", label: "Extra", hint: "One more angle (optional)" },
	];

	type BusyAction = "" | "capture" | "enroll" | "recognize" | "scan" | "save" | "delete";

	let tab: Tab = $state("live");
	let name = $state("");
	let stepIndex = $state(0);
	let busyAction = $state<BusyAction>("");
	let message = $state("");
	let messageKind = $state<"ok" | "warn" | "error">("ok");
	let captures = $state<Record<string, string>>({});
	let people = $state<PersonInfo[]>([]);

	let scanSessionId = $state("");
	let scanFaces = $state<ScanFace[]>([]);
	let selectedFaceIds = $state<Set<string>>(new Set());
	let uploadFile: File | null = $state(null);
	let streamReady = $state(false);
	let snapshotLoaded = $state(false);
	let snapshotTick = $state(0);
	let lastRecognize = $state<RecognizeResult | null>(null);

	const currentStep = $derived(steps[stepIndex]);
	const busy = $derived(busyAction !== "");
	const canCapture = $derived(name.trim().length > 0 && !busy);
	const streamUrl = $derived(doorbellStreamUrl());
	const snapshotUrl = $derived(withCacheBust(streamSnapshotUrl(), snapshotTick));

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
			showOk(result.message);
			if (stepIndex < steps.length - 1) stepIndex += 1;
		} else {
			showWarn(result.message);
		}
	}

	async function captureCurrent() {
		if (!canCapture) return;
		busyAction = "capture";
		message = "";
		try {
			const person = name.trim().toLowerCase();
			const result = await captureFromStream(person, currentStep.id);
			handleCaptureResult(result);
			people = await listPeople();
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

	function formatRecognizeResult(result: RecognizeResult): string {
		if (result.names.length > 0) {
			const names = result.names.join(", ");
			if (result.unknown > 0) {
				return `Recognized: ${names} (${result.unknown} unknown)`;
			}
			return `Recognized: ${names}`;
		}
		if (result.unknown > 0) {
			return `Unknown visitor (${result.unknown} face(s))`;
		}
		return "No faces detected";
	}

	function recognizeKind(result: RecognizeResult): "ok" | "warn" {
		return result.names.length > 0 ? "ok" : "warn";
	}

	async function runTestRecognize() {
		busyAction = "recognize";
		message = "";
		lastRecognize = null;
		try {
			lastRecognize = await testRecognize();
		} catch (err) {
			showError(err);
		} finally {
			busyAction = "";
		}
	}

	async function refreshPeople() {
		try {
			people = await listPeople();
		} catch (err) {
			showError(err);
		}
	}

	async function removePerson(personName: string) {
		if (!confirm(`Delete ${personName} and all their photos?`)) return;
		busyAction = "delete";
		try {
			await deletePerson(personName);
			people = await listPeople();
			showOk(`Deleted ${personName}`);
		} catch (err) {
			showError(err);
		} finally {
			busyAction = "";
		}
	}

	function toggleFace(id: string) {
		const next = new Set(selectedFaceIds);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selectedFaceIds = next;
	}

	async function handleUpload() {
		if (!uploadFile) return;
		busyAction = "scan";
		message = "";
		scanFaces = [];
		selectedFaceIds = new Set();
		try {
			const result = await scanFootage(uploadFile);
			scanSessionId = result.session_id;
			scanFaces = result.faces;
			showOk(`Found ${result.faces.length} face(s) — tap to select`);
		} catch (err) {
			showError(err);
		} finally {
			busyAction = "";
		}
	}

	async function saveSelectedFaces() {
		if (!name.trim() || selectedFaceIds.size === 0 || !scanSessionId) return;
		busyAction = "save";
		try {
			const result = await saveCrops(
				scanSessionId,
				name.trim().toLowerCase(),
				Array.from(selectedFaceIds),
			);
			showOk(result.message);
			people = await listPeople();
			scanFaces = [];
			selectedFaceIds = new Set();
			uploadFile = null;
		} catch (err) {
			showError(err);
		} finally {
			busyAction = "";
		}
	}

	function onFileChange(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		uploadFile = input.files?.[0] ?? null;
	}
</script>

<div class="app">
	<header>
		<h1>Doorface Enroll</h1>
		<p>Live capture uses your doorbell camera. From footage uploads saved recordings.</p>
	</header>

	<div class="tabs">
		<button class:active={tab === "live"} onclick={() => (tab = "live")}>Live capture</button>
		<button class:active={tab === "footage"} onclick={() => (tab = "footage")}>From footage</button>
	</div>

	{#if tab === "live"}
		<div class="card">
			<label for="name">Person name</label>
			<input id="name" bind:value={name} placeholder="alice" autocomplete="off" />

			<div class="steps">
				{#each steps as step, index}
					<div
						class="step"
						class:active={index === stepIndex}
						class:done={captures[step.id]}
					>
						{step.label}
					</div>
				{/each}
			</div>

			<p class="hint">{currentStep.hint}</p>

			<div class="preview">
				{#if !streamReady && !snapshotLoaded}
					<p class="preview-loading">Connecting to camera…</p>
				{/if}
				{#if streamReady}
					<img src={streamUrl} alt="Doorbell camera stream" />
				{:else}
					<img
						src={snapshotUrl}
						alt="Doorbell camera snapshot"
						onload={() => (snapshotLoaded = true)}
						onerror={() => (snapshotLoaded = false)}
					/>
					<!-- Preload MJPEG; switch when first frame arrives -->
					<img
						class="stream-preload"
						src={streamUrl}
						alt=""
						onload={() => (streamReady = true)}
					/>
				{/if}
			</div>

			<div class="actions">
				<button disabled={!canCapture} onclick={captureCurrent}>
					{busyAction === "capture" ? "Capturing…" : "Capture from stream"}
				</button>
				{#if stepIndex > 0}
					<button class="secondary" disabled={busy} onclick={() => (stepIndex -= 1)}>Back</button>
				{/if}
				{#if stepIndex < steps.length - 1}
					<button class="secondary" disabled={busy} onclick={() => (stepIndex += 1)}>Skip</button>
				{/if}
			</div>

			{#if Object.keys(captures).length > 0}
				<div class="thumbs">
					{#each steps as step}
						{#if captures[step.id]}
							<div class="thumb">{step.label}<br />{captures[step.id]}</div>
						{/if}
					{/each}
				</div>
			{/if}
		</div>
	{:else}
		<div class="card">
			<label for="footage-name">Person name</label>
			<input id="footage-name" bind:value={name} placeholder="jane" autocomplete="off" />

			<label class="drop-zone">
				<input type="file" accept="image/*,video/*" onchange={onFileChange} />
				{#if uploadFile}
					{uploadFile.name}
				{:else}
					Tap to upload video or photo from Reolink export
				{/if}
			</label>

			<div class="actions">
				<button disabled={!uploadFile || busy} onclick={handleUpload}>
					{busyAction === "scan" ? "Scanning…" : "Scan for faces"}
				</button>
			</div>

			{#if scanFaces.length > 0}
				<div class="face-grid">
					{#each scanFaces as face}
						<button
							type="button"
							class:selected={selectedFaceIds.has(face.id)}
							onclick={() => toggleFace(face.id)}
						>
							<img src={face.thumbnail} alt="Detected face" />
						</button>
					{/each}
				</div>
				<div class="actions">
					<button
						disabled={!name.trim() || selectedFaceIds.size === 0 || busy}
						onclick={saveSelectedFaces}
					>
						Save selected
					</button>
				</div>
			{/if}
		</div>
	{/if}

	<div class="card">
		<p class="hint">Rebuild embeddings after photo changes. Test recognize grabs live frames like a doorbell ring.</p>
		<div class="actions">
			<button disabled={busy} onclick={enrollNow}>
				{busyAction === "enroll" ? "Enrolling…" : "Enroll now (rebuild gallery)"}
			</button>
			<button class="secondary" disabled={busy} onclick={runTestRecognize}>
				{busyAction === "recognize" ? "Recognizing…" : "Test recognize"}
			</button>
		</div>
		{#if lastRecognize}
			<div class="message {recognizeKind(lastRecognize)}">
				{formatRecognizeResult(lastRecognize)}
			</div>
		{/if}
		{#if message}
			<div class="message {messageKind}">{message}</div>
		{/if}
	</div>

	<div class="card">
		<div class="people-header">
			<strong>Enrolled people</strong>
			<button class="secondary" onclick={refreshPeople}>Refresh</button>
		</div>
		{#if people.length === 0}
			<p class="empty">No one enrolled yet.</p>
		{:else}
			<ul class="people-list">
				{#each people as person}
					<li>
						<span>{person.name} <small>({person.photos.length})</small></span>
						<button class="secondary" onclick={() => removePerson(person.name)}>Delete</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>
