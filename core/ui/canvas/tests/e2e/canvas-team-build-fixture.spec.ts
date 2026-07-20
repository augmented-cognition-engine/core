/**
 * Visual verification of the canvas team-build surface via the
 * `?debug=team-build-fixture` flag that dispatches a deterministic event
 * sequence into useBuildRun after the canvas mounts.
 *
 * Captures both light + dark canvas mode so the dual-mode paper-card
 * design (light cards on dark canvas, dark cards on light canvas) can be
 * eyeballed by reviewers and used as a visual regression artifact.
 *
 * Mocks the canvas API at the network layer so playground reaches `live`
 * without a real engine. The fixture flag fires once the editor mounts.
 */
import { test, expect } from '@playwright/test'

const mockCanvasApi = async (page: import('@playwright/test').Page) => {
  await page.route('**/*', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    const method = req.method()

    if (path.endsWith('/auth/token')) return route.fulfill({ json: { token: 'fixture' } })
    if (path.endsWith('/contribution'))
      return route.fulfill({ json: { placed: false, tldraw_shape_id: null, text: null, kind: null, relevance: 0 } })
    if (path.endsWith('/respond') && method === 'POST')
      return route.fulfill({ json: { response_type: 'reasoning', tldraw_shape_id: 'shape:fx', read: 'fixture' } })
    if (path.endsWith('/canvas/sessions') && method === 'POST')
      return route.fulfill({ json: { id: 'canvas_session:fx', project_id: 'product:platform', title: 'Fixture', created_at: '', updated_at: '' } })
    if (path.endsWith('/timeline')) return route.fulfill({ json: { events: [], forward_momentum: [] } })
    if (path.endsWith('/classify')) return route.fulfill({ json: { discipline: 'architecture', archetypes: [], specialties: [] } })
    if (path.includes('/proactive/')) return route.fulfill({ json: null })
    if (/\/canvas\/sessions\/[^/]+$/.test(path) && method === 'GET')
      return route.fulfill({ json: { id: 'canvas_session:fx', project_id: 'product:platform', title: 'Fixture', artifacts: [] } })
    return route.continue()
  })
}

const driveToLive = async (page: import('@playwright/test').Page, colorScheme: 'light' | 'dark') => {
  await mockCanvasApi(page)
  await page.emulateMedia({ colorScheme })
  await page.goto('/?mode=playground&debug=team-build-fixture', { waitUntil: 'domcontentloaded' })

  // Partner thesis: the canvas is always warmed up. No idle gate, no
  // ignition input to fill — the ambient input is the only input and it
  // mounts with the canvas. Wait for it to appear.
  const ambient = page.locator('input[placeholder*="thinking with you"]')
  await expect(ambient).toBeVisible({ timeout: 15000 })
}

test('team-build fixture renders on LIGHT canvas (walnut cards on light surface)', async ({ page }) => {
  test.setTimeout(60000)
  await driveToLive(page, 'light')
  // The fixture dispatches synthesis.end at t+3500ms; wait through that beat
  // plus the 400ms aged-paper transition and the arrow draw-in.
  await page.waitForTimeout(5500)
  // Scroll overlay to top so all 4 lens sections are captured in the frame
  // (the overlay auto-scrolls to bottom during live event flow).
  await page.evaluate(() => {
    const el = document.querySelector('[data-test="team-build-overlay"] > div:nth-child(3)') as HTMLElement | null
    if (el !== null) el.scrollTop = 0
  })
  await page.waitForTimeout(400)
  await page.screenshot({ path: '/tmp/canvas-fixture-light.png', fullPage: true })
})

test('team-build fixture renders on DARK canvas (parchment cards on dark surface)', async ({ page }) => {
  test.setTimeout(60000)
  await driveToLive(page, 'dark')
  await page.waitForTimeout(5500)
  await page.evaluate(() => {
    const el = document.querySelector('[data-test="team-build-overlay"] > div:nth-child(3)') as HTMLElement | null
    if (el !== null) el.scrollTop = 0
  })
  await page.waitForTimeout(400)
  await page.screenshot({ path: '/tmp/canvas-fixture-dark.png', fullPage: true })
})

test('team-build fixture mid-stream — captures pre-synthesis state', async ({ page }) => {
  test.setTimeout(60000)
  await driveToLive(page, 'dark')
  // After all phase events have landed (~2550ms) but BEFORE synthesis (t+3000).
  // Captures the cards with phase chips populated but no synthesis card yet.
  await page.waitForTimeout(2700)
  await page.screenshot({ path: '/tmp/canvas-fixture-prephase-dark.png', fullPage: true })
})
