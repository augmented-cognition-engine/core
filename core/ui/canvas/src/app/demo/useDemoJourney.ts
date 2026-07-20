// core/ui/canvas/src/app/demo/useDemoJourney.ts
//
// Room demo journey. Produces an OrchestrationSessionState-shaped object
// the surface can render, by progressively revealing a MULTI-STAGE deliberation
// (prep → frame → choose → validate → critique) end to end — not collapsed onto
// a single live stage. No REST, no WebSocket. The timeline lives here, so the
// presenter gets full pause/step/replay.
//
// The scenario is a list of mutation "steps": an `init` (the full stage pipeline
// with empty tracks), then `advance_stage` + `add_track` beats that walk the
// journey and fill each stage as it becomes current, ending on `finish`.
import { useCallback, useMemo, useReducer } from 'react'

import type {
  DeliberationJourneyState,
  JourneyClassification,
  JourneyStage,
  JourneyTrack,
  StageStatus,
} from '../../types/canvas'
import { freshInitialState, type OrchestrationSessionState } from '../journey/useOrchestrationSession'
import type { DemoScenario } from './scenarios'
import { useScriptedTimeline, type TimelineControls } from './useScriptedTimeline'

export type DeliberationDemoStep =
  | { kind: 'init'; topic: string; classification: JourneyClassification; stages: JourneyStage[] }
  | { kind: 'advance_stage'; index: number }
  | { kind: 'add_track'; index: number; track: JourneyTrack }
  | { kind: 'finish' }

function statusFor(i: number, currentIndex: number): StageStatus {
  return i < currentIndex ? 'past' : i === currentIndex ? 'current' : 'future'
}

function reducer(
  state: OrchestrationSessionState,
  step: DeliberationDemoStep,
): OrchestrationSessionState {
  switch (step.kind) {
    case 'init': {
      const journey: DeliberationJourneyState = {
        topic: step.topic,
        classification: step.classification,
        stages: step.stages,
      }
      return { ...freshInitialState(), status: 'streaming', journey }
    }
    case 'advance_stage': {
      const j = state.journey
      if (j === null) return state
      const stages = j.stages.map((s, i) => ({ ...s, status: statusFor(i, step.index) }))
      return { ...state, journey: { ...j, stages } }
    }
    case 'add_track': {
      const j = state.journey
      if (j === null) return state
      const stages = j.stages.map((s, i) =>
        i === step.index ? { ...s, tracks: [...s.tracks, step.track] } : s,
      )
      return { ...state, journey: { ...j, stages } }
    }
    case 'finish':
      return { ...state, status: 'done' }
  }
}

export interface DemoJourney {
  state: OrchestrationSessionState
  controls: TimelineControls
}

export function useDemoJourney(
  scenario: DemoScenario<DeliberationDemoStep> | null,
): DemoJourney {
  // The first step is `init`; apply it synchronously at mount so the journey is
  // non-null and status='streaming' immediately (the surface's useLive flips on
  // before the first animated beat). The timeline animates steps[1..].
  const initStep = scenario?.steps[0]?.payload
  // Memoize the sliced animation steps — a fresh array each render would make
  // useScriptedTimeline's effect (keyed on steps identity) reset every render,
  // causing an infinite re-render loop.
  const animSteps = useMemo(
    () => (scenario === null ? null : scenario.steps.slice(1)),
    [scenario],
  )

  const [state, dispatch] = useReducer(
    reducer,
    initStep,
    (s): OrchestrationSessionState =>
      s !== undefined && s.kind === 'init' ? reducer(freshInitialState(), s) : freshInitialState(),
  )

  const apply = useCallback((step: DeliberationDemoStep) => dispatch(step), [])
  const base = useScriptedTimeline<DeliberationDemoStep>(animSteps, apply)

  // Replay re-applies the init (clearing revealed tracks) then re-runs.
  const replay = useCallback(() => {
    if (initStep !== undefined) dispatch(initStep)
    base.replay()
  }, [base, initStep])

  return { state, controls: { ...base, replay } }
}
