import * as grpc from "@grpc/grpc-js";
import * as protoLoader from "@grpc/proto-loader";
import path from "path";
import { fileURLToPath } from "url";
import "dotenv/config";

import { renderNewsletter, renderNewsletterText } from "./render.js";
import { sendEmail } from "./send.js";
import { mapProtoToProps } from "./proto-mapper.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ─────────────────────────────────────────────
// Load proto definition
// ─────────────────────────────────────────────

const PROTO_PATH = path.resolve(__dirname, "../../protos/newsletter.proto");
const PORT = process.env.GRPC_PORT ?? "50051";

const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});

const proto = grpc.loadPackageDefinition(packageDefinition) as any;

// ─────────────────────────────────────────────
// Service implementation
// ─────────────────────────────────────────────

async function sendNewsletter(
  call: grpc.ServerUnaryCall<any, any>,
  callback: grpc.sendUnaryData<any>
) {
  try {
    const { props, recipientEmail } = mapProtoToProps(call.request);

    console.log(
      `📬  Rendering newsletter for ${recipientEmail} (Edition #${props.editionNumber})…`
    );

    const [html, text] = await Promise.all([
      renderNewsletter(props),
      renderNewsletterText(props),
    ]);

    const subject = `☀ 每日简报 — ${props.date}`;
    const messageId = await sendEmail({
      to: recipientEmail,
      subject,
      html,
      text,
    });

    console.log(`✅  Sent! Message ID: ${messageId}`);
    callback(null, { success: true, message_id: messageId, error: "" });
  } catch (err: any) {
    console.error("❌  Send failed:", err.message);
    callback(null, {
      success: false,
      message_id: "",
      error: err.message,
    });
  }
}

// ─────────────────────────────────────────────
// Start server
// ─────────────────────────────────────────────

const server = new grpc.Server();
server.addService(proto.newsletter.NewsletterService.service, {
  SendNewsletter: sendNewsletter,
});

server.bindAsync(
  `0.0.0.0:${PORT}`,
  grpc.ServerCredentials.createInsecure(),
  (err, port) => {
    if (err) {
      console.error("Failed to bind gRPC server:", err);
      process.exit(1);
    }
    console.log(`🚀  Newsletter gRPC server listening on port ${port}`);
  }
);
