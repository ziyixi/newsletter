/**
 * e2e.ts — End-to-end validation script.
 *
 * Reads fetched data, renders the newsletter to HTML, and validates
 * the output WITHOUT sending any email.
 *
 * Usage:  tsx src/e2e.ts [path-to-json]
 */

import fs from "fs";
import path from "path";
import { renderNewsletter } from "./render.js";
import type { NewsletterProps } from "../emails/types";

const DEFAULT_JSON = path.join(
  process.cwd(),
  "packages/backend/.cache/newsletter-data.json"
);

export async function main(overridePath?: string) {
  const jsonPath = overridePath ?? DEFAULT_JSON;

  if (!fs.existsSync(jsonPath)) {
    console.error(`❌  Data file not found: ${jsonPath}`);
    console.error(`    Run "make fetch" first to fetch real data.`);
    process.exit(1);
  }

  console.log(`📖  Reading data from ${jsonPath}`);
  const raw = fs.readFileSync(jsonPath, "utf-8");
  const props: NewsletterProps = JSON.parse(raw);

  console.log(
    `🎨  Rendering: ${props.date} · for ${props.recipientName}`
  );

  const html = await renderNewsletter(props);

  // ── Validate ──────────────────────────────
  if (!html || html.length < 100) {
    console.error("❌  Rendered HTML is too short or empty");
    process.exit(1);
  }

  if (!html.includes("<html") && !html.includes("<!DOCTYPE")) {
    console.error("❌  Rendered HTML missing expected structure");
    process.exit(1);
  }

  // Check key sections are present
  const checks = ["天气", "新闻", "黑客新闻"];
  for (const keyword of checks) {
    if (!html.includes(keyword)) {
      console.warn(`⚠️  Missing expected content: "${keyword}"`);
    }
  }

  // Save for inspection
  const outDir = path.join(process.cwd(), ".cache");
  fs.mkdirSync(outDir, { recursive: true });
  const outPath = path.join(outDir, "e2e-output.html");
  fs.writeFileSync(outPath, html, "utf-8");

  console.log(`✅  E2E passed — ${html.length.toLocaleString()} bytes rendered`);
  console.log(`💾  Output saved to ${outPath}`);
}
