import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("..", import.meta.url));
const webPort = Number(process.env.SKILLBRIDGE_E2E_WEB_PORT ?? 5173);
const webOrigin = `http://localhost:${webPort}`;
export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  expect: { timeout: 15000 },
  workers: 1,
  retries: 0,
  use: {
    baseURL: webOrigin,
    trace: "off",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    {
      name: "mobile",
      use: { ...devices["Pixel 7"], defaultBrowserType: "chromium" },
    },
  ],
  webServer: [
    {
      command: ".venv/bin/python -m examples.offline_demo --port 8001",
      cwd: root,
      url: "http://127.0.0.1:8001/api/v1/health",
      reuseExistingServer: false,
      timeout: 30000,
      env: { SKILLBRIDGE_DEMO_FRONTEND_ORIGIN: webOrigin },
      gracefulShutdown: { signal: "SIGTERM", timeout: 15000 },
    },
    {
      command: `npm run dev -- --host localhost --port ${webPort} --strictPort`,
      url: webOrigin,
      reuseExistingServer: false,
      timeout: 30000,
      env: {
        VITE_API_BASE_URL: "http://127.0.0.1:8001",
        VITE_DEMO: "true",
        VITE_POLL_INTERVAL_MS: "100",
      },
    },
  ],
});
