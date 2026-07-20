// core/ui/canvas/src/app/demo/useScriptedTimeline.test.ts
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { useScriptedTimeline, type DemoStep } from './useScriptedTimeline'

const steps: DemoStep<string>[] = [
  { delayMs: 100, payload: 'a' },
  { delayMs: 100, payload: 'b' },
  { delayMs: 100, payload: 'c' },
]

beforeEach(() => {
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
})

describe('useScriptedTimeline', () => {
  test('autoplay applies beats in order on the cumulative clock', () => {
    const applied: string[] = []
    const { result } = renderHook(() => useScriptedTimeline(steps, (p) => applied.push(p)))
    expect(result.current.status).toBe('playing')
    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(applied).toEqual(['a'])
    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(applied).toEqual(['a', 'b', 'c'])
    expect(result.current.status).toBe('done')
  })

  test('pause halts scheduling; play resumes', () => {
    const applied: string[] = []
    const { result } = renderHook(() => useScriptedTimeline(steps, (p) => applied.push(p)))
    act(() => {
      vi.advanceTimersByTime(100)
    }) // 'a'
    act(() => {
      result.current.pause()
    })
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(applied).toEqual(['a'])
    expect(result.current.status).toBe('paused')
    act(() => {
      result.current.play()
    })
    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(applied).toEqual(['a', 'b', 'c'])
  })

  test('step applies exactly one beat while paused', () => {
    const applied: string[] = []
    const { result } = renderHook(() =>
      useScriptedTimeline(steps, (p) => applied.push(p), { autoplay: false }),
    )
    expect(result.current.status).toBe('idle')
    act(() => {
      result.current.step()
    })
    expect(applied).toEqual(['a'])
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(applied).toEqual(['a']) // no auto-advance after a step while not playing
  })

  test('replay restarts from the beginning', () => {
    const applied: string[] = []
    const { result } = renderHook(() => useScriptedTimeline(steps, (p) => applied.push(p)))
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(applied).toEqual(['a', 'b', 'c'])
    act(() => {
      result.current.replay()
    })
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(applied).toEqual(['a', 'b', 'c', 'a', 'b', 'c'])
  })

  test('speed scales delays', () => {
    const applied: string[] = []
    renderHook(() => useScriptedTimeline(steps, (p) => applied.push(p), { speed: 2 }))
    act(() => {
      vi.advanceTimersByTime(50)
    }) // 100/2
    expect(applied).toEqual(['a'])
  })

  test('unmount cancels pending beats', () => {
    const applied: string[] = []
    const { unmount } = renderHook(() => useScriptedTimeline(steps, (p) => applied.push(p)))
    unmount()
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(applied).toEqual([])
  })

  test('null steps is inert', () => {
    const applied: string[] = []
    const { result } = renderHook(() => useScriptedTimeline<string>(null, (p) => applied.push(p)))
    expect(result.current.status).toBe('idle')
    expect(result.current.total).toBe(0)
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(applied).toEqual([])
  })
})
