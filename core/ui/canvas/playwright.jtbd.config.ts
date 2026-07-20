import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e/jtbd',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'list',
  globalSetup: './tests/e2e/jtbd/setup.ts',
  globalTeardown: './tests/e2e/jtbd/teardown.ts',
  use: {
    baseURL: 'http://localhost:5176',
    trace: 'on-first-retry',
    screenshot: 'on',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run dev -- --port 5176',
    url: 'http://localhost:5176',
    reuseExistingServer: true,
    timeout: 30000,
  },
})
