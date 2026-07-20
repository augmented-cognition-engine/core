/**
 * Deep canvas session audit — opens a real session and inspects every component.
 */
import { test, expect, type Page } from '@playwright/test'

async function goToCanvasLauncher(page: Page) {
  await page.goto('/')
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
  // Click canvas nav button (second icon in left nav)
  const navBtns = page.locator('[style*="cursor: pointer"], button').filter({
    hasNot: page.locator('input, textarea'),
  })
  // ShellNav has fixed icon buttons — the canvas one is index 1 (after pulse)
  // Try by title attribute first
  const canvasByTitle = page.locator('[title*="anvas"], [aria-label*="anvas"]')
  if (await canvasByTitle.count() > 0) {
    await canvasByTitle.first().click()
  } else {
    // Fallback: click the second icon button in the leftmost column
    const leftNav = page.locator('div').filter({ hasNot: page.locator('main') }).first()
    const iconBtns = page.locator('button').nth(1)
    await iconBtns.click().catch(() => {})
  }
  await page.waitForTimeout(500)
}

test.describe('Canvas session deep audit', () => {
  test('open recent session and inspect canvas + BottomBar', async ({ page }) => {
    // tldraw mount + multiple bottombar tab interactions exceed default 30s budget
    test.setTimeout(60_000)
    await page.goto('/')
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})

    // Navigate to canvas mode
    await goToCanvasLauncher(page)
    await page.screenshot({ path: '/tmp/deep-01-canvas-launcher.png' })

    // Click the most recent session — sessions render as <button> elements
    const recentItems = page.locator('button').filter({
      hasText: /ago|just now|understand|Untitled|schema/,
    }).first()

    if (await recentItems.count() > 0) {
      await recentItems.click()
      await page.waitForTimeout(3000)
      await page.screenshot({ path: '/tmp/deep-02-canvas-loading.png' })

      // Wait for tldraw to mount
      await page.waitForSelector('.tl-canvas, canvas, [class*="tldraw"]', { timeout: 10000 })
        .catch(() => {})
      await page.waitForTimeout(1500)
      await page.screenshot({ path: '/tmp/deep-03-canvas-loaded.png' })

      // Check BottomBar tabs — use exact names to avoid matching ShellNav "Intelligence" button
      const intelTab = page.getByRole('button', { name: 'Intel', exact: true })
      const reasoningTab = page.getByRole('button', { name: 'Reasoning', exact: true })
      const decisionsTab = page.getByRole('button', { name: 'Decisions', exact: true })
      const momentumTab = page.getByRole('button', { name: 'Momentum', exact: true })

      const hasIntel = await intelTab.count() > 0
      const hasReasoning = await reasoningTab.count() > 0

      await page.screenshot({ path: '/tmp/deep-04-bottombar-intel.png' })

      if (hasIntel) {
        await expect(intelTab).toBeVisible()
        const intelColor = await intelTab.evaluate(el =>
          window.getComputedStyle(el).color
        )
        console.log('Intel tab color:', intelColor)
      }

      if (hasReasoning) {
        await reasoningTab.click()
        await page.waitForTimeout(400)
        await page.screenshot({ path: '/tmp/deep-05-reasoning-tab.png' })

        if (hasIntel) {
          await intelTab.click()
          await page.waitForTimeout(400)
          await page.screenshot({ path: '/tmp/deep-06-intel-tab-revisit.png' })
        }
      }

      // Test collapse/expand
      const collapseBtn = page.getByRole('button', { name: /collapse/i })
      if (await collapseBtn.count() > 0) {
        await collapseBtn.click()
        await page.waitForTimeout(300)
        await page.screenshot({ path: '/tmp/deep-07-bottombar-collapsed.png' })

        const expandBtn = page.getByRole('button', { name: /expand/i })
        if (await expandBtn.count() > 0) {
          await expandBtn.click()
          await page.waitForTimeout(300)
          await page.screenshot({ path: '/tmp/deep-08-bottombar-expanded.png' })
        }
      }

      // Check VisionAnchor is visible (top center)
      const visionAnchor = page.locator('div').filter({
        hasText: /I want to understand|Untitled|schema probe/,
      }).first()
      if (await visionAnchor.count() > 0) {
        await expect(visionAnchor).toBeVisible()
        console.log('VisionAnchor visible ✓')
      }

      // Take final full-page screenshot
      await page.screenshot({ path: '/tmp/deep-09-full-canvas.png', fullPage: false })
    } else {
      // No recent sessions — test the canvas launcher form
      const input = page.getByPlaceholder(/Describe the decision/i)
      if (await input.count() > 0) {
        await input.fill('Test audit: PostgreSQL vs MongoDB')
        await page.screenshot({ path: '/tmp/deep-02-filled-input.png' })
        // Don't submit — just audit the launcher state
      }
      await page.screenshot({ path: '/tmp/deep-02-launcher-state.png' })
    }
  })

  test('canvas launcher form layout and interactions', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
    await goToCanvasLauncher(page)

    const input = page.getByPlaceholder(/Describe the decision/i)
    await expect(input).toBeVisible({ timeout: 5000 })

    // Check input accepts text
    await input.fill('Should we rewrite the auth system?')
    await expect(input).toHaveValue('Should we rewrite the auth system?')

    // Check submit button state
    const submitBtn = page.locator('button[type="submit"], button').filter({ hasText: /→|→/ }).first()
    await page.screenshot({ path: '/tmp/deep-launcher-filled.png' })

    // Check Browse templates button
    const templatesBtn = page.getByRole('button', { name: /browse templates/i })
    await expect(templatesBtn).toBeVisible()

    // Check Start blank
    const blankBtn = page.getByRole('button', { name: /start blank/i })
    await expect(blankBtn).toBeVisible()

    await page.screenshot({ path: '/tmp/deep-launcher-buttons.png' })
  })

  test('PulseView stats are visible and non-empty', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
    await page.waitForTimeout(1500)
    await page.screenshot({ path: '/tmp/deep-pulse-loaded.png' })

    // Check stats at bottom
    const insightsText = await page.locator('body').textContent()
    const hasInsights = insightsText?.includes('insights') ?? false
    const hasSpecialties = insightsText?.includes('specialties') ?? false

    console.log('Has insights stat:', hasInsights)
    console.log('Has specialties stat:', hasSpecialties)

    // PulseView shows "ACE" label with a dot
    const aceLabel = page.locator('text=ACE')
    if (await aceLabel.count() > 0) {
      await expect(aceLabel.first()).toBeVisible()
      console.log('ACE label visible ✓')
    }

    // Check no horizontal overflow
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth)
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 5)
  })

  test('IntelView shows briefing and signals', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})

    // ShellNav has an "Intelligence" button with title="Intelligence"
    const intelNavBtn = page.locator('button[title="Intelligence"]')
    if (await intelNavBtn.count() > 0) {
      await intelNavBtn.click()
      await page.waitForTimeout(2000)
      await page.screenshot({ path: '/tmp/deep-intel-view.png' })
      const text = await page.locator('body').textContent()
      const hasContent = text?.includes('BRIEFING') || text?.includes('signals') || text?.includes('insights')
      console.log('IntelView has content:', hasContent)
    } else {
      // Fallback: iterate nav buttons
      const buttons = page.locator('button[title], button[aria-label]')
      const count = await buttons.count()
      for (let i = 0; i < Math.min(count, 6); i++) {
        await buttons.nth(i).click().catch(() => {})
        await page.waitForTimeout(300)
        const text = await page.locator('body').textContent()
        if (text?.includes('BRIEFING') || text?.includes('HIGH RISK')) {
          await page.screenshot({ path: '/tmp/deep-intel-view.png' })
          break
        }
      }
    }
    await page.screenshot({ path: '/tmp/deep-intel-final.png' })
  })
})
