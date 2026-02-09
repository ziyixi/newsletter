#!/usr/bin/env node
/**
 * Reads newsletter.config.yaml and generates template-config.ts
 * for the email-service frontend.
 *
 * Usage: node scripts/sync-config.mjs
 */

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse as parseYaml } from "yaml";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");

const configPath = resolve(ROOT, "newsletter.config.yaml");
const outPath = resolve(
  ROOT,
  "packages/email-service/emails/template-config.ts"
);

const config = parseYaml(readFileSync(configPath, "utf-8"));

const sectionsJson = JSON.stringify(config.sections, null, 2)
  .split("\n")
  .map((line, i) => (i === 0 ? line : "  " + line))
  .join("\n");

const output = `// ─────────────────────────────────────────────
// AUTO-GENERATED from newsletter.config.yaml
// Do not edit — run \`make sync-config\` to refresh.
// ─────────────────────────────────────────────

export interface SectionDef {
  /** Unique key — matches a key in the section registry */
  id: string;
  /** Human-readable label (for logging / debugging) */
  label: string;
}

export interface TemplateConfig {
  /** Newsletter title shown in the masthead */
  title: string;
  /** Tagline (supports {recipientName} placeholder) */
  tagline: string;
  /** Ordered list of sections to render */
  sections: SectionDef[];
}

export const templateConfig: TemplateConfig = {
  title: ${JSON.stringify(config.newsletter.title)},
  tagline: ${JSON.stringify(config.newsletter.tagline)},
  sections: ${sectionsJson},
};
`;

writeFileSync(outPath, output, "utf-8");
console.log("✅  template-config.ts synced from newsletter.config.yaml");
