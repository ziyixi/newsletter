#!/usr/bin/env node
/**
 * Bundle email-service into a single CJS file for Node SEA.
 * Run from package root: node build-bundle.mjs
 */
import * as esbuild from "esbuild";
import { mkdirSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const outDir = join(__dirname, "dist");
mkdirSync(outDir, { recursive: true });

await esbuild.build({
  entryPoints: [join(__dirname, "src", "cli.ts")],
  bundle: true,
  platform: "node",
  format: "cjs",
  outfile: join(outDir, "email-service.cjs"),
  target: "node20",
  sourcemap: false,
  minify: false,
});

console.log("Bundled to dist/email-service.cjs");
