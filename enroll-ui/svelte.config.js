import adapter from "@sveltejs/adapter-static"
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte"

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter({
			pages: "../worker/static/enroll",
			assets: "../worker/static/enroll",
			fallback: "index.html",
		}),
		paths: {
			base: "/enroll",
		},
	},
}

export default config
