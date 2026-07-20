// app/usePredictionOutcomes.test.ts
//
// Hook-level tests for the L9 prediction-lifecycle subscription. The
// CanvasSocket module is mocked so tests can push synthesized wire
// messages through the registered handler and assert the resulting
// hook state — no WebSocket, no backend.
//
// Covered:
//   - prediction.outcome.closed appends to `outcomes`
//   - decision.prediction.attached lands in `lastAttached`
//   - unrelated / malformed events are ignored
//   - no sessionId → no socket subscription at all
//   - outcomeToBannerState maps a closed outcome onto the existing
//     ReconciliationBanner prop contract (archetype + predicted vs
//     actual + calibration movement)

import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import type {
  DecisionPredictionAttachedPayload,
  PredictionOutcomeClosedPayload,
} from '../types/canvas'
import { outcomeToBannerState, usePredictionOutcomes } from './usePredictionOutcomes'

type MessageHandler = (event: Record<string, unknown>) => void

const socketSpy = vi.hoisted(() => ({
  handlers: [] as MessageHandler[],
  constructed: [] as string[],
  connectCount: 0,
  closeCount: 0,
}))

vi.mock('../api/canvasSocket', () => {
  class FakeCanvasSocket {
    constructor(sessionId: string) {
      socketSpy.constructed.push(sessionId)
    }

    onMessage(handler: MessageHandler) {
      socketSpy.handlers.push(handler)
      return () => {
        socketSpy.handlers = socketSpy.handlers.filter((h) => h !== handler)
      }
    }

    connect() {
      socketSpy.connectCount += 1
    }

    close() {
      socketSpy.closeCount += 1
    }
  }
  return { CanvasSocket: FakeCanvasSocket }
})

function emit(msg: Record<string, unknown>) {
  act(() => {
    socketSpy.handlers.forEach((h) => h(msg))
  })
}

const CLOSED: PredictionOutcomeClosedPayload = {
  prediction_id: 'decision_prediction:p1',
  agent_id: 'skeptic',
  archetype: 'skeptic',
  predicted: 0.3,
  actual: 0.1,
  predicted_deltas: { 'capability:auth': 0.3 },
  actual_deltas: { 'capability:auth': 0.1 },
  calibration_score: 0.9,
  weight_delta: -0.03,
  discipline: 'security',
}

const ATTACHED: DecisionPredictionAttachedPayload = {
  decision_id: 'decision:d1',
  prediction_id: 'decision_prediction:p1',
  agent_id: 'skeptic',
  predicted_delta: 0.3,
  falsifier: 'CIO churn > 5%',
  horizon_days: 30,
}

beforeEach(() => {
  socketSpy.handlers = []
  socketSpy.constructed = []
  socketSpy.connectCount = 0
  socketSpy.closeCount = 0
})

describe('usePredictionOutcomes', () => {
  test('starts empty and subscribes with the session id', () => {
    const { result } = renderHook(() => usePredictionOutcomes('canvas_session:abc'))
    expect(result.current.outcomes).toEqual([])
    expect(result.current.lastAttached).toBeNull()
    expect(socketSpy.constructed).toEqual(['canvas_session:abc'])
    expect(socketSpy.connectCount).toBe(1)
  })

  test('no sessionId → no socket at all', () => {
    renderHook(() => usePredictionOutcomes(null))
    renderHook(() => usePredictionOutcomes(undefined))
    renderHook(() => usePredictionOutcomes(''))
    expect(socketSpy.constructed).toEqual([])
    expect(socketSpy.handlers).toHaveLength(0)
  })

  test('prediction.outcome.closed appends to outcomes in arrival order', () => {
    const { result } = renderHook(() => usePredictionOutcomes('canvas_session:abc'))

    emit({ event_type: 'prediction.outcome.closed', payload: CLOSED })
    emit({
      event_type: 'prediction.outcome.closed',
      payload: { ...CLOSED, prediction_id: 'decision_prediction:p2' },
    })

    expect(result.current.outcomes).toHaveLength(2)
    expect(result.current.outcomes[0].prediction_id).toBe('decision_prediction:p1')
    expect(result.current.outcomes[1].prediction_id).toBe('decision_prediction:p2')
    expect(result.current.outcomes[0].calibration_score).toBe(0.9)
    expect(result.current.outcomes[0].weight_delta).toBe(-0.03)
  })

  test('decision.prediction.attached lands in lastAttached', () => {
    const { result } = renderHook(() => usePredictionOutcomes('canvas_session:abc'))

    emit({ event_type: 'decision.prediction.attached', payload: ATTACHED })

    expect(result.current.lastAttached).not.toBeNull()
    expect(result.current.lastAttached?.prediction_id).toBe('decision_prediction:p1')
    expect(result.current.lastAttached?.horizon_days).toBe(30)
    expect(result.current.outcomes).toEqual([])
  })

  test('unrelated and malformed events are ignored', () => {
    const { result } = renderHook(() => usePredictionOutcomes('canvas_session:abc'))

    emit({ event_type: 'composition.selected', payload: { meta_skills: [] } })
    emit({ event_type: 'prediction.outcome.closed' }) // no payload
    emit({ event_type: 'prediction.outcome.closed', payload: 'not-an-object' })
    emit({ event_type: 'decision.prediction.attached', payload: null })

    expect(result.current.outcomes).toEqual([])
    expect(result.current.lastAttached).toBeNull()
  })

  test('unmount unsubscribes and closes the socket', () => {
    const { unmount } = renderHook(() => usePredictionOutcomes('canvas_session:abc'))
    expect(socketSpy.handlers).toHaveLength(1)
    unmount()
    expect(socketSpy.handlers).toHaveLength(0)
    expect(socketSpy.closeCount).toBe(1)
  })
})

describe('outcomeToBannerState', () => {
  test('maps a closed outcome onto the ReconciliationBanner contract', () => {
    const banner = outcomeToBannerState(CLOSED)
    expect(banner.active).toBe(true)
    expect(banner.horizonLabel).toBe('just closed')
    // Archetype + predicted vs actual, signed two-decimal deltas.
    expect(banner.decisionTitle).toBe('Skeptic predicted +0.30, actual +0.10')
    // Calibration movement: per-outcome score + the EMA weight shift.
    expect(banner.outcomeHint).toBe('calibration 0.90 · weight -0.03')
  })

  test('formats negative deltas and snake_case archetypes', () => {
    const banner = outcomeToBannerState({
      ...CLOSED,
      archetype: 'risk_intelligence',
      predicted: -0.25,
      actual: -0.4,
      calibration_score: 0.925,
      weight_delta: 0.12,
    })
    expect(banner.decisionTitle).toBe('Risk intelligence predicted -0.25, actual -0.40')
    expect(banner.outcomeHint).toBe('calibration 0.93 · weight +0.12')
  })
})
