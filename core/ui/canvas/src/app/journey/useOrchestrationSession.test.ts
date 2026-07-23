// app/journey/useOrchestrationSession.test.ts
//
// Reducer-level tests for the live ACE orchestration session. These
// validate the event → JourneyState projection without needing a
// running backend — feed synthesized WsInbound events into
// applyRemoteEvent and assert on the resulting state.
//
// What these tests cover (Phase 1 + 2 protocol surface):
//   - classification populates L2 metadata
//   - engagement_start adds a track with inFlight=true
//   - token / agent_token streams into the live track contribution
//   - engagement_done finalizes the track
//   - decision_captured / prediction_attached / sentinel_event attach
//     to the live stage
//   - run_done marks the live stage past
//   - hello / ping / unknown frames are pass-through (no state change)

import { describe, expect, test } from 'vitest'

import {
  applyRemoteEvent,
  freshInitialState,
  orchestrationSessionStartMode,
  reconnectBackoffMs,
  steerFrame,
} from './useOrchestrationSession'

describe('orchestrationSessionStartMode', () => {
  test('replays only when both durable session and run coordinates are present', () => {
    expect(orchestrationSessionStartMode(null, {
      resumeSessionId: 'session:one',
      resumeRunId: 'run:one',
    })).toBe('resume')
    expect(orchestrationSessionStartMode(null, { resumeSessionId: 'session:one' })).toBe('idle')
  })

  test('starts fresh only from a non-empty topic', () => {
    expect(orchestrationSessionStartMode('  decide this  ', {})).toBe('fresh')
    expect(orchestrationSessionStartMode('  ', {})).toBe('idle')
    expect(orchestrationSessionStartMode(null, {})).toBe('idle')
  })
})

describe('steerFrame', () => {
  test('builds the same {type:message} frame the initial topic uses', () => {
    expect(steerFrame('slow down on pricing')).toBe(
      JSON.stringify({ type: 'message', content: 'slow down on pricing' }),
    )
  })

  test('trims surrounding whitespace', () => {
    expect(steerFrame('  hold on  ')).toBe(JSON.stringify({ type: 'message', content: 'hold on' }))
  })

  test('returns null for empty / whitespace-only input (nothing to send)', () => {
    expect(steerFrame('')).toBeNull()
    expect(steerFrame('   ')).toBeNull()
    expect(steerFrame('\n\t')).toBeNull()
  })
})

const TOPIC = 'Should we ship the AI-first hero?'

function topicState() {
  // After dispatch({type: 'reset', topic}) the reducer sets status=creating
  // and journey=initialJourney(topic). We mirror that minimal precondition.
  const base = freshInitialState()
  return applyRemoteEvent(base, { type: 'run_start', run_id: 'r1', task_id: 't0' }, TOPIC)
}

