import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'list',
  globalSetup: './tests/e2e/_global-setup.ts',
  globalTeardown: './tests/e2e/_global-teardown.ts',
  use: {
    baseURL: 'http://localhost:5176',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      // Use system Chrome via channel — the cached chromium-1208 binary
      // doesn't match the 1217 build Playwright 1.59.1 expects. System
      // Chrome works fine for verification screenshots.
      use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    },
  ],
  // Start the Vite dev server before running tests
  webServer: {
    command: 'npm run dev -- --port 5176',
    url: 'http://localhost:5176',
    reuseExistingServer: true,
    timeout: 30000,
  },
})
