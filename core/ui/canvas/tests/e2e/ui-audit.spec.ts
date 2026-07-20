/**
 * UI audit — drives the demo arc and screenshots every meaningful beat.
 *
 * Not for CI: this writes to /tmp/ace-ui-audit/ so a human can inspect.
 * Run with: npx playwright test tests/e2e/ui-audit.spec.ts
 *
 * Beats audited:
 *   01-launcher          — landing state
 *   02-canvas-loaded     — canvas mounted inside a session
 *   03-decision-ledger   — decisions tab, expanded row (lineage)
 *   04-foresight-rollouts — Foresight default tab
 *   05-foresight-predictions — second tab
 *   06-foresight-calibration — Calibration tab with seeded outcomes
 *   07-calibration-moment-pre — canvas before synthetic outcome.closed
 *   08-calibration-moment-post — ProactiveLine override visible
 */
import { test, expect, type Page } from '@playwright/test'

const OUT = '/tmp/ace-ui-audit'

test.setTimeout(180000)

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false })
}

async function clickNav(page: Page, label: RegExp): Promise<boolean> {
  const btn = page.getByRole('button', { name: label }).first()
  if ((await btn.count()) === 0) return false
  await btn.click()
  await page.waitForTimeout(800)
  return true
}

test('ui-audit — full demo arc walkthrough with screenshots', async ({ page }) => {
  await page.goto('/')
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(3000)
  await shot(page, '01-launcher')

  // Open a real session — the launcher lists Recent sessions; click the first.
  const recentBtn = page
    .locator('button')
    .filter({ hasText: /understand|Untitled|event bus|brainstorm|decision/i })
    .first()
  if ((await recentBtn.count()) > 0) {
    await recentBtn.click()
    await page.waitForTimeout(6000) // tldraw + WS settle
    await shot(page, '02-canvas-loaded')

    // Try to surface the Decision Ledger tab.
    const decTab = page.getByRole('button', { name: /^decisions$/i }).first()
    if ((await decTab.count()) > 0) {
      await decTab.click()
      await page.waitForTimeout(800)
      await shot(page, '03a-decisions-tab')

      // Try clicking the first decision row to expand its lineage.
      const expandable = page
        .locator('[data-testid^="decision-row"], button:has-text("▸"), button:has-text("▾")')
        .first()
      if ((await expandable.count()) > 0) {
        await expandable.click()
        await page.waitForTimeout(500)
        await shot(page, '03b-decision-row-expanded')
      } else {
        // Fall back: just click any list item in the decisions panel
        await page.locator('text=/Shaped by|frameworks_used|perspective/i').first()
          .click({ trial: true })
          .catch(() => {})
        await shot(page, '03b-decision-row-fallback')
      }
    } else {
      await shot(page, '03-no-decisions-tab')
    }
  } else {
    await shot(page, '02-no-recent-session')
  }

  // Navigate to Foresight — three tabs.
  const foresightOpened = await clickNav(page, /foresight/i)
  if (foresightOpened) {
    await page.waitForSelector('[data-testid="foresight-view"]', { timeout: 5000 }).catch(() => {})
    await shot(page, '04-foresight-rollouts')

    await page.locator('[data-testid="foresight-tab-predictions"]').click().catch(() => {})
    await page.waitForTimeout(500)
    await shot(page, '05-foresight-predictions')

    await page.locator('[data-testid="foresight-tab-calibration"]').click().catch(() => {})
    await page.waitForTimeout(1500) // let fetch land
    await shot(page, '06-foresight-calibration')
  } else {
    await shot(page, '04-no-foresight-nav')
  }

  // Calibration moment — go back to canvas, dispatch synthetic event, screenshot.
  const canvasOpened = await clickNav(page, /^Canvas/i)
  if (canvasOpened) {
    await page.waitForTimeout(2000)
    await shot(page, '07-canvas-pre-calibration')

    await page.evaluate(() => {
      window.dispatchEvent(
        new CustomEvent('foresight:outcome_closed', {
          detail: {
            prediction_id: 'decision_prediction:audit-synth',
            agent_id: 'pm',
            archetype: 'pm',
            predicted: 0.4,
            actual: 0.36,
            predicted_deltas: { 'capability:partner_onboarding': 0.4 },
            actual_deltas: { 'capability:partner_onboarding': 0.36 },
            calibration_score: 0.88,
            weight_delta: 0.38,
            discipline: 'product',
          },
        }),
      )
    })
    await page.waitForTimeout(2000)
    await shot(page, '08-calibration-moment-post')

    // Look for the calibration line text to confirm it surfaced.
    const calibLine = page.locator('text=/played out|calibrated/i').first()
    await expect(calibLine).toBeVisible({ timeout: 3000 }).catch(async () => {
      await shot(page, '08-FAIL-no-calibration-line')
    })
  }
})
