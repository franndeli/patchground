import { copyFile, mkdir, rm } from "node:fs/promises";

const source = new URL("../public/", import.meta.url);
const output = new URL("../dist/", import.meta.url);
const files = ["index.html", "status.html", "styles.css", "main.js", "favicon.svg", "catalog.json"];

await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
for (const file of files) {
  await copyFile(new URL(file, source), new URL(file, output));
}
console.log(`Built ${files.length} public assets in web/dist/`);
