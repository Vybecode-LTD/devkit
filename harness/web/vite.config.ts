import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const kernel = fileURLToPath(new URL("../../kernel/web/index.ts", import.meta.url));

// The harness's web app. `npm run dev` serves it on 5173 and sends /api to the
// harness's FastAPI app on 8000 (`python -m uvicorn harness.main:app`).
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@/kernel": kernel } },
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
});
