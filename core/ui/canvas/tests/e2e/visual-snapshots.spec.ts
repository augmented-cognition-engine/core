/**
 * Visual snapshots — wait long enough for auth+API to settle, then screenshot.
 */
import { test, type Page } from '@playwright/test'

test.setTimeout(60000)

async function settle(page: Page, ms = 4000) {
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(ms)
}

test('pulse view — settled state', async ({ page }) => {
  await page.goto('/')
  await settle(page, 5000)
  await page.screenshot({ path: '/tmp/snap-pulse.png' })
})

test('canvas launcher — settled', async ({ page }) => {
  await page.goto('/')
  await settle(page, 2000)

  // Canvas nav button has title="Canvas" or similar
  const canvasBtn = page.locator('button[title="Canvas"], button[title*="canvas"]')
  if (await canvasBtn.count() > 0) {
    await canvasBtn.first().click()
  } else {
    // Fallback: click nav-icon buttons only (not content area buttons)
    const navBtns = page.locator('button[title]')
    const count = await navBtns.count()
    for (let i = 0; i < Math.min(count, 6); i++) {
      await navBtns.nth(i).click().catch(() => {})
      const text = await page.locator('body').textContent().catch(() => '')
      if (text?.includes('Recent') || text?.includes('Describe the decision')) break
    }
  }
  await page.waitForTimeout(1000)
  await page.screenshot({ path: '/tmp/snap-launcher.png' })
})

test('canvas session with BottomBar', async ({ page }) => {
  await page.goto('/')
  await settle(page, 2000)

  // Navigate to canvas via nav button
  const canvasBtn = page.locator('button[title="Canvas"]')
  if (await canvasBtn.count() > 0) {
    await canvasBtn.first().click()
  } else {
    const navBtns = page.locator('button[title]')
    const count = await navBtns.count()
    for (let i = 0; i < Math.min(count, 6); i++) {
      await navBtns.nth(i).click().catch(() => {})
      const text = await page.locator('body').textContent().catch(() => '')
      if (text?.includes('Recent') || text?.includes('Describe the decision')) break
    }
  }
  await page.waitForTimeout(500)

  // Click most recent session button
  const recentBtns = page.locator('button').filter({ hasText: /I want to understand|Untitled|schema probe/ })
  if (await recentBtns.count() > 0) {
    await recentBtns.first().click()
    // Give tldraw time to init
    await page.waitForTimeout(8000)
    await page.screenshot({ path: '/tmp/snap-canvas-session.png' })

    // Look for BottomBar tabs — exact names avoid matching nav "Intelligence" button
    const intelTab = page.getByRole('button', { name: 'Intel', exact: true })
    const reasoningTab = page.getByRole('button', { name: 'Reasoning', exact: true })

    if (await intelTab.count() > 0) {
      await page.screenshot({ path: '/tmp/snap-intel-tab.png' })

      await reasoningTab.click()
      await page.waitForTimeout(500)
      await page.screenshot({ path: '/tmp/snap-reasoning-tab.png' })

      // Decisions tab
      const decisionsTab = page.getByRole('button', { name: 'Decisions', exact: true })
      if (await decisionsTab.count() > 0) {
        await decisionsTab.click()
        await page.waitForTimeout(400)
        await page.screenshot({ path: '/tmp/snap-decisions-tab.png' })
      }

      // Back to Intel
      await intelTab.click()
      await page.waitForTimeout(400)
      await page.screenshot({ path: '/tmp/snap-intel-final.png' })
    }
  }
})

test('intel view (shell)', async ({ page }) => {
  await page.goto('/')
  await settle(page, 2000)

  // Intelligence nav button has title="Intelligence"
  const intelBtn = page.locator('button[title="Intelligence"]')
  if (await intelBtn.count() > 0) {
    await intelBtn.click()
    await page.waitForTimeout(2000)
    await page.screenshot({ path: '/tmp/snap-intel-shell.png' })
  } else {
    // Fallback: iterate nav-only buttons
    const navBtns = page.locator('button[title]')
    const count = await navBtns.count()
    for (let i = 0; i < Math.min(count, 6); i++) {
      await navBtns.nth(i).click().catch(() => {})
      await page.waitForTimeout(300)
      const text = await page.locator('body').textContent().catch(() => '')
      if (text?.includes('BRIEFING') || text?.includes('HIGH RISK')) {
        await page.screenshot({ path: '/tmp/snap-intel-shell.png' })
        break
      }
    }
  }
  await page.screenshot({ path: '/tmp/snap-intel-final.png' })
})
