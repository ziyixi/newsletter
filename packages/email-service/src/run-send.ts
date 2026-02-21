/**
 * Dev runner for send: tsx src/run-send.ts
 * In Docker the single executable uses src/cli.ts instead.
 */
import { main } from "./send-real.js";

main(process.argv[2]).catch((err) => {
  console.error("❌  Send failed:", err);
  process.exit(1);
});