describe('applyRemoteEvent', () => {
  test('hello + ping are no-ops', () => {
    const s0 = topicState()
    const sHello = applyRemoteEvent(
      s0,
      { type: 'hello', session_id: 'sess1', product_id: 'product:platform', active_runs: [] },
      TOPIC,
    )
    const sPing = applyRemoteEvent(sHello, { type: 'ping' }, TOPIC)
    expect(sPing).toEqual(sHello)
    expect(sHello.journey).toEqual(s0.journey)
  })

  test('classification populates L2 metadata', () => {
    const s0 = topicState()
    const s1 = applyRemoteEvent(
      s0,
      {
        type: 'classification',
        run_id: 'r1',
        task_id: 't-class',
        discipline: 'product_strategy',
        archetypes: ['strategic_intelligence', 'risk_intelligence'],
        depth: 3,
      },
      TOPIC,
    )
    expect(s1.journey?.classification.discipline).toBe('product_strategy')
    expect(s1.journey?.classification.archetype).toBe('strategic_intelligence')
    expect(s1.journey?.classification.depth).toBe(3)
    expect(s1.journey?.classification.fusionMode).toBe(false)
    expect(s1.journey?.classification.metaSkills).toEqual([
      'strategic_intelligence',
      'risk_intelligence',
    ])
  })

  test('engagement_start adds a track with inFlight=true', () => {
    const s0 = topicState()
    const s1 = applyRemoteEvent(
      s0,
      {
        type: 'engagement_start',
        run_id: 'r1',
        task_id: 't-eng-1',
        pattern: 'strategy-palerise',
        archetypes: ['strategic_intelligence'],
      },
      TOPIC,
    )
    const liveStage = s1.journey?.stages.find((s) => s.status === 'current')
    expect(liveStage?.tracks).toHaveLength(1)
    expect(liveStage?.tracks[0].metaSkill).toBe('strategic_intelligence')
    expect(liveStage?.tracks[0].inFlight).toBe(true)
    expect(liveStage?.tracks[0].instrument).toBe('strategy-palerise')
  })

  test('token events stream into the live track contribution', () => {
    let s = topicState()
    s = applyRemoteEvent(
      s,
      {
        type: 'engagement_start',
        task_id: 't-eng-1',
        pattern: 'strategy-palerise',
        archetypes: ['strategic_intelligence'],
      },
      TOPIC,
    )
    s = applyRemoteEvent(s, { type: 'token', task_id: 't-eng-1', content: 'Pivot ' }, TOPIC)
    s = applyRemoteEvent(s, { type: 'token', task_id: 't-eng-1', content: 'fully.' }, TOPIC)

    const liveStage = s.journey?.stages.find((st) => st.status === 'current')
    expect(liveStage?.tracks[0].contribution).toBe('Pivot fully.')
    expect(liveStage?.tracks[0].inFlight).toBe(true)
    expect(s.tokenBuffers['t-eng-1']).toBe('Pivot fully.')
  })

  test('engagement_done finalizes the track', () => {
    let s = topicState()
    s = applyRemoteEvent(
      s,
      { type: 'engagement_start', task_id: 't-eng-1', archetypes: ['risk_intelligence'] },
      TOPIC,
    )
    s = applyRemoteEvent(s, { type: 'token', task_id: 't-eng-1', content: 'CIO drift risk' }, TOPIC)
    s = applyRemoteEvent(s, { type: 'engagement_done', task_id: 't-eng-1' }, TOPIC)

    const liveStage = s.journey?.stages.find((st) => st.status === 'current')
    expect(liveStage?.tracks[0].inFlight).toBe(false)
    expect(liveStage?.tracks[0].contribution).toBe('CIO drift risk')
    expect(s.tokenBuffers['t-eng-1']).toBeUndefined()
  })

  test('agent_token also streams (alternative wire shape)', () => {
    let s = topicState()
    s = applyRemoteEvent(
      s,
      { type: 'engagement_start', task_id: 't-eng-1', archetypes: ['planning_intelligence'] },
      TOPIC,
    )
    s = applyRemoteEvent(
      s,
      { type: 'agent_token', task_id: 't-eng-1', agent_id: 'planner', text: 'Sequence Q3 first.' },
      TOPIC,
    )
    const liveStage = s.journey?.stages.find((st) => st.status === 'current')
    expect(liveStage?.tracks[0].contribution).toBe('Sequence Q3 first.')
  })

  test('decision_captured attaches to the live stage', () => {
    const s0 = topicState()
    const s1 = applyRemoteEvent(
      s0,
      { type: 'decision_captured', task_id: 't-dec', decision_id: 'dec_42' },
      TOPIC,
    )
    const liveStage = s1.journey?.stages.find((st) => st.status === 'current')
    expect(liveStage?.decisions).toHaveLength(1)
    expect(liveStage?.decisions?.[0].id).toBe('dec_42')
  })

  test('prediction_attached attaches with horizon + falsification', () => {
    const s0 = topicState()
    const s1 = applyRemoteEvent(
      s0,
      {
        type: 'prediction_attached',
        task_id: 't-pred',
        prediction_id: 'pred_7',
        horizon_days: 60,
        falsification_condition: 'CIO churn > 5%',
      },
      TOPIC,
    )
    const liveStage = s1.journey?.stages.find((st) => st.status === 'current')
    expect(liveStage?.prediction?.horizonDays).toBe(60)
    expect(liveStage?.prediction?.falsifyIf).toBe('CIO churn > 5%')
  })

  test('sentinel_event severity is normalized', () => {
    const s0 = topicState()
    const sHigh = applyRemoteEvent(
      s0,
      { type: 'sentinel_event', task_id: 't-sn-1', engine: 'perspective_gaps', severity: 'high', summary: 'no CFO voice' },
      TOPIC,
    )
    const sUnknown = applyRemoteEvent(
      sHigh,
      { type: 'sentinel_event', task_id: 't-sn-2', engine: 'competitive', severity: 'critical', summary: 'AWS preempted' },
      TOPIC,
    )
    const liveStage = sUnknown.journey?.stages.find((st) => st.status === 'current')
    expect(liveStage?.sentinel).toHaveLength(2)
    expect(liveStage?.sentinel?.[0].severity).toBe('high')
    // Unknown severity ('critical') normalizes to 'medium' — protocol defensive.
    expect(liveStage?.sentinel?.[1].severity).toBe('medium')
  })

  test('run_done marks live stage past and drops inFlight on tracks', () => {
    let s = topicState()
    s = applyRemoteEvent(
      s,
      { type: 'engagement_start', task_id: 't-eng-1', archetypes: ['strategic_intelligence'] },
      TOPIC,
    )
    s = applyRemoteEvent(s, { type: 'run_done', task_id: 't-end', duration_ms: 4200 }, TOPIC)
    expect(s.status).toBe('done')
    const past = s.journey?.stages.find((st) => st.id === 'live')
    expect(past?.status).toBe('past')
    expect(past?.tracks[0].inFlight).toBe(false)
  })

  test('tool_call records an in-flight call keyed by task_id', () => {
    const s0 = topicState()
    const s1 = applyRemoteEvent(
      s0,
      {
        type: 'tool_call',
        task_id: 't-tool-1',
        tool: 'ace_search',
        input_summary: 'recent decisions about launch positioning',
      },
      TOPIC,
    )
    expect(s1.toolCalls['t-tool-1'].tool).toBe('ace_search')
    expect(s1.toolCalls['t-tool-1'].inputSummary).toBe(
      'recent decisions about launch positioning',
    )
    expect(s1.toolCalls['t-tool-1'].resolvedAt).toBeUndefined()
  })

  test('tool_result resolves the matching call', () => {
    let s = topicState()
    s = applyRemoteEvent(
      s,
      { type: 'tool_call', task_id: 't-tool-2', tool: 'web_search', input_summary: 'AWS Outposts pricing' },
      TOPIC,
    )
    s = applyRemoteEvent(
      s,
      { type: 'tool_result', task_id: 't-tool-2', tool: 'web_search', summary: '4 results' },
      TOPIC,
    )
    expect(s.toolCalls['t-tool-2'].resultSummary).toBe('4 results')
    expect(s.toolCalls['t-tool-2'].resolvedAt).toBeDefined()
  })

  test('tool_result without prior tool_call creates synthetic resolved entry', () => {
    const s0 = topicState()
    const s1 = applyRemoteEvent(
      s0,
      { type: 'tool_result', task_id: 't-tool-3', tool: 'grep_repo', summary: '12 matches' },
      TOPIC,
    )
    expect(s1.toolCalls['t-tool-3'].tool).toBe('grep_repo')
    expect(s1.toolCalls['t-tool-3'].resultSummary).toBe('12 matches')
    expect(s1.toolCalls['t-tool-3'].resolvedAt).toBeDefined()
  })

  test('reconnectBackoffMs gives exponential backoff capped at 30s', () => {
    expect(reconnectBackoffMs(1)).toBe(1_000)
    expect(reconnectBackoffMs(2)).toBe(2_000)
    expect(reconnectBackoffMs(3)).toBe(4_000)
    expect(reconnectBackoffMs(4)).toBe(8_000)
    expect(reconnectBackoffMs(5)).toBe(16_000)
    expect(reconnectBackoffMs(6)).toBe(30_000)
    expect(reconnectBackoffMs(100)).toBe(30_000) // capped
    expect(reconnectBackoffMs(0)).toBe(1_000) // clamped
  })

  test('unknown event types are passthrough (no state mutation)', () => {
    const s0 = topicState()
    const s1 = applyRemoteEvent(
      s0,
      { type: 'some_future_event', task_id: 't-x' },
      TOPIC,
    )
    expect(s1).toBe(s0)
  })

  test('full sequence: classification → 2 engagements streaming in parallel → run_done', () => {
    let s = topicState()
    s = applyRemoteEvent(
      s,
      {
        type: 'classification',
        archetypes: ['strategic_intelligence', 'risk_intelligence'],
        depth: 2,
      },
      TOPIC,
    )
    s = applyRemoteEvent(
      s,
      { type: 'engagement_start', task_id: 't-strat', archetypes: ['strategic_intelligence'] },
      TOPIC,
    )
    s = applyRemoteEvent(
      s,
      { type: 'engagement_start', task_id: 't-risk', archetypes: ['risk_intelligence'] },
      TOPIC,
    )
    // Interleave tokens between two tracks
    s = applyRemoteEvent(s, { type: 'token', task_id: 't-strat', content: 'AI-' }, TOPIC)
    s = applyRemoteEvent(s, { type: 'token', task_id: 't-risk', content: 'CIO ' }, TOPIC)
    s = applyRemoteEvent(s, { type: 'token', task_id: 't-strat', content: 'first.' }, TOPIC)
    s = applyRemoteEvent(s, { type: 'token', task_id: 't-risk', content: 'drift exposure.' }, TOPIC)
    s = applyRemoteEvent(s, { type: 'engagement_done', task_id: 't-strat' }, TOPIC)
    s = applyRemoteEvent(s, { type: 'engagement_done', task_id: 't-risk' }, TOPIC)
    s = applyRemoteEvent(s, { type: 'run_done', duration_ms: 8100 }, TOPIC)

    const stage = s.journey?.stages[0]
    expect(stage?.status).toBe('past')
    expect(stage?.tracks).toHaveLength(2)
    expect(stage?.tracks[0].contribution).toBe('AI-first.')
    expect(stage?.tracks[1].contribution).toBe('CIO drift exposure.')
    expect(stage?.tracks.every((t) => t.inFlight === false)).toBe(true)
  })
})

