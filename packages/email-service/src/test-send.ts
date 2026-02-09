/**
 * test-send.ts
 *
 * One-shot script: renders the newsletter with fake data and sends it
 * via Resend. Useful for testing the full pipeline without the Python backend.
 *
 * Usage:  yarn workspace email-service send:test
 * Requires: RESEND_API_KEY and RECIPIENT_EMAIL in .env
 */

import dotenv from "dotenv";
import path from "path";
import { fileURLToPath } from "url";

// Load .env from project root
const __ts_dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(__ts_dirname, "../../../.env") });

import { renderNewsletter, renderNewsletterText } from "./render.js";
import { sendEmail } from "./send.js";
import { fakeData } from "../emails/fixtures/fake-data.js";

async function main() {
  const recipientEmail =
    process.env.RECIPIENT_EMAIL ?? "delivered@resend.dev";

  console.log(`📬  Rendering newsletter with fake data…`);
  const [html, text] = await Promise.all([
    renderNewsletter(fakeData),
    renderNewsletterText(fakeData),
  ]);

  console.log(`📨  Sending to ${recipientEmail}…`);
  const subject = `☀ 每日简报 — ${fakeData.date}`;
  const messageId = await sendEmail({
    to: recipientEmail,
    subject,
    html,
    text,
  });

  console.log(`✅  Sent! Message ID: ${messageId}`);
}

main().catch((err) => {
  console.error("❌  Failed:", err);
  process.exit(1);
});
