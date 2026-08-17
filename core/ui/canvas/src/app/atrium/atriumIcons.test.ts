import {
  Database,
  History,
  Radio,
  ShieldCheck,
} from 'lucide-react'
import { describe, expect, it } from 'vitest'

import {
  ATRIUM_ACTION_ICONS,
  ATRIUM_DOWNSTREAM_ICONS,
  ATRIUM_INTELLIGENCE_ICONS,
  ATRIUM_SURFACE_ICONS,
  atriumIconForResourceKind,
} from './atriumIcons'

describe('Atrium icon taxonomy', () => {
  it('gives every primary surface a distinct icon', () => {
    expect(new Set(Object.values(ATRIUM_SURFACE_ICONS)).size).toBe(5)
  })

  it('reserves the shield for the Operate surface', () => {
    expect(ATRIUM_SURFACE_ICONS.operate).toBe(ShieldCheck)

    for (const [surface, icon] of Object.entries(ATRIUM_SURFACE_ICONS)) {
      if (surface !== 'operate') expect(icon).not.toBe(ShieldCheck)
    }

    expect(Object.values(ATRIUM_ACTION_ICONS)).not.toContain(ShieldCheck)
    expect(Object.values(ATRIUM_DOWNSTREAM_ICONS)).not.toContain(ShieldCheck)
    expect(Object.values(ATRIUM_INTELLIGENCE_ICONS)).not.toContain(ShieldCheck)
    expect(atriumIconForResourceKind('source_health')).not.toBe(ShieldCheck)
    expect(atriumIconForResourceKind('feedback')).not.toBe(ShieldCheck)
  })

  it('uses literal resource semantics instead of a generic AI glyph', () => {
    expect(atriumIconForResourceKind('source')).toBe(Database)
    expect(atriumIconForResourceKind('signal')).toBe(Radio)
    expect(atriumIconForResourceKind('memory_use')).toBe(History)
  })
})
