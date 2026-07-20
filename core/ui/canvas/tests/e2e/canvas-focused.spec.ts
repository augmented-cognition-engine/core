/**
 * Focused canvas flow audit — explicit waits, reliable selectors.
 */
import { test, type Page } from '@playwright/test'

test.setTimeout(90000)

async function clickNavButton(page: Page, index: number) {
  // ShellNav renders buttons in a fixed column — click by index
  const navCol = page.locator('[style*="flex-direction: column"]').first()
  const btns = navCol.locator('button')
  const cnt = await btns.count()
  if (index < cnt) await btns.nth(index).click()
}

test('full canvas flow — pulse → launcher → session → bottombar tabs', async ({ page }) => {
  // ── 1. Load app ──────────────────────────────────────────────────────────
  await page.goto('/')
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(4000) // let auth + proactive line settle
  await page.screenshot({ path: '/tmp/flow-01-pulse.png' })

  // ── 2. Navigate to canvas ─────────────────────────────────────────────────
  // Canvas is the second icon in the left nav
  const allBtns = page.locator('button')
  let launcherFound = false
  for (let i = 0; i < 8; i++) {
    const cnt = await allBtns.count()
    if (i >= cnt) break
    await allBtns.nth(i).click().catch(() => {})
    await page.waitForTimeout(300)
    const text = await page.locator('body').textContent().catch(() => '')
    if (text?.includes('Recent') || text?.includes('Describe the decision')) {
      launcherFound = true
      break
    }
  }

  if (!launcherFound) {
    await page.screenshot({ path: '/tmp/flow-02-no-launcher.png' })
    return
  }

  // Wait for recent sessions list to load
  await page.waitForSelector('button:has-text("I want to understand"), button:has-text("Untitled"), button:has-text("schema")', {
    timeout: 8000,
  }).catch(() => {})
  await page.screenshot({ path: '/tmp/flow-02-launcher.png' })

  // ── 3. Open recent session ────────────────────────────────────────────────
  const sessionBtn = page.locator('button').filter({
    hasText: 'I want to understand what to work on next with ACE'
  }).first()

  const sessionBtnAlt = page.locator('button').filter({ hasText: /understand|Untitled/ }).first()

  const btn = (await sessionBtn.count() > 0) ? sessionBtn : sessionBtnAlt
  if (await btn.count() === 0) {
    await page.screenshot({ path: '/tmp/flow-03-no-session-btn.png' })
    return
  }

  await btn.click()
  await page.screenshot({ path: '/tmp/flow-03-canvas-loading.png' })

  // Wait for canvas to initialize (tldraw + WebSocket)
  await page.waitForTimeout(6000)
  await page.screenshot({ path: '/tmp/flow-04-canvas-loaded.png' })

  // ── 4. Audit BottomBar ─────────────────────────────────────────────────────
  // Intel tab (default)
  const intelTab  = page.getByRole('button', { name: /^intel$/i })
  const reasonTab = page.getByRole('button', { name: /^reasoning$/i })
  const decTab    = page.getByRole('button', { name: /^decisions$/i })
  const momTab    = page.getByRole('button', { name: /^momentum$/i })
  const collapseBtn = page.getByRole('button', { name: /collapse/i })

  // Screenshot: Intel tab default
  await page.screenshot({ path: '/tmp/flow-05-intel-default.png' })

  if (await reasonTab.count() > 0) {
    await reasonTab.click()
    await page.waitForTimeout(400)
    await page.screenshot({ path: '/tmp/flow-06-reasoning-tab.png' })
  }

  if (await decTab.count() > 0) {
    await decTab.click()
    await page.waitForTimeout(400)
    await page.screenshot({ path: '/tmp/flow-07-decisions-tab.png' })
  }

  if (await momTab.count() > 0) {
    await momTab.click()
    await page.waitForTimeout(400)
    await page.screenshot({ path: '/tmp/flow-08-momentum-tab.png' })
  }

  if (await intelTab.count() > 0) {
    await intelTab.click()
    await page.waitForTimeout(600)
    await page.screenshot({ path: '/tmp/flow-09-intel-tab-content.png' })
  }

  // Collapse / expand
  if (await collapseBtn.count() > 0) {
    await collapseBtn.click()
    await page.waitForTimeout(350)
    await page.screenshot({ path: '/tmp/flow-10-collapsed.png' })

    const expandBtn = page.getByRole('button', { name: /expand/i })
    if (await expandBtn.count() > 0) {
      await expandBtn.click()
      await page.waitForTimeout(350)
      await page.screenshot({ path: '/tmp/flow-11-expanded.png' })
    }
  }

  // ── 5. VisionAnchor ────────────────────────────────────────────────────────
  // The VisionAnchor sits at top center of canvas area
  await page.screenshot({ path: '/tmp/flow-12-vision-anchor.png' })

  // ── 6. Submit a prompt to trigger reasoning pipeline ─────────────────────
  // AceCard has an input — find it
  const aceInput = page.locator('textarea, input[type="text"]').last()
  if (await aceInput.count() > 0) {
    await aceInput.click()
    await aceInput.fill('What should we focus on this sprint?')
    await page.waitForTimeout(300)
    await page.screenshot({ path: '/tmp/flow-13-prompt-typed.png' })

    // Submit via Enter
    await aceInput.press('Enter')
    await page.waitForTimeout(2000)
    await page.screenshot({ path: '/tmp/flow-14-pipeline-started.png' })

    // Wait for reasoning to appear
    await page.waitForTimeout(4000)
    await page.screenshot({ path: '/tmp/flow-15-reasoning-active.png' })
  }
})
