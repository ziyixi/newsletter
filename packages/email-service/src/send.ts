import { Resend } from "resend";
import dotenv from "dotenv";
import path from "path";
import { fileURLToPath } from "url";

// Load .env from project root (not cwd)
const __send_dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(__send_dirname, "../../../.env") });

const resend = new Resend(process.env.RESEND_API_KEY);

interface SendOptions {
  to: string;
  subject: string;
  html: string;
  text?: string;
}

/**
 * Send an email via Resend.
 * Returns the message ID on success.
 */
export async function sendEmail(opts: SendOptions): Promise<string> {
  const { data, error } = await resend.emails.send({
    from: "The Daily Briefing <onboarding@resend.dev>",
    to: opts.to,
    subject: opts.subject,
    html: opts.html,
    text: opts.text,
  });

  if (error) {
    throw new Error(`Resend error: ${error.message}`);
  }

  return data?.id ?? "unknown";
}
