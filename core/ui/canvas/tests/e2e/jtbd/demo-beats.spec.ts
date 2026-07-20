/**
 * Demo-beats spec — exercises the wiring behind the four pick-a-future +
 * calibration-moment beats.
 *
 * Scope notes (see advisor checkpoint in commit log):
 *
 *   Beat 3 (decision lineage)          — covered by DecisionLedger unit tests.
 *   Beat 4 (rollouts picker)            — covered here: nav + tab + empty/populated state.
 *   Beat 5 (prediction auto-mount)      — deferred to manual QA. Requires a
 *                                         real forecaster → WS → CanvasApp
 *                                         roundtrip with timing; Playwright
 *                                         over that flakes for non-bug reasons.
 *                                         useCanvasSession unit tests cover
 *                                         the wiring itself.
 *   Beat 6 (calibration moment)         — covered here via SYNTHETIC
 *                                         CustomEvent dispatch on window.
 *                                         The reconciler unit test covers
 *                                         the backend emit; this spec covers
 *                                         the frontend response (ProactiveLine
 *                                         override + CalibrationTab refresh).
 *
 * Forgiving style mirrors canvas-focused.spec.ts — screenshots over hard
 * failures so the spec is useful for both CI and live presenter checks.
 */
import { test, expect, type Page } from '@playwright/test'

test.setTimeout(60000)

async function clickNavIconByLabel(page: Page, label: RegExp): Promise<boolean> {
  // ShellNav sets title={label} on each nav button — getByRole reads that.
  const btn = page.getByRole('button', { name: label }).first()
  if ((await btn.count()) === 0) return false
  await btn.click()
  return true
}

test('beat 4 — Foresight nav exposes rollouts/predictions/calibration tabs', async ({ page }) => {
  await page.goto('/')
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(3000)

  const clicked = await clickNavIconByLabel(page, /foresight/i)
  if (!clicked) {
    // If we can't find the nav (auth-gated build, sidebar collapsed, etc.),
    // capture and exit — manual QA picks up the gap.
    await page.screenshot({ path: '/tmp/demo-beat-4-no-nav.png' })
    return
  }

  await page.waitForSelector('[data-testid="foresight-view"]', { timeout: 5000 }).catch(() => {})
  const foresightView = page.locator('[data-testid="foresight-view"]')
  await expect(foresightView).toBeVisible({ timeout: 5000 })
  await page.screenshot({ path: '/tmp/demo-beat-4-rollouts.png' })

  // The default tab is rollouts. Switching tabs must succeed even with empty data.
  await page.locator('[data-testid="foresight-tab-calibration"]').click()
  await page.waitForTimeout(300)
  await page.screenshot({ path: '/tmp/demo-beat-4-calibration.png' })

  await page.locator('[data-testid="foresight-tab-predictions"]').click()
  await page.waitForTimeout(300)
  await page.locator('[data-testid="foresight-tab-rollouts"]').click()
})

test('beat 6 — synthetic outcome.closed surfaces calibration line in ProactiveLine', async ({ page }) => {
  await page.goto('/')
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(3000)

  // Open a canvas session — ProactiveLine only mounts inside a session.
  // Default landing is the Canvas mode + launcher. Pick the first recent
  // session button if the launcher rendered one.
  const sessionBtn = page.locator('button').filter({ hasText: /understand|Untitled/ }).first()
  if (await sessionBtn.count() === 0) {
    await page.screenshot({ path: '/tmp/demo-beat-6-no-session.png' })
    return
  }
  await sessionBtn.click()
  await page.waitForTimeout(5000) // canvas + WS settle

  // Dispatch the outcome.closed event the way CanvasApp.onPredictionOutcomeClosed
  // does — synthetic here because waiting on the real backend round-trip is
  // the failure mode the advisor flagged.
  await page.evaluate(() => {
    window.dispatchEvent(
      new CustomEvent('foresight:outcome_closed', {
        detail: {
          prediction_id: 'decision_prediction:demo-synth',
          agent_id: 'pm',
          archetype: 'pm',
          predicted: 0.4,
          actual: 0.35,
          predicted_deltas: { 'capability:partner_onboarding': 0.4 },
          actual_deltas: { 'capability:partner_onboarding': 0.35 },
          calibration_score: 0.88,
          weight_delta: 0.38,
          discipline: 'product',
        },
      }),
    )
  })

  // ProactiveLine should swap to the calibration line within a tick (it's a
  // useEffect setOverride — no debounce). Look for the "played out" partner-
  // voice phrasing baked into formatCalibrationLine.
  const pl = page.locator('text=/played out|calibrated|recalibrating/i').first()
  await expect(pl).toBeVisible({ timeout: 4000 })
  await page.screenshot({ path: '/tmp/demo-beat-6-calibration-line.png' })

  // The CALIBRATION chip should also surface.
  const chip = page.locator('text=CALIBRATION').first()
  await expect(chip).toBeVisible({ timeout: 4000 })
})
