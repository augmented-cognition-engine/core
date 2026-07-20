// core/ui/canvas/src/design/__enforcement__/chartTokensParity.test.ts
//
// The visualization tokens exist in two places on purpose: as RGB channels in
// tokens.css (so CSS can compose them — rgb(var(--ace-chart-call) / .4)) and as
// numeric triplets in design/viz/chartTokens.ts (so the SVG renderer can do color
// MATH on them — σ-tier intensity ramps, OI magnitude alpha).
//
// Two sources of truth for one value is a drift bug waiting to happen. This test is
// the thing that makes it safe: change one without the other and the suite fails the
// same day, exactly like tokensContract.test.ts does for the rest of the system.
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  DIFF_CALL_COLOR,
  DIFF_PUT_COLOR,
  FUTURE_LIS_COLOR,
  ROLL3_LIS_COLOR,
  SHORT_TERM_COLOR,
  chartInk,
  hues,
  rgba,
} from '../viz/chartTokens'

/** `callTint` -> `call-tint`: the TS mirror is camelCase, the CSS var is kebab. */
function toCssName(tsName: string): string {
  return tsName.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)
}

const TOKENS_CSS = path.join(path.resolve(__dirname, '..'), 'tokens.css')

/** `--ace-chart-call: 74 222 128;` -> { 'call': [74,222,128] } */
function readChartChannelsFromCss(): Record<string, number[]> {
  const css = fs.readFileSync(TOKENS_CSS, 'utf8')
  const out: Record<string, number[]> = {}
  const re = /--ace-chart-([a-z0-9-]+):\s*([0-9]+)\s+([0-9]+)\s+([0-9]+)\s*;/g
  let m: RegExpExecArray | null
  while ((m = re.exec(css)) !== null) {
    out[m[1]] = [Number(m[2]), Number(m[3]), Number(m[4])]
  }
  return out
}

describe('chart token parity (tokens.css <-> design/viz/chartTokens.ts)', () => {
  const css = readChartChannelsFromCss()

  it('defines every domain hue in CSS as RGB channels', () => {
    for (const name of Object.keys(hues)) {
      expect(css[name], `--ace-chart-${name} missing from tokens.css`).toBeDefined()
    }
  })

  it.each(Object.keys(hues))('hue %s matches its CSS channels exactly', (name) => {
    const ts = hues[name as keyof typeof hues]
    expect(css[name]).toEqual([...ts])
  })

  it.each([
    ['short-term', SHORT_TERM_COLOR],
    ['roll3', ROLL3_LIS_COLOR],
    ['roll5', FUTURE_LIS_COLOR],
    ['diff-call', DIFF_CALL_COLOR],
    ['diff-put', DIFF_PUT_COLOR],
  ])('lens/diff color %s matches its CSS channels exactly', (cssName, tsValue) => {
    const fromTs = String(tsValue).split(',').map(Number)
    expect(css[cssName], `--ace-chart-${cssName} missing from tokens.css`).toEqual(fromTs)
  })

  it('defines every chart-ink token in CSS as RGB channels', () => {
    for (const name of Object.keys(chartInk)) {
      const cssName = toCssName(name)
      expect(css[cssName], `--ace-chart-${cssName} missing from tokens.css`).toBeDefined()
    }
  })

  it.each(Object.keys(chartInk))('chart-ink %s matches its CSS channels exactly', (name) => {
    const ts = chartInk[name as keyof typeof chartInk]
    expect(css[toCssName(name)]).toEqual([...ts])
  })

  it('CSS defines no chart token the TS mirror has forgotten', () => {
    // The direction that catches DRIFT: someone adds a hue to CSS, uses it in a
    // component, and the renderer's color math silently never learns about it.
    const known = new Set([
      ...Object.keys(hues),
      ...Object.keys(chartInk).map(toCssName),
      'short-term',
      'roll3',
      'roll5',
      'diff-call',
      'diff-put',
    ])
    const orphans = Object.keys(css).filter((k) => !known.has(k))
    expect(orphans, 'chart tokens in tokens.css with no TS mirror').toEqual([])
  })
})

describe('color math helpers', () => {
  it('rgba composes a hue with a computed alpha — the reason channels are numbers', () => {
    expect(rgba(hues.call, 0.4)).toBe('rgba(74,222,128,0.4)')
  })

  it('clamps alpha rather than emitting an invalid color', () => {
    // An intensity ramp that overshoots must not produce rgba(...,1.7) — browsers
    // silently drop the whole declaration and the bar renders invisible.
    expect(rgba(hues.put, 1.7)).toBe('rgba(248,113,113,1)')
    expect(rgba(hues.put, -0.2)).toBe('rgba(248,113,113,0)')
  })
})
