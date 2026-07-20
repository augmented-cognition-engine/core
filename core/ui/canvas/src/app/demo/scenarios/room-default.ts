// core/ui/canvas/src/app/demo/scenarios/room-default.ts
//
// Room demo: replays the full multi-stage deliberation from the
// multiplayer fixture — prep → frame → choose → validate → critique — end to
// end on a compressed clock. The journey pipeline is shown up front (future
// stages as quiet stubs); each stage becomes current in turn and its tracks
// fill in, so the audience sees the whole deliberation progress, not a single
// stage. Content is derived from multiplayerFixture.journey so it stays in sync.
import { multiplayerFixture } from '../../fixtures/multiplayer'
import { registerScenario, type DemoScenario } from '../scenarios'
import type { DeliberationDemoStep } from '../useDemoJourney'
import type { DemoStep } from '../useScriptedTimeline'

function buildSteps(): DemoStep<DeliberationDemoStep>[] {
  const journey = multiplayerFixture.journey
  if (journey === undefined) return []

  // Stage shells: the full pipeline with empty tracks; stage 0 starts current,
  // the rest as future stubs. Other stage content (synthesis, capability graph,
  // working signals, decisions) is kept so it renders as each stage activates.
  const shells = journey.stages.map((s, i) => ({
    ...s,
    tracks: [],
    status: i === 0 ? ('current' as const) : ('future' as const),
  }))

  const steps: DemoStep<DeliberationDemoStep>[] = [
    {
      delayMs: 1,
      payload: { kind: 'init', topic: journey.topic, classification: journey.classification, stages: shells },
    },
  ]

  journey.stages.forEach((stage, i) => {
    steps.push({ delayMs: 900, payload: { kind: 'advance_stage', index: i } })
    for (const track of stage.tracks) {
      steps.push({
        delayMs: 500,
        // Settle the track (no permanent in-flight spinner) as it lands.
        payload: { kind: 'add_track', index: i, track: { ...track, inFlight: false } },
      })
    }
  })

  steps.push({ delayMs: 700, payload: { kind: 'finish' } })
  return steps
}

export const roomScenario: DemoScenario<DeliberationDemoStep> = {
  id: 'room',
  surface: 'room',
  defaultFor: 'room',
  topic: multiplayerFixture.journey?.topic ?? 'demo deliberation',
  steps: buildSteps(),
}

registerScenario(roomScenario)
