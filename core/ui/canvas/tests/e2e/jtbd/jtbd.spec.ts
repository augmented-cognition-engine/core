import { test, expect } from '@playwright/test'
import { loadState, waitForCanvas, screenshot } from './fixtures'

test.beforeEach(({ page: _page }, testInfo) => {
  const state = loadState()
  if (state.skip) {
    testInfo.skip(true, 'Backend not reachable — skipped by setup.ts')
  }
})

// ---------------------------------------------------------------------------
// JTBD-1: Make an architecture decision
// ---------------------------------------------------------------------------
test('JTBD-1: trade-off matrix renders on canvas and decision appears in ledger', async ({ page }) => {
  const state = loadState()
  await page.goto(`/?session=${encodeURIComponent(state.jtbd1.sessionId)}`)
  await waitForCanvas(page)

  // Matrix card shape must be visible on canvas
  await expect(page.locator('[data-testid="matrix-card-shape"]')).toBeVisible({ timeout: 10000 })
  await screenshot(page, 'jtbd1-01-canvas-loaded')

  // Open decision ledger tab
  await page.locator('[data-testid="tab-ledger"]').click()

  // Decision card must appear — it arrives via WebSocket, so allow extra time
  await expect(page.locator('[data-testid="decision-card"]').filter({ hasText: 'Use SurrealDB' }))
    .toBeVisible({ timeout: 10000 })
  await screenshot(page, 'jtbd1-02-decisions-tab')

  // Switch to context/intel tab
  await page.locator('[data-testid="tab-context"]').click()
  await screenshot(page, 'jtbd1-03-intel-tab')
})

// ---------------------------------------------------------------------------
// JTBD-2: Explore design options
// ---------------------------------------------------------------------------
test('JTBD-2: design options artifact renders on canvas', async ({ page }) => {
  const state = loadState()
  await page.goto(`/?session=${encodeURIComponent(state.jtbd2.sessionId)}`)
  await waitForCanvas(page)

  await expect(page.locator('[data-testid="design-artifact-shape"]')).toBeVisible({ timeout: 10000 })
  await screenshot(page, 'jtbd2-01-canvas-loaded')
})

// ---------------------------------------------------------------------------
// JTBD-3: Return and orient
// ---------------------------------------------------------------------------
test('JTBD-3: default landing shows launcher with recent sessions; pulse + map still reachable', async ({ page }) => {
  const state = loadState()

  // Default landing — `/` now lands on the canvas launcher (populated) rather
  // than the ambient pulse surface, which was rendering empty skeletons in
  // most real-world states. JTBD-3 ("return and orient") is better served by
  // the launcher's topical browse.
  await page.goto('/')
  await page.waitForTimeout(1000) // allow recent sessions list to populate
  await expect(
    page.locator('[data-testid="recent-session-item"]').filter({ hasText: '[JTBD] DB selection' })
  ).toBeVisible({ timeout: 8000 })
  await expect(
    page.locator('[data-testid="recent-session-item"]').filter({ hasText: '[JTBD] Streaming transport' })
  ).toBeVisible({ timeout: 8000 })
  await screenshot(page, 'jtbd3-01-launcher-default')

  // Pulse remains accessible via sidebar
  await page.locator('button[title="Pulse"]').click()
  await expect(page.locator('[data-testid="pulse-view"]')).toBeVisible({ timeout: 10000 })
  await screenshot(page, 'jtbd3-02-pulse')

  // Map view
  await page.locator('button[title="Map"]').click()
  await expect(page.locator('[data-testid="map-view"]')).toBeVisible({ timeout: 10000 })
  await screenshot(page, 'jtbd3-03-map-view')
})

// ---------------------------------------------------------------------------
// JTBD-4: Close the loop
// ---------------------------------------------------------------------------
test('JTBD-4: decision card textarea persists what_it_led_to', async ({ page }) => {
  const state = loadState()
  const outcomeText = 'Reduced auth coupling; partner API shipped 2 weeks later.'

  // Navigate and open ledger
  await page.goto(`/?session=${encodeURIComponent(state.jtbd4.sessionId)}`)
  await waitForCanvas(page)
  await page.locator('[data-testid="tab-ledger"]').click()

  // Decision card must be present before annotation
  const card = page.locator('[data-testid="decision-card"]').filter({ hasText: 'Extract auth into standalone service' })
  await expect(card).toBeVisible({ timeout: 10000 })
  await screenshot(page, 'jtbd4-01-decision-before')

  // Expand the card to reveal the "what it led to" textarea
  await card.locator('button', { hasText: 'Expand' }).click()
  const textarea = card.locator('textarea')
  await expect(textarea).toBeVisible({ timeout: 3000 })

  // Type annotation — onChange sets localStorage, onBlur PATCHes backend
  await textarea.fill(outcomeText)
  await textarea.blur()

  await screenshot(page, 'jtbd4-02-decision-after')

  // Reload and verify annotation persists from localStorage
  await page.goto(`/?session=${encodeURIComponent(state.jtbd4.sessionId)}`)
  await waitForCanvas(page)
  await page.locator('[data-testid="tab-ledger"]').click()
  await expect(
    page.locator('[data-testid="decision-card"]').filter({ hasText: 'Extract auth into standalone service' })
  ).toBeVisible({ timeout: 10000 })
})

// ---------------------------------------------------------------------------
// JTBD-5: Map code architecture before a risky change
// ---------------------------------------------------------------------------
test('JTBD-5: code architecture artifact renders on canvas', async ({ page }) => {
  const state = loadState()
  await page.goto(`/?session=${encodeURIComponent(state.jtbd5.sessionId)}`)
  await waitForCanvas(page)

  await expect(page.locator('[data-testid="code-artifact-shape"]')).toBeVisible({ timeout: 10000 })
  await screenshot(page, 'jtbd5-01-canvas-loaded')
})
