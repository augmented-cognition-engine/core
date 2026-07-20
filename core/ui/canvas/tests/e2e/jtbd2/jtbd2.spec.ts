import { test, expect } from '@playwright/test'
import { loadState, waitForCanvas, screenshot } from './fixtures2'

test.beforeEach(({ page: _page }, testInfo) => {
  const state = loadState()
  if (state.skip) {
    testInfo.skip(true, 'Backend not reachable — skipped by setup2.ts')
  }
})

// ---------------------------------------------------------------------------
// JTBD-6: Both AI and user sticky notes render on the canvas
// ---------------------------------------------------------------------------
test('JTBD-6: sticky notes render for both AI and user authors', async ({ page }) => {
  const state = loadState()
  await page.goto(`/?session=${encodeURIComponent(state.jtbd6.sessionId)}`)
  await waitForCanvas(page)

  // Both sticky shapes must be visible — there are 2 so we check count
  await expect(page.locator('[data-testid="sticky-shape"]')).toHaveCount(2, { timeout: 10000 })
  await screenshot(page, 'jtbd6-01-stickies')
})

// ---------------------------------------------------------------------------
// JTBD-7: Matrix card renders correct option names and recommendation
// ---------------------------------------------------------------------------
test('JTBD-7: matrix card content — option names and recommendation visible', async ({ page }) => {
  const state = loadState()
  await page.goto(`/?session=${encodeURIComponent(state.jtbd7.sessionId)}`)
  await waitForCanvas(page)

  const card = page.locator('[data-testid="matrix-card-shape"]')
  await expect(card).toBeVisible({ timeout: 10000 })

  // Option names rendered inside the card (exact match avoids collision with recommendation text)
  await expect(card.getByText('Kafka', { exact: true }).first()).toBeVisible()
  await expect(card.getByText('Redis Streams', { exact: true }).first()).toBeVisible()

  // Recommendation text visible
  await expect(card.getByText(/throughput and replay are non-negotiable/i)).toBeVisible()

  await screenshot(page, 'jtbd7-01-matrix-content')
})

// ---------------------------------------------------------------------------
// JTBD-8: Topic cluster in launcher expands to reveal individual sessions
// ---------------------------------------------------------------------------
test('JTBD-8: topic cluster expands to show multiple sessions', async ({ page }) => {
  const state = loadState()

  await page.goto('/')
  await page.locator('button[title="Canvas"]').click()
  await page.waitForTimeout(1200)

  // Both auth sessions must be in the launcher (cluster shows ≥2 sessions count)
  // Click the cluster header to expand it
  const authCluster = page.locator('[data-testid="recent-session-item"]').filter({
    hasText: 'Security & Auth',
  })
  await expect(authCluster).toBeVisible({ timeout: 8000 })

  await screenshot(page, 'jtbd8-01-cluster-collapsed')
  await authCluster.click()

  // After expand, individual session titles should be visible
  await expect(
    page.locator('[data-testid="recent-session-item"]').filter({ hasText: '[JTBD2] Auth token refresh strategy' })
  ).toBeVisible({ timeout: 5000 })
  await expect(
    page.locator('[data-testid="recent-session-item"]').filter({ hasText: '[JTBD2] Auth middleware extraction plan' })
  ).toBeVisible({ timeout: 5000 })

  await screenshot(page, 'jtbd8-02-cluster-expanded')
})

// ---------------------------------------------------------------------------
// JTBD-9: Decision count badge shows "2" when session has 2 decisions
// ---------------------------------------------------------------------------
test('JTBD-9: decision badge shows correct count for 2 decisions', async ({ page }) => {
  const state = loadState()
  await page.goto(`/?session=${encodeURIComponent(state.jtbd9.sessionId)}`)
  await waitForCanvas(page)
  await page.locator('[data-testid="tab-ledger"]').click()

  // Badge on tab shows "2"
  await expect(page.locator('[data-testid="tab-ledger"]')).toContainText('2', { timeout: 10000 })

  // Both decision cards visible
  await expect(
    page.locator('[data-testid="decision-card"]').filter({ hasText: 'Use JWT with 15-minute expiry' })
  ).toBeVisible({ timeout: 8000 })
  await expect(
    page.locator('[data-testid="decision-card"]').filter({ hasText: 'Store refresh tokens in Redis' })
  ).toBeVisible({ timeout: 8000 })

  await screenshot(page, 'jtbd9-01-two-decisions')
})

// ---------------------------------------------------------------------------
// JTBD-10: Decision rationale is visible after expanding a decision card
// ---------------------------------------------------------------------------
test('JTBD-10: decision card shows rationale on expand', async ({ page }) => {
  const state = loadState()
  await page.goto(`/?session=${encodeURIComponent(state.jtbd10.sessionId)}`)
  await waitForCanvas(page)
  await page.locator('[data-testid="tab-ledger"]').click()

  const card = page.locator('[data-testid="decision-card"]').filter({
    hasText: 'Adopt short-lived JWT + Redis refresh',
  })
  await expect(card).toBeVisible({ timeout: 10000 })
  await screenshot(page, 'jtbd10-01-decision-collapsed')

  // Expand to reveal rationale
  await card.locator('button', { hasText: 'Expand' }).click()

  // Rationale text is now visible
  await expect(card.getByText(/HttpOnly cookie prevents XSS/)).toBeVisible({ timeout: 3000 })
  await screenshot(page, 'jtbd10-02-decision-expanded-rationale')
})
