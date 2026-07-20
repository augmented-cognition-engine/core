import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e/jtbd2',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'list',
  globalSetup: './tests/e2e/jtbd2/setup2.ts',
  globalTeardown: './tests/e2e/jtbd2/teardown2.ts',
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
