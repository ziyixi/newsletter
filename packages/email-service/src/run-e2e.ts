/**
 * Dev runner for e2e: tsx src/run-e2e.ts
 * In Docker the single executable uses src/cli.ts instead.
 */
import { main } from "./e2e.js";

main(process.argv[2]).catch((err) => {
  console.error("❌  E2E failed:", err);
  process.exit(1);
});
