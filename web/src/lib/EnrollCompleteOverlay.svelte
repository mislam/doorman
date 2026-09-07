<script lang="ts">
	interface Props {
		onfinished?: () => void;
	}

	let { onfinished }: Props = $props();

	function onFillAnimationEnd(event: AnimationEvent) {
		if (event.animationName !== "complete-cycle") return;
		onfinished?.();
	}
</script>

<div class="complete-overlay" aria-hidden="true">
	<div class="complete-fill" onanimationend={onFillAnimationEnd}>
		<svg
			class="complete-tick"
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
</div>

<style>
	.complete-overlay {
		position: absolute;
		inset: 0;
		z-index: 2;
		overflow: hidden;
		pointer-events: none;
	}

	.complete-fill {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 50%;
		background: rgb(62 207 142 / 0.38);
		transform: scale(1);
		transform-origin: center;
		animation: complete-cycle 1.82s cubic-bezier(0.32, 0.94, 0.6, 1) forwards;
	}

	.complete-tick {
		width: 58%;
		height: 58%;
		color: rgb(255 255 255 / 0.98);
		opacity: 0;
		transform: scale(0.55);
		animation: complete-tick 1.82s ease-out forwards;
	}

	/* 0.42s stamp → 1s hold → 0.4s expand + fade (total 1.82s) */
	@keyframes complete-cycle {
		0% {
			transform: scale(1);
			opacity: 1;
		}
		23% {
			transform: scale(0.25);
			opacity: 1;
		}
		78% {
			transform: scale(0.25);
			opacity: 1;
		}
		100% {
			transform: scale(1);
			opacity: 0;
		}
	}

	@keyframes complete-tick {
		0% {
			opacity: 0;
			transform: scale(0.55);
		}
		14% {
			opacity: 1;
			transform: scale(1);
		}
		78% {
			opacity: 1;
			transform: scale(1);
		}
		100% {
			opacity: 0;
			transform: scale(0.85);
		}
	}
</style>
