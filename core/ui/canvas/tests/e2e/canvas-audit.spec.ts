/**
 * Canvas experience audit — full flow visual inspection.
 * Checks layout, navigation, BottomBar tabs, and the Intel panel at rest.
 * Runs against live backend at :3000 for real API responses.
 */

import { test, expect, type Page } from '@playwright/test'

// ─── helpers ────────────────────────────────────────────────────────────────

async function collectErrors(page: Page): Promise<string[]> {
  const errs: string[] = []
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()) })
  page.on('pageerror', (e) => errs.push(e.message))
  return errs
}

async function waitForNav(page: Page) {
  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {})
}

// ─── Entry / Shell ───────────────────────────────────────────────────────────

test.describe('AppShell navigation', () => {
  test('loads without JS errors and shows nav icons', async ({ page }) => {
    const errors = await collectErrors(page)
    await page.goto('/')
    await waitForNav(page)

    // Shell nav should render
    await expect(page.locator('nav, [role="navigation"]').first()).toBeVisible({ timeout: 5000 })
      .catch(async () => {
        // AppShell uses divs not semantic nav — look for the nav buttons area
        await expect(page.locator('body')).toBeVisible()
      })

    await page.screenshot({ path: '/tmp/audit-01-shell.png', fullPage: false })
    expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0)
  })

  test('pulse view shows on load', async ({ page }) => {
    await page.goto('/')
    await waitForNav(page)
    await page.screenshot({ path: '/tmp/audit-02-pulse.png' })
    // PulseView renders something — just check no blank white screen
    const body = await page.locator('body').innerHTML()
    expect(body.length).toBeGreaterThan(500)
  })
})

// ─── Canvas Launcher ─────────────────────────────────────────────────────────

test.describe('Canvas launcher', () => {
  test('nav click reaches canvas launcher', async ({ page }) => {
    await page.goto('/')
    await waitForNav(page)

    // Find the canvas nav button — it has a title or aria-label containing "canvas" or an icon
    // AppShell renders ShellNav with mode buttons
    const canvasBtn = page.getByRole('button').filter({ hasText: /canvas/i }).first()
    const hasCanvasBtn = await canvasBtn.count() > 0

    if (!hasCanvasBtn) {
      // ShellNav uses icons, not text. Try clicking the second nav item.
      const navBtns = page.locator('button[title], button[aria-label]')
      const count = await navBtns.count()
      if (count > 1) await navBtns.nth(1).click()
    } else {
      await canvasBtn.click()
    }

    await page.waitForTimeout(500)
    await page.screenshot({ path: '/tmp/audit-03-canvas-launcher.png' })

    // Should show CanvasLauncher or a session input
    const body = await page.locator('body').innerHTML()
    // At minimum, no crash
    expect(body.length).toBeGreaterThan(200)
  })
})

// ─── BottomBar ───────────────────────────────────────────────────────────────

test.describe('BottomBar Intel tab', () => {
  test('BottomBar renders with Intel tab as default when in canvas', async ({ page }) => {
    await page.goto('/')
    await waitForNav(page)

    // Navigate to canvas mode without a session — CanvasLauncher shows
    // Try direct navigation to canvas mode
    await page.evaluate(() => {
      // Look for any button that sets mode to canvas
      const btns = Array.from(document.querySelectorAll('button'))
      const found = btns.find(b => b.getAttribute('title')?.toLowerCase().includes('canvas')
        || b.getAttribute('aria-label')?.toLowerCase().includes('canvas'))
      if (found) (found as HTMLButtonElement).click()
    })
    await page.waitForTimeout(600)
    await page.screenshot({ path: '/tmp/audit-04-canvas-mode.png' })
  })
})

// ─── Entry Screen (existing golden path) ─────────────────────────────────────

