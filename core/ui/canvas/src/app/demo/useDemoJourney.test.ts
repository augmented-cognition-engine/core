// core/ui/canvas/src/app/demo/useDemoJourney.test.ts
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { roomScenario } from './scenarios/room-default'
import { useDemoJourney } from './useDemoJourney'

beforeEach(() => {
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
})

describe('useDemoJourney', () => {
  test('replays the scenario to a done journey without any WebSocket', () => {
    const wsSpy = vi.spyOn(globalThis, 'WebSocket' as never)
    const { result } = renderHook(() => useDemoJourney(roomScenario))

    // Journey activates immediately (status streaming, journey non-null)
    // so the surface's useLive flips on before any beat lands.
    expect(result.current.state.status).toBe('streaming')
    expect(result.current.state.journey).not.toBeNull()

    act(() => {
      vi.advanceTimersByTime(60_000)
    })

    expect(result.current.state.status).toBe('done')
    const tracks = result.current.state.journey?.stages.flatMap((s) => s.tracks) ?? []
    expect(tracks.length).toBeGreaterThanOrEqual(2)
    expect(tracks.every((t) => t.contribution.length > 0)).toBe(true)
    expect(wsSpy).not.toHaveBeenCalled()
  })

  test('null scenario is inert (idle, null journey)', () => {
    const { result } = renderHook(() => useDemoJourney(null))
    expect(result.current.state.status).toBe('idle')
    expect(result.current.state.journey).toBeNull()
  })

  test('replay resets the journey then re-runs (no duplicate tracks)', () => {
    const { result } = renderHook(() => useDemoJourney(roomScenario))
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    const firstCount = result.current.state.journey?.stages.flatMap((s) => s.tracks).length ?? 0
    act(() => {
      result.current.controls.replay()
    })
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    const secondCount = result.current.state.journey?.stages.flatMap((s) => s.tracks).length ?? 0
    expect(secondCount).toBe(firstCount)
  })
})
