// Playwright for this site's end-to-end tests: Chromium, against the site's app
// and its built web app (`python backend/tests/e2e_server.py`). Run
// `npm run build`, then `npm run e2e`, with TEST_DATABASE_URL pointing at a
// Postgres server's admin URL. Once on a new machine: `npx playwright install chromium`.
import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.E2E_PORT ?? "8766");
const python = process.env.E2E_PYTHON ?? (process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python");

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  reporter: "list",
  use: { baseURL: `http://localhost:${String(port)}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `"${python}" ../backend/tests/e2e_server.py`, // quoted: a path may hold spaces
    url: `http://localhost:${String(port)}/api/kernel/health`,
    // Never a server already running: each run starts its own on a fresh database.
    reuseExistingServer: false,
    timeout: 120_000,
    env: { E2E_PORT: String(port), PYTHONPATH: "../backend" },
  },
});
