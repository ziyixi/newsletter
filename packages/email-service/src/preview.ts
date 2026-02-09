/**
 * preview.ts
 *
 * Reads real data from a JSON file (produced by the Python backend),
 * renders the newsletter to HTML, saves it, and opens in the browser.
 *
 * Usage:  tsx src/preview.ts [path-to-json]
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { exec } from "child_process";
import { renderNewsletter } from "./render.js";
import type { NewsletterProps } from "../emails/types";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const DEFAULT_JSON = path.resolve(
  __dirname,
  "../../backend/.cache/newsletter-data.json"
);

async function main() {
  const jsonPath = process.argv[2] ?? DEFAULT_JSON;

  if (!fs.existsSync(jsonPath)) {
    console.error(`❌  Data file not found: ${jsonPath}`);
    console.error(`    Run "make fetch" first to fetch real data.`);
    process.exit(1);
  }

  console.log(`📖  Reading data from ${jsonPath}`);
  const raw = fs.readFileSync(jsonPath, "utf-8");
  const props: NewsletterProps = JSON.parse(raw);

  console.log(
    `📰  Rendering: ${props.date} · 第${props.editionNumber}期 · for ${props.recipientName}`
  );

  const html = await renderNewsletter(props);

  // Write preview HTML
  const outDir = path.resolve(__dirname, "../../.cache");
  fs.mkdirSync(outDir, { recursive: true });
  const outPath = path.join(outDir, "preview.html");
  fs.writeFileSync(outPath, html, "utf-8");

  console.log(`💾  Preview saved to ${outPath}`);
  console.log(`🌐  Opening in browser…`);

  // Open in default browser (macOS: open, Linux: xdg-open)
  const cmd =
    process.platform === "darwin"
      ? `open "${outPath}"`
      : process.platform === "win32"
        ? `start "" "${outPath}"`
        : `xdg-open "${outPath}"`;

  exec(cmd, (err) => {
    if (err) {
      console.log(`    Could not auto-open. Open manually: file://${outPath}`);
    }
  });
}

main().catch((err) => {
  console.error("❌  Preview failed:", err);
  process.exit(1);
});
