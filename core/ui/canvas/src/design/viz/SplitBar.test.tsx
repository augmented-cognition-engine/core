// The two claims SplitBar and RampBars make, held to.
//
// These are not "does it render" tests. Each primitive encodes ONE reading, and each
// reading is a thing a person will act on:
//
//   SplitBar  — the split POSITION is the ratio. There is no neutral centre it returns
//               to; 50/50 is a reading (two equal sides pushing against each other is a
//               loaded book, not an empty one), and sign is per-side, not per-position.
//   RampBars  — direction lives in the GEOMETRY. Bars hang down for a negative push and
//               grow up for a positive one, so the sign survives a glance. And "asleep"
//               is a state, not a gap: the force is present and doing nothing, which is a
//               different claim from "there is no such force".

import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RampBars } from './RampBars'
import { SplitBar } from './SplitBar'
import { hues, rgb, rgba } from './chartTokens'

const widths = (c: HTMLElement) =>
  Array.from(c.querySelectorAll('span'))
    .map((s) => (s as HTMLElement).style.width)
    .filter(Boolean)

/** jsdom re-serializes colours with spaces (`rgba(1, 2, 3, 1)`); the token helpers emit
 *  them without. Compare the VALUE, not the whitespace. */
const norm = (v: string) => v.replace(/\s+/g, '')

/** The PAINTED segments, in order — skipping the track, whose background is a token var
 *  rather than a computed colour. */
const backgrounds = (c: HTMLElement) =>
  Array.from(c.querySelectorAll('span'))
    .map((s) => (s as HTMLElement).style.background)
    .filter((bg) => bg && !bg.startsWith('var('))
    .map(norm)

describe('SplitBar — the split position IS the ratio', () => {
  it('places the seam at the ratio, not at the centre', () => {
    const { container } = render(
      <SplitBar leftPct={70} leftPositive={false} rightPositive />,
    )
    expect(widths(container)).toEqual(['70%', '30%'])
  })

  it('renders a balanced book as 50/50 — a reading, not a fallback', () => {
    const { container } = render(<SplitBar leftPct={50} leftPositive rightPositive />)
    expect(widths(container)).toEqual(['50%', '50%'])
  })

  it('colours each segment by ITS OWN sign, not by which side it sits on', () => {
    const { container } = render(
      <SplitBar leftPct={50} leftPositive={false} rightPositive />,
    )
    const bg = backgrounds(container)

    expect(bg[0]).toBe(norm(rgba(hues.down, 1)))   // left side is negative
    expect(bg[1]).toBe(norm(rgba(hues.up, 1)))     // right side is positive
  })

  it('steps the second segment when both sides share a sign', () => {
    // Otherwise two same-signed sides merge into one bar and the split — the entire
    // point — becomes invisible.
    const { container } = render(
      <SplitBar leftPct={40} leftPositive rightPositive sameSign />,
    )
    const bg = backgrounds(container)

    expect(bg[0]).toBe(norm(rgba(hues.up, 1)))
    expect(bg[1]).toBe(norm(rgba(hues.up, 0.5)))
  })

  it('clamps a nonsense ratio rather than drawing outside itself', () => {
    const { container } = render(<SplitBar leftPct={140} leftPositive rightPositive />)
    expect(widths(container)).toEqual(['100%', '0%'])
  })
})

describe('RampBars — direction lives in the geometry', () => {
  it('hangs DOWN from a top rule for a negative push', () => {
    const { container } = render(<RampBars heights={[3, 6, 10]} direction="down" />)
    const ramp = container.querySelectorAll('span')[1] as HTMLElement

    expect(ramp.style.alignItems).toBe('flex-start')
    expect(ramp.style.borderTopWidth).toBe('1px')
    expect(ramp.style.borderTopColor).toBe('var(--ace-line)')
    expect(ramp.style.borderBottomWidth).toBe('')
  })

  it('grows UP from a bottom rule for a positive push', () => {
    const { container } = render(<RampBars heights={[3, 6, 10]} direction="up" />)
    const ramp = container.querySelectorAll('span')[1] as HTMLElement

    expect(ramp.style.alignItems).toBe('flex-end')
    expect(ramp.style.borderBottomWidth).toBe('1px')
    expect(ramp.style.borderBottomColor).toBe('var(--ace-line)')
    expect(ramp.style.borderTopWidth).toBe('')
  })

  it('colour agrees with the geometry rather than carrying it alone', () => {
    const { container } = render(<RampBars heights={[4]} direction="down" />)
    expect(backgrounds(container)[0]).toBe(norm(rgb(hues.down)))
  })

  it('renders ASLEEP as visibly present and visibly doing nothing', () => {
    // Not hidden. Hiding it would say "there is no such force", which is a different
    // and false claim: the force exists, it is simply not pushing.
    const { container } = render(<RampBars heights={[]} direction={null} />)
    const ramp = container.querySelectorAll('span')[1] as HTMLElement

    expect(ramp.style.opacity).toBe('0.4')
    const bars = Array.from(container.querySelectorAll('span')).filter(
      (s) => (s as HTMLElement).style.height === '2px',
    )
    expect(bars.length).toBeGreaterThan(0)   // a flat rule, still drawn
  })

  it('an unknown direction is asleep, never silently "up"', () => {
    // Heights are supplied but the direction is unknown. It must NOT pick one — an
    // unknown push rendered as an upward one is a fabricated reading.
    const { container } = render(<RampBars heights={[3, 6]} direction={null} />)

    // Asleep paints with a token (dim ink), not a signed colour — so it is deliberately
    // NOT among the painted segments the other tests read.
    const painted = backgrounds(container)
    expect(painted).toHaveLength(0)

    const bar = Array.from(container.querySelectorAll('span')).find(
      (el) => (el as HTMLElement).style.height === '2px',
    ) as HTMLElement
    expect(bar.style.background).toContain('--ace-ink-faint')
  })
})
