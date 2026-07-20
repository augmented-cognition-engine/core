// core/ui/canvas/src/app/demo/scenarios/room-default.test.ts
import { describe, expect, test } from 'vitest'

import { roomScenario } from './room-default'

describe('roomScenario', () => {
  test('registers for the room surface as default, with a topic', () => {
    expect(roomScenario.surface).toBe('room')
    expect(roomScenario.defaultFor).toBe('room')
    expect(typeof roomScenario.topic).toBe('string')
    expect((roomScenario.topic ?? '').length).toBeGreaterThan(0)
  })

  test('begins with an init that seeds the full multi-stage pipeline', () => {
    const first = roomScenario.steps[0]?.payload
    expect(first?.kind).toBe('init')
    if (first?.kind !== 'init') throw new Error('first step must be init')
    // End-to-end means MULTIPLE stages, not one.
    expect(first.stages.length).toBeGreaterThanOrEqual(3)
    // Shells start empty — tracks are revealed by the animated steps.
    expect(first.stages.every((s) => s.tracks.length === 0)).toBe(true)
  })

  test('walks more than one stage and fills tracks, ending on finish', () => {
    const kinds = roomScenario.steps.map((s) => s.payload.kind)
    const advancedIndices = new Set(
      roomScenario.steps
        .filter((s) => s.payload.kind === 'advance_stage')
        .map((s) => (s.payload as { index: number }).index),
    )
    expect(advancedIndices.size).toBeGreaterThanOrEqual(3) // multi-stage walk
    expect(kinds.filter((k) => k === 'add_track').length).toBeGreaterThanOrEqual(2)
    expect(kinds[kinds.length - 1]).toBe('finish')
  })
})
