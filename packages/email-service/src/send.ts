import { Resend } from "resend";
import dotenv from "dotenv";
import path from "path";

// Load .env from project root (cwd when run from repo or Docker /app)
dotenv.config({ path: path.join(process.cwd(), ".env") });

let _resend: InstanceType<typeof Resend> | null = null;
function getResend(): InstanceType<typeof Resend> {
  if (!_resend) _resend = new Resend(process.env.RESEND_API_KEY);
  return _resend;
}

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
  const { data, error } = await getResend().emails.send({
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
