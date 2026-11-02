import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  site: "https://patchground.dev",
  // status.astro → status.html, so links stay `./status.html` and need no server-side routing.
  build: { format: "file", inlineStylesheets: "never" },
  devToolbar: { enabled: false },
  vite: { plugins: [tailwindcss()] },
});
