import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const kernel = fileURLToPath(new URL("./kernel/web/index.ts", import.meta.url));

// One Vitest run for every workspace: the kernel's web half, the harness and
// each module's web binding (modules/*/web, its tests in modules/*/tests/web).
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@/kernel": kernel } },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: [
      "kernel/web/**/*.test.{ts,tsx}",
      "harness/web/**/*.test.{ts,tsx}",
      "modules/*/web/**/*.test.{ts,tsx}",
      "modules/*/tests/web/**/*.test.{ts,tsx}",
    ],
    exclude: ["**/node_modules/**", "modules/_template/**"],
    restoreMocks: true,
  },
});
