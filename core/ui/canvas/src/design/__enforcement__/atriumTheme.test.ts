import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

const INDEX_CSS = path.resolve(__dirname, '..', '..', 'index.css')
const css = fs.readFileSync(INDEX_CSS, 'utf8')
const atriumBlock = css.match(/\.atrium-command-center\.dark\s*\{([\s\S]*?)\n\}/)?.[1]

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

  it('uses neutral primary actions and one ACE-mark focus accent', () => {
    expect(token('--primary')).toBe('#E7E5E1')
    expect(token('--brand')).toBe('#9B7BF6')
    expect(token('--ring')).toBe('#9B7BF6')
    expect(token('--anchor')).toBe('#15151A')
  })

  it.each([
    ['foreground on canvas', '--foreground', '--background', 4.5],
    ['card foreground on card', '--card-foreground', '--card', 4.5],
    ['muted foreground on canvas', '--muted-foreground', '--background', 4.5],
    ['primary foreground on primary', '--primary-foreground', '--primary', 4.5],
    ['brand on canvas', '--brand', '--background', 4.5],
    ['brand on card', '--brand', '--card', 4.5],
    ['brand foreground on brand', '--brand-foreground', '--brand', 4.5],
    ['sidebar foreground on sidebar', '--sidebar-foreground', '--sidebar', 4.5],
    ['focus ring on canvas', '--ring', '--background', 3],
    ['live foreground on live', '--live-foreground', '--live', 4.5],
    ['success foreground on success', '--success-foreground', '--success', 4.5],
  ])('%s meets its contrast contract', (_label, foreground, background, minimum) => {
    expect(contrast(token(foreground), token(background))).toBeGreaterThanOrEqual(minimum)
  })
})