function withJourney() {
  return applyRemoteEvent(freshInitialState(), { type: 'run_start', run_id: 'r1' } as any, 'topic')
}

describe('phase markers (block_start/block_done)', () => {
  test('first block_start replaces the placeholder with a single current stage', () => {
    const s = applyRemoteEvent(withJourney(), { type: 'block_start', block_name: 'classify' } as any, 'topic')
    expect(s.journey!.stages).toHaveLength(1)
    expect(s.journey!.stages[0].title).toBe('Framing')
    expect(s.journey!.stages[0].phase).toBe('frame')
    expect(s.journey!.stages[0].status).toBe('current')
  })

  test('subsequent block_start marks prior stages past and adds a current one', () => {
    let s = withJourney()
    s = applyRemoteEvent(s, { type: 'block_start', block_name: 'classify' } as any, 'topic')
    s = applyRemoteEvent(s, { type: 'block_start', block_name: 'compose' } as any, 'topic')
    s = applyRemoteEvent(s, { type: 'block_start', block_name: 'engage' } as any, 'topic')
    const stages = s.journey!.stages
    expect(stages.map((x) => x.title)).toEqual(['Framing', 'Assembling the committee', 'Deliberating'])
    expect(stages.map((x) => x.status)).toEqual(['past', 'past', 'current'])
  })

  test('engagement tracks attach to the current (Deliberating) stage', () => {
    let s = withJourney()
    s = applyRemoteEvent(s, { type: 'block_start', block_name: 'classify' } as any, 'topic')
    s = applyRemoteEvent(s, { type: 'block_start', block_name: 'engage' } as any, 'topic')
    s = applyRemoteEvent(
      s,
      { type: 'engagement_start', task_id: 't1', archetypes: ['creative_intelligence'], pattern: 'analyst' } as any,
      'topic',
    )
    const current = s.journey!.stages.find((x) => x.status === 'current')!
    expect(current.title).toBe('Deliberating')
    expect(current.tracks).toHaveLength(1)
    expect(current.tracks[0].metaSkill).toBe('creative_intelligence')
  })

  test('run_done marks every stage past', () => {
    let s = withJourney()
    s = applyRemoteEvent(s, { type: 'block_start', block_name: 'classify' } as any, 'topic')
    s = applyRemoteEvent(s, { type: 'block_start', block_name: 'engage' } as any, 'topic')
    s = applyRemoteEvent(s, { type: 'run_done', duration_ms: 10 } as any, 'topic')
    expect(s.journey!.stages.every((x) => x.status === 'past')).toBe(true)
  })

  test('run_error also freezes all stages to past', () => {
    let s = withJourney()
    s = applyRemoteEvent(s, { type: 'block_start', block_name: 'classify' } as any, 'topic')
    s = applyRemoteEvent(s, { type: 'block_start', block_name: 'engage' } as any, 'topic')
    s = applyRemoteEvent(s, { type: 'run_error', error: 'timeout' } as any, 'topic')
    expect(s.journey!.stages.every((x) => x.status === 'past')).toBe(true)
  })

  test('unknown block_name still creates a stage titled by the raw name', () => {
    const s = applyRemoteEvent(withJourney(), { type: 'block_start', block_name: 'mystery' } as any, 'topic')
    expect(s.journey!.stages[0].title).toBe('mystery')
    expect(s.journey!.stages[0].phase).toBe('choose')
  })
})

