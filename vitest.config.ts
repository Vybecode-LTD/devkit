import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const kernel = fileURLToPath(new URL("./kernel/web/index.ts", import.meta.url));
const testing = fileURLToPath(new URL("./kernel/web/testing.ts", import.meta.url));

// One Vitest run for every workspace: the kernel's web half, the harness and
// each module's web binding (modules/*/web, its tests in modules/*/tests/web).
export default defineConfig({
  plugins: [react()],
  // Exact names: "@/kernel" alone would also catch "@/kernel/testing".
  resolve: {
    alias: [
      { find: /^@\/kernel\/testing$/, replacement: testing },
      { find: /^@\/kernel$/, replacement: kernel },
    ],
  },
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
    unstubGlobals: true,
    // `npm run test:coverage`: the web's floor, 85 % of lines (K4 contract §7).
    coverage: {
      provider: "v8",
      include: ["kernel/web/**/*.{ts,tsx}", "harness/web/src/**/*.{ts,tsx}", "modules/*/web/**/*.{ts,tsx}"],
      exclude: [
        "**/*.test.{ts,tsx}",
        "kernel/web/src/api/schema.ts", // generated types: no code
        "harness/web/src/main.tsx", // the harness's two lines of wiring, run by Playwright
        "harness/web/src/kit.tsx", // the UI kit's page, checked by Playwright (kit.spec.ts)
        "modules/_*/**",
      ],
      thresholds: { lines: 85 },
    },
  },
});
