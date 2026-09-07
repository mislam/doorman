<script lang="ts">
	import type { GuideDirection } from "$lib/enroll-guide";

	interface Props {
		direction: GuideDirection | null;
	}

	let { direction }: Props = $props();

	// Equilateral head + rectangular tail.
	const cx = 24;
	const side = 32;
	const headH = (side * Math.sqrt(3)) / 2;
	const tailH = headH * 0.52;
	const tailW = 13;
	const yTip = 0;
	const yBase = yTip + headH;
	const yTailEnd = yBase + tailH;
	const halfTail = tailW / 2;
	const halfSide = side / 2;

	const arrowPath = `M ${cx} ${yTip} L ${cx + halfSide} ${yBase} L ${cx + halfTail} ${yBase} L ${cx + halfTail} ${yTailEnd} L ${cx - halfTail} ${yTailEnd} L ${cx - halfTail} ${yBase} L ${cx - halfSide} ${yBase} Z`;
</script>

{#if direction}
	<div class="guide-arrow guide-arrow--{direction} guide-arrow--visible" aria-hidden="true">
		<svg class="guide-arrow-icon" viewBox="0 0 48 48" fill="currentColor">
			<path d={arrowPath} />
		</svg>
	</div>
{/if}

<style>
	.guide-arrow {
		position: absolute;
		z-index: 2;
		color: rgb(255 255 255 / 0.95);
		filter: drop-shadow(0 0 8px rgb(255 255 255 / 0.45));
		--edge-inset: 10%;
		--tip-offset: calc((11rem - 7.25rem) / 2);
		opacity: 0;
		transition: opacity 0.25s ease;
	}

	.guide-arrow--visible {
		opacity: 1;
	}

	.guide-arrow-icon {
		width: 11rem;
		height: 7.25rem;
	}

	/* Top of frame — look up (step 3) or raise head to straight (step 5). */
	.guide-arrow--up {
		top: calc(var(--edge-inset) + var(--tip-offset));
		left: 50%;
		animation: pulse-up 1.15s ease-in-out infinite;
	}

	.guide-arrow--down {
		bottom: calc(var(--edge-inset) + var(--tip-offset));
		left: 50%;
		animation: pulse-down 1.15s ease-in-out infinite;
	}

	.guide-arrow--left {
		left: var(--edge-inset);
		top: 50%;
		animation: pulse-left 1.15s ease-in-out infinite;
	}

	.guide-arrow--right {
		right: var(--edge-inset);
		top: 50%;
		animation: pulse-right 1.15s ease-in-out infinite;
	}

	@keyframes pulse-up {
		0%,
		100% {
			transform: translate(-50%, 0);
			opacity: 0.45;
		}
		50% {
			transform: translate(-50%, -34px);
			opacity: 1;
		}
	}

	@keyframes pulse-down {
		0%,
		100% {
			transform: translate(-50%, 0) rotate(180deg);
			opacity: 0.45;
		}
		50% {
			transform: translate(-50%, 34px) rotate(180deg);
			opacity: 1;
		}
	}

	@keyframes pulse-left {
		0%,
		100% {
			transform: translate(0, -50%) rotate(-90deg);
			opacity: 0.45;
		}
		50% {
			transform: translate(-34px, -50%) rotate(-90deg);
			opacity: 1;
		}
	}

	@keyframes pulse-right {
		0%,
		100% {
			transform: translate(0, -50%) rotate(90deg);
			opacity: 0.45;
		}
		50% {
			transform: translate(34px, -50%) rotate(90deg);
			opacity: 1;
		}
	}
</style>
