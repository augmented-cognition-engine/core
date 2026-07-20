// core/ui/canvas/src/app/usePredictionOutcomes.ts
//
// Subscribes to the canvas WebSocket and accumulates the L9 prediction
// lifecycle for the active session:
//
//   decision.prediction.attached  → a falsifiable forecast was pinned to
//                                   a decision (forecaster)
//   prediction.outcome.closed     → the horizon lapsed; the reconciler
//                                   scored the forecast and moved the
//                                   archetype's calibration (reconciler)
//
// This is the "loop closes visibly" wire: the backend already emits both
// events; this hook surfaces them into React state so the reconciliation
// banner and the calibration ledger update in real time instead of the
// learning loop finishing silently in the database.
//
// Pattern (mirrors useLiveComposition):
//   const { outcomes, lastAttached } = usePredictionOutcomes(sessionId)
//   const banner = outcomes.length ? outcomeToBannerState(outcomes.at(-1)!) : undefined
import { useEffect, useState } from 'react'

import { CanvasSocket } from '../api/canvasSocket'
import {
  LCE_DECISION_PREDICTION_ATTACHED,
  LCE_PREDICTION_OUTCOME_CLOSED,
  type DecisionPredictionAttachedPayload,
  type PredictionOutcomeClosedPayload,
} from '../types/canvas'
import type { ReconciliationBannerState } from './state'

export interface PredictionLifecycleState {
  /** Closed outcomes in arrival order — newest last. */
  outcomes: PredictionOutcomeClosedPayload[]
  /** The most recent forecast attached to a decision, if any. */
  lastAttached: DecisionPredictionAttachedPayload | null
}

interface PredictionEventEnvelope {
  event_type?: string
  payload?: unknown
}

/** Type guard: a prediction.outcome.closed event with a usable payload. */
function isOutcomeClosed(
  msg: Record<string, unknown>,
): msg is { event_type: string; payload: PredictionOutcomeClosedPayload } {
  const envelope = msg as PredictionEventEnvelope
  if (envelope.event_type !== LCE_PREDICTION_OUTCOME_CLOSED) return false
  const payload = envelope.payload
  if (payload === null || payload === undefined || typeof payload !== 'object') return false
  // Minimal shape check — prediction_id is the load-bearing field
  return typeof (payload as PredictionOutcomeClosedPayload).prediction_id === 'string'
}

/** Type guard: a decision.prediction.attached event with a usable payload. */
function isPredictionAttached(
  msg: Record<string, unknown>,
): msg is { event_type: string; payload: DecisionPredictionAttachedPayload } {
  const envelope = msg as PredictionEventEnvelope
  if (envelope.event_type !== LCE_DECISION_PREDICTION_ATTACHED) return false
  const payload = envelope.payload
  if (payload === null || payload === undefined || typeof payload !== 'object') return false
  return typeof (payload as DecisionPredictionAttachedPayload).prediction_id === 'string'
}

export function usePredictionOutcomes(
  sessionId: string | null | undefined,
): PredictionLifecycleState {
  const [state, setState] = useState<PredictionLifecycleState>({
    outcomes: [],
    lastAttached: null,
  })

  useEffect(() => {
    if (sessionId === null || sessionId === undefined || sessionId === '') return

    const socket = new CanvasSocket(sessionId)
    const unsubscribe = socket.onMessage((msg) => {
      if (isOutcomeClosed(msg)) {
        setState((prev) => ({ ...prev, outcomes: [...prev.outcomes, msg.payload] }))
      } else if (isPredictionAttached(msg)) {
        setState((prev) => ({ ...prev, lastAttached: msg.payload }))
      }
    })
    socket.connect()

    return () => {
      unsubscribe()
      socket.close()
    }
  }, [sessionId])

  return state
}

/** Signed two-decimal delta, e.g. +0.30 / -0.03. */
function signed(value: number): string {
  return value >= 0 ? `+${value.toFixed(2)}` : value.toFixed(2)
}

/** 'risk_intelligence' → 'Risk intelligence'. */
function humanizeArchetype(archetype: string): string {
  const spaced = archetype.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

/** Map a closed outcome onto the existing ReconciliationBanner contract.
 *
 *  The banner names who called it, what they predicted vs what landed,
 *  and how the calibration moved — e.g.
 *  "Skeptic predicted +0.30, actual +0.10 · calibration 0.90 · weight -0.03".
 */
export function outcomeToBannerState(
  outcome: PredictionOutcomeClosedPayload,
): ReconciliationBannerState {
  return {
    active: true,
    horizonLabel: 'just closed',
    decisionTitle: `${humanizeArchetype(outcome.archetype)} predicted ${signed(
      outcome.predicted,
    )}, actual ${signed(outcome.actual)}`,
    outcomeHint: `calibration ${outcome.calibration_score.toFixed(2)} · weight ${signed(
      outcome.weight_delta,
    )}`,
  }
}