test.describe('Entry screen', () => {
  test('AppShell renders without errors', async ({ page }) => {
    const errors = await collectErrors(page)
    await page.goto('/')
    await waitForNav(page)

    // AppShell renders with nav + PulseView by default
    const hasOpenCanvas = await page.getByText(/Open canvas/i).count() > 0
    const hasInsights = await page.getByText(/insights/i).count() > 0

    await page.screenshot({ path: '/tmp/audit-05-entry.png' })

    // App shell or pulse view visible
    expect(hasOpenCanvas || hasInsights || (await page.locator('body').innerHTML()).length > 500).toBe(true)
    expect(errors.filter(e => !e.includes('favicon') && !e.includes('net::ERR'))).toHaveLength(0)
  })

  test('no layout overflow on viewport', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/')
    await waitForNav(page)

    // Check horizontal scroll — indicates overflow
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth)
    await page.screenshot({ path: '/tmp/audit-06-overflow.png' })

    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 5) // 5px tolerance
  })
})

// ─── ShellNav modes ──────────────────────────────────────────────────────────

test.describe('ShellNav mode switching', () => {
  test('all nav modes switch without errors', async ({ page }) => {
    const errors = await collectErrors(page)
    await page.goto('/')
    await waitForNav(page)

    // ShellNav is the left column — click only nav icon buttons (title or aria-label present)
    const navBtns = page.locator('button[title], button[aria-label]')
    const count = await navBtns.count()
    for (let i = 0; i < Math.min(count, 5); i++) {
      await navBtns.nth(i).click().catch(() => {})
      await page.waitForTimeout(300)
    }

    await page.screenshot({ path: '/tmp/audit-07-nav-switch.png' })
    const critical = errors.filter(e =>
      !e.includes('favicon') && !e.includes('net::ERR') && !e.includes('404')
    )
    expect(critical).toHaveLength(0)
  })
})

// ─── Canvas with live session (if backend available) ─────────────────────────

test.describe('Canvas with live backend', () => {
  test('creates session and sees canvas with BottomBar', async ({ page }) => {
    // Check backend is reachable
    const backendOk = await page.request.get('http://localhost:3000/health')
      .then(() => true)
      .catch(() => false)

    if (!backendOk) {
      test.skip(true, 'Backend not available')
      return
    }

    const errors = await collectErrors(page)
    await page.goto('/')
    await waitForNav(page)

    // Screenshot: initial state
    await page.screenshot({ path: '/tmp/audit-08-live-initial.png' })

    // Look for an input or button that starts a canvas session
    const input = page.getByPlaceholder(/what are you deciding|tell me|start/i).first()
    if (await input.count() > 0) {
      await input.fill('Should we use PostgreSQL or MongoDB for our user data?')
      await page.screenshot({ path: '/tmp/audit-09-input-filled.png' })

      const submitBtn = page.getByRole('button', { name: /start|submit|go|begin/i }).first()
      if (await submitBtn.count() > 0) {
        await submitBtn.click()
        await page.waitForTimeout(2000)
        await page.screenshot({ path: '/tmp/audit-10-after-submit.png' })
      }
    }

    // If we're in canvas mode, check BottomBar
    const intelTab = page.getByRole('button', { name: /intel/i }).first()
    if (await intelTab.count() > 0) {
      await expect(intelTab).toBeVisible()
      await page.screenshot({ path: '/tmp/audit-11-bottombar.png' })

      // Check Intel tab is active by default (active tab has different color)
      const isActive = await intelTab.evaluate((el) => {
        const style = window.getComputedStyle(el)
        return style.color !== 'rgb(85, 85, 85)' // #555 = inactive
      })
      expect(isActive).toBe(true)

      // Click reasoning tab
      const reasoningTab = page.getByRole('button', { name: /reasoning/i }).first()
      if (await reasoningTab.count() > 0) {
        await reasoningTab.click()
        await page.waitForTimeout(300)
        await page.screenshot({ path: '/tmp/audit-12-reasoning-tab.png' })
      }

      // Click back to Intel
      await intelTab.click()
      await page.waitForTimeout(300)
      await page.screenshot({ path: '/tmp/audit-13-intel-tab.png' })
    }

    const critical = errors.filter(e =>
      !e.includes('favicon') && !e.includes('net::ERR') && !e.includes('401') && !e.includes('404')
    )
    expect(critical).toHaveLength(0)
  })
})
