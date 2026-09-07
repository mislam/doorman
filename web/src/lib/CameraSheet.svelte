<script lang="ts">
	import { isPhoneCameraSupported } from "$lib/phone-camera";

	export type CameraSource = "doorbell" | "phone";

	type Props = {
		open: boolean;
		current: CameraSource;
		onselect: (source: CameraSource) => void;
		onclose: () => void;
	};

	let { open, current, onselect, onclose }: Props = $props();

	const phoneAvailable = isPhoneCameraSupported();

	function pick(source: CameraSource) {
		if (source === "phone" && !phoneAvailable) return;
		onselect(source);
		onclose();
	}
</script>

{#if open}
	<button
		type="button"
		class="fixed inset-0 z-40 bg-black/60"
		aria-label="Close"
		onclick={onclose}
	></button>
	<div
		class="fixed inset-x-0 bottom-0 z-50 mx-auto max-w-xl rounded-t-2xl border border-border bg-surface px-4 pb-6 pt-3 shadow-xl"
		role="dialog"
		aria-label="Choose camera"
	>
		<p class="mb-3 text-center font-medium text-muted">Choose camera</p>
		<div class="flex flex-col gap-2">
			<button
				type="button"
				class="rounded-xl px-4 py-3.5 text-left transition-colors {current === 'doorbell'
					? 'bg-accent/15 ring-1 ring-accent'
					: 'bg-bg hover:bg-bg/80'}"
				onclick={() => pick("doorbell")}
			>
				<span class="block font-medium text-text">Doorbell</span>
				<span class="mt-0.5 block text-muted">Best for recognition at the door</span>
			</button>
			<button
				type="button"
				class="rounded-xl px-4 py-3.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60 {current ===
				'phone'
					? 'bg-accent/15 ring-1 ring-accent'
					: 'bg-bg hover:bg-bg/80'}"
				disabled={!phoneAvailable}
				onclick={() => pick("phone")}
			>
				<span class="block font-medium text-text">Phone</span>
				<span class="mt-0.5 block text-muted">
					{#if phoneAvailable}
						Easier solo enroll — add doorbell photos later
					{:else}
						Needs HTTPS — use Upload for phone photos on this network
					{/if}
				</span>
			</button>
			<button
				type="button"
				class="mt-1 rounded-xl px-4 py-3 font-medium text-muted hover:text-text"
				onclick={onclose}
			>
				Cancel
			</button>
		</div>
	</div>
{/if}
