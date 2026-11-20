import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const kernel = fileURLToPath(new URL("./src/kernel/index.ts", import.meta.url));
const testing = fileURLToPath(new URL("./src/kernel/testing.ts", import.meta.url));

// This site's web app. `npm run dev` serves it on 5173 and sends /api to the
// site's FastAPI app on 8000; `npm run build` writes dist/, which the backend
// serves as WEB_DIST. `npm test` runs Vitest on the site's own pages: the
// kernel's and the modules' are tested where MechFrame keeps them.
export default defineConfig({
  plugins: [react()],
  // Exact names: "@/kernel" alone would also catch "@/kernel/testing".
  resolve: {
    alias: [
      { find: /^@\/kernel\/testing$/, replacement: testing },
      { find: /^@\/kernel$/, replacement: kernel },
    ],
  },
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/site/**/*.test.{ts,tsx}"],
    testTimeout: 15_000,
    restoreMocks: true,
    unstubGlobals: true,
  },
});