describe('live token accumulation in the post-block stage (M2)', () => {
  test('streamed token deltas accumulate into the current (Deliberating) stage track', () => {
    let s = topicState()
    s = applyRemoteEvent(s, { type: 'block_start', block_name: 'engage' } as any, TOPIC)
    s = applyRemoteEvent(
      s,
      { type: 'engagement_start', task_id: 'canvas-perspective-0', archetypes: ['analyst'] } as any,
      TOPIC,
    )
    s = applyRemoteEvent(s, { type: 'token', task_id: 'canvas-perspective-0', content: 'Hello ' } as any, TOPIC)
    s = applyRemoteEvent(s, { type: 'token', task_id: 'canvas-perspective-0', content: 'world' } as any, TOPIC)

    const current = s.journey!.stages.find((x) => x.status === 'current')!
    expect(current.title).toBe('Deliberating')
    const track = current.tracks.find(
      (t) => (t as { _taskId?: string })._taskId === 'canvas-perspective-0',
    )!
    expect(track).toBeDefined()
    expect(track.contribution).toBe('Hello world')
  })
})

describe('seq de-dupe (M3 resume)', () => {
  test('an event with seq <= lastSeq is ignored (idempotent replay)', () => {
    let s = topicState()
    s = applyRemoteEvent(s, { type: 'block_start', block_name: 'engage', seq: 3 } as any, TOPIC)
    s = applyRemoteEvent(
      s,
      { type: 'engagement_start', task_id: 'canvas-perspective-0', archetypes: ['analyst'], seq: 4 } as any,
      TOPIC,
    )
    s = applyRemoteEvent(s, { type: 'token', task_id: 'canvas-perspective-0', content: 'Hi', seq: 5 } as any, TOPIC)
    const afterFirst = s
    // Replay re-sends seq 5 (already applied) → must be ignored, not double-appended.
    s = applyRemoteEvent(s, { type: 'token', task_id: 'canvas-perspective-0', content: 'Hi', seq: 5 } as any, TOPIC)
    const track = s.journey!.stages
      .find((x) => x.status === 'current')!
      .tracks.find((t) => (t as { _taskId?: string })._taskId === 'canvas-perspective-0')!
    expect(track.contribution).toBe('Hi') // not 'HiHi'
    expect(s.lastSeq).toBe(5)
    expect(s).toEqual(afterFirst) // no-op
  })

  test('a new higher-seq event is applied and advances lastSeq', () => {
    let s = topicState()
    s = applyRemoteEvent(s, { type: 'block_start', block_name: 'engage', seq: 3 } as any, TOPIC)
    s = applyRemoteEvent(
      s,
      { type: 'engagement_start', task_id: 'canvas-perspective-0', archetypes: ['analyst'], seq: 4 } as any,
      TOPIC,
    )
    s = applyRemoteEvent(s, { type: 'token', task_id: 'canvas-perspective-0', content: 'Hi', seq: 5 } as any, TOPIC)
    s = applyRemoteEvent(s, { type: 'token', task_id: 'canvas-perspective-0', content: ' there', seq: 6 } as any, TOPIC)
    const track = s.journey!.stages
      .find((x) => x.status === 'current')!
      .tracks.find((t) => (t as { _taskId?: string })._taskId === 'canvas-perspective-0')!
    expect(track.contribution).toBe('Hi there')
    expect(s.lastSeq).toBe(6)
  })
})
