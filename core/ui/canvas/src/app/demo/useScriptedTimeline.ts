// core/ui/canvas/src/app/demo/useScriptedTimeline.ts
//
// Generic timed-replay engine. Walks a list of {delayMs, payload} beats
// on a compressed clock, calling `apply(payload)` for each. Surface-
// agnostic: the only coupling is the `apply` callback, so the same engine
// drives Brief Composer (reducer actions) and the room (WS events).
//
// Refs + a force-render counter are used so the setTimeout callback always
// reads the latest index/status without re-subscribing the timer on every
// render — the returned object reads ref.current at render time, and every
// state change calls force() to re-render with fresh values.
import { useCallback, useEffect, useReducer, useRef } from 'react'

export interface DemoStep<P> {
  /** Delay BEFORE applying this beat, relative to the previous beat (ms). */
  delayMs: number
  payload: P
}

export type TimelineStatus = 'idle' | 'playing' | 'paused' | 'done'

export interface TimelineControls {
  status: TimelineStatus
  /** Beats applied so far. */
  index: number
  total: number
  play: () => void
  pause: () => void
  /** Apply the next queued beat immediately; re-base the remaining schedule. */
  step: () => void
  /** Reset to the start and play. */
  replay: () => void
}

export interface ScriptedTimelineOptions {
  autoplay?: boolean
  /** Delay multiplier — 2 runs twice as fast. Default 1. */
  speed?: number
}

export function useScriptedTimeline<P>(
  steps: DemoStep<P>[] | null,
  apply: (payload: P) => void,
  opts: ScriptedTimelineOptions = {},
): TimelineControls {
  const speed = opts.speed ?? 1
  const autoplay = opts.autoplay ?? true

  const applyRef = useRef(apply)
  applyRef.current = apply
  const stepsRef = useRef(steps)
  stepsRef.current = steps

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const indexRef = useRef(0)
  const statusRef = useRef<TimelineStatus>('idle')
  const [, force] = useReducer((n: number) => n + 1, 0)

  const clear = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const scheduleNext = useCallback(() => {
    const s = stepsRef.current
    if (s === null) return
    if (indexRef.current >= s.length) {
      statusRef.current = 'done'
      force()
      return
    }
    const next = s[indexRef.current]
    const delay = Math.max(0, next.delayMs / speed)
    timerRef.current = setTimeout(() => {
      applyRef.current(next.payload)
      indexRef.current += 1
      if (statusRef.current === 'playing') {
        scheduleNext()
      } else {
        force()
      }
    }, delay)
  }, [speed])

  const play = useCallback(() => {
    const s = stepsRef.current
    if (s === null || indexRef.current >= s.length) return
    clear()
    statusRef.current = 'playing'
    force()
    scheduleNext()
  }, [clear, scheduleNext])

  const pause = useCallback(() => {
    clear()
    statusRef.current = 'paused'
    force()
  }, [clear])

  const step = useCallback(() => {
    const s = stepsRef.current
    if (s === null) return
    clear()
    if (indexRef.current < s.length) {
      applyRef.current(s[indexRef.current].payload)
      indexRef.current += 1
    }
    if (indexRef.current >= s.length) {
      statusRef.current = 'done'
    } else if (statusRef.current === 'playing') {
      scheduleNext()
    } else {
      statusRef.current = 'paused'
    }
    force()
  }, [clear, scheduleNext])

  const replay = useCallback(() => {
    clear()
    indexRef.current = 0
    statusRef.current = 'playing'
    force()
    scheduleNext()
  }, [clear, scheduleNext])

  // (Re)start when the steps array identity changes.
  useEffect(() => {
    clear()
    indexRef.current = 0
    statusRef.current = steps === null ? 'idle' : autoplay ? 'playing' : 'idle'
    force()
    if (steps !== null && autoplay) scheduleNext()
    return () => clear()
  }, [steps, autoplay, scheduleNext, clear])

  return {
    status: statusRef.current,
    index: indexRef.current,
    total: steps?.length ?? 0,
    play,
    pause,
    step,
    replay,
  }
}
