// Playwright for the kernel's end-to-end tests (K4 contract §7): Chromium,
// against the harness with its test support and the built web app
// (`python -m harness.e2e`). Run `npm run build`, then `npm run e2e`, with
// TEST_DATABASE_URL pointing at a Postgres server's admin URL. Locally before
// each push; in CI on main's pushes, weekly and by hand (.github/workflows/e2e.yml).
import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.E2E_PORT ?? "8765");
const python = process.env.E2E_PYTHON ?? (process.platform === "win32" ? ".venv\\Scripts\\python.exe" : "python");

export default defineConfig({
  testDir: "kernel/tests/e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  reporter: "list",
  use: { baseURL: `http://localhost:${String(port)}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `"${python}" -m harness.e2e`, // quoted: an interpreter's path may hold spaces (cubic on #79)
    url: `http://localhost:${String(port)}/api/kernel/health`,
    // Never a server already running: each run starts its own on a fresh database (cubic on #79).
    reuseExistingServer: false,
    timeout: 120_000,
    env: { E2E_PORT: String(port) },
  },
});
