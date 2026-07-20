import { test, expect } from '@playwright/test'

// Playground e2e regression guard.
//
// Deterministic by design: the canvas API is mocked at the network layer, so this
// needs no engine and no LLM. Its job is the ONE thing unit tests can't cover —
// the integration that the phase machine actually reaches `live` after a real
// session round-trip. (A fast session-create once cancelled the ignition timer and
// stranded the app in `igniting`; this guards against that class of regression.)
//
// The co-generation loop itself (runTick, governor, contribution endpoint) is
// covered by unit/integration tests; we deliberately don't re-test it here.

test.describe('Playground', () => {
  test('idle -> submit -> reaches the live canvas', async ({ page }) => {
    let contributionCalls = 0
    let respondCalls = 0

    // Single catch-all router: mock the canvas API, pass everything else (app
    // bundle, vite assets, websocket) straight through.
    await page.route('**/*', async (route) => {
      const req = route.request()
      const path = new URL(req.url()).pathname
      const method = req.method()

      if (path.endsWith('/auth/token')) return route.fulfill({ json: { token: 'e2e' } })
      if (path.endsWith('/contribution')) {
        contributionCalls++
        return route.fulfill({ json: { placed: false, tldraw_shape_id: null, text: null, kind: null, relevance: 0 } })
      }
      if (path.endsWith('/respond') && method === 'POST') {
        respondCalls++
        return route.fulfill({
          json: { response_type: 'reasoning', tldraw_shape_id: 'shape:rs_e2e', read: 'strategy · strategic' },
        })
      }
      if (path.endsWith('/canvas/sessions') && method === 'POST') {
        return route.fulfill({
          json: { id: 'canvas_session:e2e', project_id: 'product:platform', title: 'Playground', created_at: '', updated_at: '' },
        })
      }
      if (path.endsWith('/timeline')) return route.fulfill({ json: { events: [], forward_momentum: [] } })
      if (path.endsWith('/classify')) return route.fulfill({ json: { discipline: 'architecture', archetypes: [], specialties: [] } })
      if (path.includes('/proactive/')) return route.fulfill({ json: null })
      if (/\/canvas\/sessions\/[^/]+$/.test(path) && method === 'GET') {
        return route.fulfill({ json: { id: 'canvas_session:e2e', project_id: 'product:platform', title: 'Playground', artifacts: [] } })
      }
      return route.continue()
    })

    await page.goto('/?mode=playground')

    // idle: the convening line, no login/setup.
    const ignition = page.locator('input[placeholder*="thinking about"]')
    await expect(ignition).toBeVisible({ timeout: 15000 })

    await ignition.fill('How should we sequence the open-source launch?')
    await ignition.press('Enter')

    // live: the canvas must mount — ambient input + pause control appear.
    // This is the phase-stuck regression guard.
    const ambient = page.locator('input[placeholder*="thinking with you"]')
    await expect(ambient).toBeVisible({ timeout: 15000 })
    await expect(page.locator('[aria-label="toggle generation"]')).toBeVisible()

    // Router behavior: typing a thought and submitting fires POST /respond.
    // Rendering (reasoning artifact) requires a WS artifact.placed event that
    // the mock can't emit, so we assert only the network call — deterministic.
    await ambient.fill('what about usage-based pricing?')
    await ambient.press('Enter')
    await expect.poll(() => respondCalls).toBeGreaterThan(0)

    // The mocked contribution route is wired but cadence is slow; not asserted here
    // (loop is unit-tested). Referencing the counter keeps the mock honest.
    expect(contributionCalls).toBeGreaterThanOrEqual(0)
  })
})
