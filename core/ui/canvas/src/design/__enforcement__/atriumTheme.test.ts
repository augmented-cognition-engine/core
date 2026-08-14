import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

const INDEX_CSS = path.resolve(__dirname, '..', '..', 'index.css')
const css = fs.readFileSync(INDEX_CSS, 'utf8')
const atriumBlock = css.match(/\.atrium-command-center\.dark\s*\{([\s\S]*?)\n\}/)?.[1]
const ATRIUM_APP = path.resolve(__dirname, '..', '..', 'app', 'atrium')
const atriumSources = fs.readdirSync(ATRIUM_APP)
  .filter((name) => name.endsWith('.tsx') && !name.endsWith('.test.tsx'))
  .map((name) => fs.readFileSync(path.join(ATRIUM_APP, name), 'utf8'))
  .join('\n')

function token(name: string): string {
  if (atriumBlock === undefined) throw new Error('Atrium theme block is missing')
  const value = atriumBlock.match(new RegExp(`${name}:\\s*(#[0-9A-Fa-f]{6})`))?.[1]
  if (value === undefined) throw new Error(`${name} is missing from the Atrium theme`)
  return value.toUpperCase()
}

function rgb(hex: string): [number, number, number] {
  return [
    Number.parseInt(hex.slice(1, 3), 16),
    Number.parseInt(hex.slice(3, 5), 16),
    Number.parseInt(hex.slice(5, 7), 16),
  ]
}

function luminance(hex: string): number {
  const channels = rgb(hex).map((channel) => {
    const value = channel / 255
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
}

function contrast(foreground: string, background: string): number {
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a)
  return (values[0] + 0.05) / (values[1] + 0.05)
}

describe('Atrium neutral-first theme', () => {
  it('keeps command-center surfaces achromatic instead of blue-tinted', () => {
    const surfaces = [
      '--background',
      '--card',
      '--popover',
      '--secondary',
      '--muted',
      '--accent',
      '--sidebar',
    ]

    for (const name of surfaces) {
      const channels = rgb(token(name))
      expect(Math.max(...channels) - Math.min(...channels), `${name} must remain achromatic`).toBeLessThanOrEqual(4)
    }
  })

  it('uses neutral actions and focus with semantic ACE spectrum roles', () => {
    expect(token('--primary')).toBe('#E7E5E1')
    expect(token('--brand')).toBe('#9777F5')
    expect(token('--ring')).toBe('#B4B2AF')
    expect(token('--live')).toBe('#58E8F9')
    expect(token('--evidence')).toBe('#2896E7')
    expect(token('--anchor')).toBe('#15151A')
  })

  it('keeps Atrium signature compositions scoped to the command center', () => {
    expect(css).toContain('.atrium-horizon {')
    expect(css).toContain('.atrium-cognitive-field {')
    expect(css).toContain('.atrium-opportunity-aperture {')
  })

  it('freezes the cognitive field when the user requests reduced motion', () => {
    expect(css).toContain('@media (prefers-reduced-motion: reduce)')
    expect(css).toContain('.atrium-cognitive-field.is-current .atrium-cognitive-nodes circle')
  })

  it('routes interactive Atrium controls through the shared shadcn layer', () => {
    expect(atriumSources).not.toMatch(/<(button|input|select|textarea|dialog)(\s|>)/)
    expect(atriumSources).toContain("from '@/design/shadcn/ui/button'")
    expect(atriumSources).toContain("from '@/design/shadcn/ui/dialog'")
    expect(atriumSources).toContain("from '@/design/shadcn/ui/input'")
    expect(atriumSources).toContain("from '@/design/shadcn/ui/sheet'")
  })

  it.each([
    ['foreground on canvas', '--foreground', '--background', 4.5],
    ['card foreground on card', '--card-foreground', '--card', 4.5],
    ['muted foreground on canvas', '--muted-foreground', '--background', 4.5],
    ['primary foreground on primary', '--primary-foreground', '--primary', 4.5],
    ['brand on canvas', '--brand', '--background', 4.5],
    ['brand on card', '--brand', '--card', 4.5],
    ['brand foreground on brand', '--brand-foreground', '--brand', 4.5],
    ['evidence on canvas', '--evidence', '--background', 3],
    ['evidence on card', '--evidence', '--card', 3],
    ['sidebar foreground on sidebar', '--sidebar-foreground', '--sidebar', 4.5],
    ['focus ring on canvas', '--ring', '--background', 3],
    ['live foreground on live', '--live-foreground', '--live', 4.5],
    ['success foreground on success', '--success-foreground', '--success', 4.5],
  ])('%s meets its contrast contract', (_label, foreground, background, minimum) => {
    expect(contrast(token(foreground), token(background))).toBeGreaterThanOrEqual(minimum)
  })
})
