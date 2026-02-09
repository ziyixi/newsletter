/**
 * send-real.ts
 *
 * Reads real data from a JSON file (produced by the Python backend),
 * renders the newsletter, and sends it via Resend.
 *
 * Usage:  tsx src/send-real.ts [path-to-json]
 * Requires: RESEND_API_KEY and RECIPIENT_EMAIL in .env
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import dotenv from "dotenv";
import { renderNewsletter, renderNewsletterText } from "./render.js";
import { sendEmail } from "./send.js";
import type { NewsletterProps } from "../emails/types";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Load .env from project root
dotenv.config({ path: path.resolve(__dirname, "../../../.env") });

const DEFAULT_JSON = path.resolve(
  __dirname,
  "../../backend/.cache/newsletter-data.json"
);

async function main() {
  const jsonPath = process.argv[2] ?? DEFAULT_JSON;
  const recipientEmail =
    process.env.RECIPIENT_EMAIL ?? "delivered@resend.dev";

  if (!fs.existsSync(jsonPath)) {
    console.error(`❌  Data file not found: ${jsonPath}`);
    console.error(`    Run "make fetch" first to fetch real data.`);
    process.exit(1);
  }

  console.log(`📖  Reading data from ${jsonPath}`);
  const raw = fs.readFileSync(jsonPath, "utf-8");
  const props: NewsletterProps = JSON.parse(raw);

  console.log(
    `📰  Rendering: ${props.date} · for ${props.recipientName}`
  );

  const [html, text] = await Promise.all([
    renderNewsletter(props),
    renderNewsletterText(props),
  ]);

  const subject = `☀ 每日简报 — ${props.date}`;

  console.log(`📨  Sending to ${recipientEmail}…`);
  const messageId = await sendEmail({
    to: recipientEmail,
    subject,
    html,
    text,
  });

  console.log(`✅  Sent! Message ID: ${messageId}`);
}

main().catch((err) => {
  console.error("❌  Send failed:", err);
  process.exit(1);
});
