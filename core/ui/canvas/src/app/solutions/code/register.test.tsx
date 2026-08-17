import { describe, expect, test } from 'vitest'

import {
  canvasNavItems,
  canvasRoutes,
  installedSolutions,
} from '../../ext/registry'
import codeIntelligenceSolution from './register'

describe('installed Code Intelligence Canvas contribution', () => {
  test('owns one exact route and matching additive navigation entry', () => {
    expect(codeIntelligenceSolution.name).toBe('code-intelligence')
    expect(codeIntelligenceSolution.routes?.map((route) => route.path)).toEqual([
      '/atrium/code',
    ])
    expect(codeIntelligenceSolution.navItems?.map(({ href, label }) => ({ href, label }))).toEqual([
      { href: '/atrium/code', label: 'Code' },
    ])
  })

  test('is discovered as an installed solution in the live Canvas registry', () => {
    expect(installedSolutions.map(({ name }) => name)).toContain('code-intelligence')
    expect(canvasRoutes().map(({ path }) => path)).toContain('/atrium/code')
    expect(canvasNavItems().map(({ href }) => href)).toContain('/atrium/code')
  })
})
