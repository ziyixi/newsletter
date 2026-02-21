/**
 * Single entrypoint for the email-service executable (send | e2e).
 * Used when compiled to a single binary via Node SEA.
 */
import path from "path";
import dotenv from "dotenv";
import { main as sendMain } from "./send-real.js";
import { main as e2eMain } from "./e2e.js";

dotenv.config({ path: path.join(process.cwd(), ".env") });

const cmd = process.argv[2] ?? "send";
const dataPath = process.argv[3];

async function run() {
  switch (cmd) {
    case "send":
      await sendMain(dataPath);
      break;
    case "e2e":
      await e2eMain(dataPath);
      break;
    default:
      console.error(`Usage: email-service [send|e2e]`);
      process.exit(1);
  }
}

run().catch((err) => {
  console.error("❌  Failed:", err);
  process.exit(1);
});
