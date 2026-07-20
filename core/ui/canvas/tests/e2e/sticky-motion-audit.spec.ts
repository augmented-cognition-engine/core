/**
 * Audit test: detects unexpected sideways motion of stickies in the working row.
 *
 * Loads the multiplayer demo, hits Play, and samples the bounding-box position
 * of each worker-card in the active section every 100ms. Reports any card whose
 * x-position changes by >5px after it has appeared (which would indicate
 * unwanted reshuffling). Saves a video + DOM snapshot for inspection.
 */
import { test, expect } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'

// Write to a deterministic log path so we can read results without relying
// on Playwright's stdout buffering (which doesn't flush until completion).
const LOG_PATH = '/tmp/sticky-motion-audit.log'
function flog(msg: string) {
  fs.appendFileSync(LOG_PATH, msg + '\n')
}
try { fs.unlinkSync(LOG_PATH) } catch {}
flog(`=== sticky-motion-audit run @ ${new Date().toISOString()} ===`)

test('worker-card positions stay stable once placed', async ({ page }) => {
  // Open the demo
  await page.goto('/demos/multiplayer.html', { waitUntil: 'networkidle' })
  // Give the canvas a moment to set up (boot stagger ~1s + brief card)
  await page.waitForTimeout(1500)

  // Inject a position-tracking script — sample every 100ms and store records
  await page.evaluate(() => {
    const w = window as any
    w.__cardSamples = [] as Array<{
      t: number
      sectionId: string
      cards: Array<{
        agent: string
        idx: number
        left: number
        top: number
        width: number
        height: number
        cls: string
      }>
    }>
    w.__sampleStart = performance.now()
    function sample() {
      const t = Math.round(performance.now() - w.__sampleStart)
      // Sample workers from the ACTIVE section only
      const active = document.querySelector('.cog-section.is-active') as HTMLElement
      if (active) {
        const sectionId = active.id
        const cards = Array.from(active.querySelectorAll('.swr-grid .worker-card')) as HTMLElement[]
        const rec = cards.map((c, idx) => {
          const r = c.getBoundingClientRect()
          return {
            agent: c.dataset.agent || '?',
            idx,
            left: Math.round(r.left),
            top: Math.round(r.top),
            width: Math.round(r.width),
            height: Math.round(r.height),
            cls: c.className,
          }
        })
        w.__cardSamples.push({ t, sectionId, cards: rec })
      }
    }
    w.__samplerId = setInterval(sample, 100)
  })

  // Hit Play
  await page.click('#play')

  // Let the flow run for ~12 seconds so we capture at least Prep + Frame
  await page.waitForTimeout(12000)

  // Stop sampling
  const samples = await page.evaluate(() => {
    const w = window as any
    clearInterval(w.__samplerId)
    return w.__cardSamples
  })

  flog(`\nCaptured ${samples.length} samples\n`)

  // For each card identity (agent + first-appearance timestamp), check if its
  // left position changed by more than 5px AFTER it first appeared.
  type FirstSeen = { left: number; top: number; firstT: number; sectionId: string }
  const firstSeen = new Map<string, FirstSeen>()
  const driftReports: string[] = []

  for (const s of samples) {
    for (const c of s.cards) {
      const key = `${s.sectionId}::${c.agent}::${c.idx}`
      if (!firstSeen.has(key)) {
        firstSeen.set(key, {
          left: c.left,
          top: c.top,
          firstT: s.t,
          sectionId: s.sectionId,
        })
      } else {
        const first = firstSeen.get(key)!
        const dx = Math.abs(c.left - first.left)
        const dy = Math.abs(c.top - first.top)
        if (dx > 5 || dy > 5) {
          // Wait ~400ms after first appearance to let the opacity transition settle
          if (s.t - first.firstT > 500) {
            driftReports.push(
              `${s.sectionId} ${c.agent}[${c.idx}]: at t=${s.t}ms drifted Δx=${dx}px Δy=${dy}px ` +
              `(first seen at t=${first.firstT}ms at ${first.left},${first.top}; now ${c.left},${c.top})`
            )
          }
        }
      }
    }
  }

  // Group drift reports by card key, take the LAST report per key (final drift)
  const lastDriftPerKey = new Map<string, string>()
  for (const r of driftReports) {
    const k = r.split(':')[0] + ':' + r.split(':')[1]
    lastDriftPerKey.set(k, r)
  }
  const uniqueDrifts = Array.from(lastDriftPerKey.values())

  flog(`Drift events (>5px after settle, deduplicated): ${uniqueDrifts.length}`)
  uniqueDrifts.slice(0, 20).forEach(r => flog('  - ' + r))
  flog(`__SUMMARY__ uniqueDrifts=${uniqueDrifts.length}`)

  // Also: list the cards seen per section in order of appearance
  flog('\nCards observed per section:')
  const bySection = new Map<string, Array<{ agent: string; idx: number; left: number; firstT: number }>>()
  for (const [key, fs] of firstSeen.entries()) {
    const parts = key.split('::')
    const sectionId = parts[0], agent = parts[1], idx = parseInt(parts[2])
    if (!bySection.has(sectionId)) bySection.set(sectionId, [])
    bySection.get(sectionId)!.push({ agent, idx, left: fs.left, firstT: fs.firstT })
  }
  for (const [sec, cards] of bySection.entries()) {
    cards.sort((a, b) => a.firstT - b.firstT)
    flog(`  ${sec}:`)
    cards.forEach(c => flog(`    t=${c.firstT}ms  ${c.agent}[${c.idx}]  left=${c.left}px`))
  }

  // Save a screenshot for inspection
  await page.screenshot({ path: 'test-results/sticky-motion-final.png', fullPage: false })

  // The test PASSES if no significant drift — but we always print info.
  expect(uniqueDrifts.length, `Expected no sideways drift; got: ${uniqueDrifts.join('\n')}`).toBeLessThanOrEqual(0)
})
