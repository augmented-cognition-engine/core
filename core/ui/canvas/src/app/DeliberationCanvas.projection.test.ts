// Pure tests for projectJourneyToCommittee — the live-session → committee-surface mapping. Validates the
// projection without a socket (the surface's demo fallback is exercised by rendering; this pins the wire).
import { describe, expect, test } from 'vitest'

import type { DeliberationJourneyState } from '@/types/canvas'
import { projectJourneyToCommittee } from './DeliberationCanvas'

function liveState(): DeliberationJourneyState {
  return {
    topic: 'Should the homepage hero pivot to outcomes-first for the Q3 launch?',
    classification: {
      discipline: 'positioning',
      taskType: 'decide',
      mode: 'deliberative',
      archetype: 'analyst',
      complexity: 'high',
      depth: 3,
      fusionMode: false,
      metaSkills: [],
    },
    stages: [
      {
        id: 's1', phase: 'frame', glyph: '◯', title: 'Frame', status: 'past', tracks: [],
        synthesis: { implication: 'Anchored on the economic buyer.' },
      },
      {
        id: 's2', phase: 'choose', glyph: '◇', title: 'Converge', status: 'current',
        tracks: [
          { metaSkill: 'creative_intelligence', label: 'creative', contribution: 'Lead with the operating-model question.', inFlight: true },
          { metaSkill: 'risk_intelligence', label: 'risk', contribution: 'The proof point must be the stack diagram.', instrument: 'red_team' },
        ],
      },
    ],
    priorDecisions: [{ id: 'd1', title: 'Vetoed the unhedged pricing line.', rationale: 'CFO seat' }],
  }
}

describe('projectJourneyToCommittee', () => {
  test('scenario comes from the topic + classification', () => {
    const v = projectJourneyToCommittee(liveState())
    expect(v.scenario.question).toBe(liveState().topic)
    expect(v.scenario.classification).toEqual(['positioning', 'analyst', 'deliberative · depth 3'])
  })

  test('the committee is the meta-skill tracks at the latest stage that has any', () => {
    const v = projectJourneyToCommittee(liveState())
    expect(v.agents.map((a) => a.slot)).toEqual(['creative_intelligence', 'risk_intelligence'])
    expect(v.agents[0]!.name).toBe('creative')
    expect(v.agents[0]!.speaking).toBe(true) // inFlight track
    expect(v.agents[1]!.role).toBe('red_team') // instrument
    expect(v.agents[1]!.speaking).toBe(false)
  })

  test('stages map through with status, summary, and per-stage contributions', () => {
    const v = projectJourneyToCommittee(liveState())
    expect(v.stages).toHaveLength(2)
    expect(v.stages[0]!.status).toBe('past')
    expect(v.stages[0]!.summary).toBe('Anchored on the economic buyer.')
    expect(v.stages[0]!.contributions).toEqual([]) // no tracks -> no contributions
    expect(v.stages[1]!.contributions).toHaveLength(2)
    expect(v.stages[1]!.contributions![0]!.text).toContain('operating-model')
    expect(v.stages[1]!.contributions![0]!.agent.name).toBe('creative')
  })

  test('pins come from priorDecisions', () => {
    const v = projectJourneyToCommittee(liveState())
    expect(v.pins).toEqual([
      { id: 'd1', kind: 'decision', text: 'Vetoed the unhedged pricing line.', meta: 'CFO seat' },
    ])
  })

  test('long topics are truncated in the label but kept whole in the question', () => {
    const s = liveState()
    const long = 'x'.repeat(200)
    const v = projectJourneyToCommittee({ ...s, topic: long })
    expect(v.scenario.label.endsWith('…')).toBe(true)
    expect(v.scenario.label.length).toBeLessThan(long.length)
    expect(v.scenario.question).toBe(long)
  })
})
