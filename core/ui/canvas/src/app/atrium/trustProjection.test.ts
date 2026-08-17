import { describe, expect, it } from 'vitest'

import type {
  IntelligenceResourceKind,
  IntelligenceResourcePage,
  IntelligenceResourceRecord,
} from '@/api/intelligenceResourcesApi'

import {
  canonicalPayloadObject,
  challengeProjectionForRecord,
  domainHealthProjection,
  exactLineageClosure,
  intelligenceViewState,
  whyProjectionForRecord,
} from './trustProjection'

const loadedAt = '2026-08-14T18:00:00.000Z'

function record(
  kind: IntelligenceResourceKind,
  id: string,
  options: {
    readonly title?: string
    readonly summary?: string | null
    readonly payload?: unknown
    readonly provenance?: IntelligenceResourceRecord['provenance']
    readonly subjectRefs?: string[]
    readonly availability?: IntelligenceResourceRecord['availability']
    readonly supersedes?: IntelligenceResourceRecord['supersedes']
    readonly revision?: number
  } = {},
): IntelligenceResourceRecord {
  return {
    contract: 'ace.intelligence.resource-plane-record/v1alpha1',
    reference: {
      contract: 'ace.intelligence.resource-plane-reference/v1alpha1',
      product_id: 'product:world-intelligence',
      resource_kind: kind,
      resource_id: `${kind}:${id}`,
      resource_digest: `sha256:${`${id}-${options.revision ?? 1}`.padEnd(64, 'a').slice(0, 64)}`,
      resource_contract: `ace.test.${kind}/v1`,
      revision: options.revision ?? 1,
      as_of: loadedAt,
      available_at: loadedAt,
    },
    availability: options.availability ?? 'available',
    title: options.title ?? `${kind} ${id}`,
    summary: options.summary ?? null,
    subject_refs: options.subjectRefs ?? [],
    provenance: options.provenance ?? [],
    supersedes: options.supersedes ?? null,
    payload: options.payload ?? {},
    degraded_reason_refs: options.availability === 'degraded' ? ['degraded_reason:test'] : [],
  }
}

function page(
  items: IntelligenceResourceRecord[],
  options: {
    readonly state?: IntelligenceResourcePage['state']
    readonly reasons?: string[]
    readonly evaluatedAt?: string
  } = {},
): IntelligenceResourcePage {
  return {
    contract: 'ace.intelligence.resource-plane-page/v1alpha1',
    query_id: 'resource_query:test',
    query_digest: `sha256:${'b'.repeat(64)}`,
    product_id: 'product:world-intelligence',
    actor_ref: 'principal:test',
    as_of: loadedAt,
    available_at: loadedAt,
    evaluated_at: options.evaluatedAt ?? loadedAt,
    state: options.state ?? 'complete',
    items,
    next_cursor: null,
    degraded_reason_refs: options.reasons ?? [],
    page_id: 'resource_page:test',
    page_digest: `sha256:${'c'.repeat(64)}`,
  }
}

describe('trust projection contract boundaries', () => {
  it('decodes the canonical JSON wrapper without inventing malformed material', () => {
    expect(canonicalPayloadObject({ value_json: JSON.stringify({ confidence: 0.91 }) })).toEqual({ confidence: 0.91 })
    expect(canonicalPayloadObject({ value_json: '{not json' })).toEqual({ value_json: '{not json' })
    expect(canonicalPayloadObject(null)).toBeNull()
  })

  it('reports all eight Domain Health dimensions without turning presentation counts into quality', () => {
    const items = [
      record('source', 'official-records'),
      record('connection', 'public-web'),
      record('entity', 'market'),
      record('agent', 'analyst'),
      record('monitor', 'watch'),
      record('signal', 'movement', {
        payload: { value_json: JSON.stringify({ confidence: 0.91 }) },
      }),
    ]
    const projection = domainHealthProjection(page(items), items)

    expect(projection.dimensions.map((item) => item.label)).toEqual([
      'Coverage',
      'Freshness',
      'Confidence',
      'Conflicts',
      'Resolution',
      'Source health',
      'Maintenance health',
      'Historical depth',
    ])
    expect(projection.dimensions.find((item) => item.label === 'Coverage')).toMatchObject({
      value: 'Not measured',
      support: 'not_supported',
    })
    expect(projection.dimensions.find((item) => item.label === 'Confidence')).toMatchObject({
      value: 'Record-level only',
      support: 'observed',
    })
    expect(projection.dimensions.find((item) => item.label === 'Resolution')).toMatchObject({
      value: 'Snapshot state only',
      support: 'observed',
    })
    expect(projection.dimensions.find((item) => item.label === 'Maintenance health')).toMatchObject({
      value: 'Lifecycle state only',
    })
  })

  it('keeps recorded-source readiness, freshness, and aggregate source health distinct', () => {
    const readiness = record('source_health', 'official-records', {
      payload: {
        value_json: JSON.stringify({
          health_basis: 'recorded_admission',
          readiness_state: 'ready',
          last_success_at: '2026-08-14T17:45:00.000Z',
          freshness: 'unverified',
          freshness_verified: false,
        }),
      },
    })
    const projection = domainHealthProjection(page([readiness]), [readiness])

    expect(projection.dimensions.find((item) => item.label === 'Source health')).toMatchObject({
      value: 'Readiness recorded',
      support: 'observed',
    })
    expect(projection.dimensions.find((item) => item.label === 'Freshness')).toMatchObject({
      value: 'Unverified',
      support: 'observed',
    })
    expect(projection.dimensions.find((item) => item.label === 'Freshness')?.detail).toContain(
      'last recorded source admission succeeded',
    )

    const degraded = { ...readiness, availability: 'degraded' as const }
    const degradedProjection = domainHealthProjection(page([degraded], { state: 'degraded' }), [degraded])
    expect(degradedProjection.dimensions.find((item) => item.label === 'Source health')).toMatchObject({
      value: 'Partial readiness records',
      support: 'unavailable',
      attention: true,
    })
  })

  it('marks an unsupported conflict family unavailable and never claims zero conflicts', () => {
    const currentPage = page([], {
      state: 'degraded',
      reasons: ['degraded_reason:unsupported-conflict', 'degraded_reason:unsupported-uncertainty'],
    })
    expect(domainHealthProjection(currentPage, []).dimensions.find((item) => item.label === 'Conflicts')).toMatchObject({
      value: 'Unavailable',
      support: 'unavailable',
    })
  })

  it('does not infer historical depth from unrelated Briefs and limits supersedes to revision lineage', () => {
    const firstTopic = record('brief', 'first-topic')
    const secondTopic = record('brief', 'second-topic')
    const unrelated = domainHealthProjection(page([firstTopic, secondTopic]), [firstTopic, secondTopic])
    expect(unrelated.dimensions.find((item) => item.label === 'Historical depth')).toMatchObject({
      value: 'Not projected',
    })

    const firstRevision = record('source_health', 'feed', { revision: 1 })
    const secondRevision = record('source_health', 'feed', {
      revision: 2,
      supersedes: firstRevision.reference,
    })
    const revisionLineage = domainHealthProjection(
      page([firstRevision, secondRevision]),
      [firstRevision, secondRevision],
    )
    expect(revisionLineage.dimensions.find((item) => item.label === 'Historical depth')).toMatchObject({
      value: 'Revision lineage only',
      support: 'observed',
    })
    expect(revisionLineage.dimensions.find((item) => item.label === 'Historical depth')?.detail).toContain(
      'comparable historical intelligence depth is not contracted',
    )
  })

  it('reports exact maintenance lifecycle state without calling it runtime liveness', () => {
    const active = record('monitor', 'policy-watch', {
      payload: { value_json: JSON.stringify({ state_after: 'active' }) },
    })
    const activeHealth = domainHealthProjection(page([active]), [active])
    expect(activeHealth.dimensions.find((item) => item.label === 'Maintenance health')).toMatchObject({
      value: 'Active lifecycle recorded',
      support: 'observed',
    })
    expect(activeHealth.dimensions.find((item) => item.label === 'Maintenance health')?.detail).toContain(
      'does not establish runtime liveness',
    )

    const paused = record('subscription', 'executive-brief', {
      payload: { value_json: JSON.stringify({ state_after: 'paused' }) },
    })
    const pausedHealth = domainHealthProjection(page([active, paused]), [active, paused])
    expect(pausedHealth.dimensions.find((item) => item.label === 'Maintenance health')).toMatchObject({
      value: 'Lifecycle paused',
      support: 'observed',
      attention: true,
    })
  })
})

describe('reversible Why derivation', () => {
  it('uses only exact revision-and-digest lineage and excludes a signal that merely shares a source', () => {
    const source = record('source', 'official-records')
    const shift = record('shift', 'material-change', {
      title: 'Material change',
      summary: 'The governed baseline changed.',
      subjectRefs: ['entity:market'],
      provenance: [source.reference],
      payload: { value_json: JSON.stringify({ confidence: 0.82 }) },
    })
    const unrelatedSignal = record('signal', 'shared-source-only', {
      title: 'Unrelated signal',
      provenance: [source.reference],
    })
    const derivedSignal = record('signal', 'derived-from-shift', {
      title: 'Exact derived signal',
      provenance: [shift.reference],
    })

    const items = [source, unrelatedSignal, shift, derivedSignal]
    const projection = whyProjectionForRecord(shift, items, page(items))

    expect(projection.stages.find((item) => item.label === 'Material event')).toMatchObject({
      body: 'Material change',
      support: 'supported',
    })
    expect(projection.stages.find((item) => item.label === 'Signal')).toMatchObject({
      body: 'Exact derived signal',
      support: 'supported',
    })
    expect(projection.stages.find((item) => item.label === 'Signal')?.body).not.toContain('Unrelated signal')
    expect(projection.stages.find((item) => item.label === 'Resolved entities')?.body).toContain(
      'no resolved Entity Snapshot',
    )
    expect(projection.confidence).toEqual({ value: '82%', support: 'measured' })
  })

  it('surfaces missing exact evidence instead of matching a different digest', () => {
    const loadedSource = record('source', 'official-records')
    const wrongDigest = {
      ...loadedSource.reference,
      resource_digest: `sha256:${'f'.repeat(64)}`,
    }
    const brief = record('brief', 'current', { provenance: [wrongDigest] })

    const closure = exactLineageClosure(brief, [loadedSource, brief])
    expect(closure.loaded).toEqual([])
    expect(closure.missing).toEqual([wrongDigest])

    const projection = whyProjectionForRecord(brief, [loadedSource, brief], page([loadedSource, brief]))
    expect(projection.supportingEvidence).toContainEqual(expect.objectContaining({
      availability: 'not_loaded',
      kind: 'source',
    }))
  })

  it('separates explicit conflicting evidence and keeps conflict absence unknown', () => {
    const source = record('source', 'official-records')
    const shift = record('shift', 'material-change', { provenance: [source.reference] })
    const conflict = record('conflict', 'disagreement', {
      title: 'Sources disagree about the effective date',
      provenance: [shift.reference],
    })
    const withConflict = whyProjectionForRecord(shift, [source, shift, conflict], page([source, shift, conflict]))
    expect(withConflict.conflictingEvidence).toEqual([
      expect.objectContaining({ title: 'Sources disagree about the effective date', kind: 'conflict' }),
    ])
    expect(withConflict.unknowns.some((item) => item.includes('not evidence that no conflict exists'))).toBe(false)

    const withoutConflict = whyProjectionForRecord(shift, [source, shift], page([source, shift]))
    expect(withoutConflict.conflictingEvidence).toEqual([])
    expect(withoutConflict.unknowns).toContain(
      'No exact conflict record is loaded; this is not evidence that no conflict exists.',
    )
    expect(withoutConflict.recalculation).toContain('does not establish that recalculation has not occurred')
  })

  it('uses exact supersession for recalculation state and keeps broader effect unknown', () => {
    const first = record('brief', 'current', { revision: 1 })
    const second = record('brief', 'current', {
      revision: 2,
      supersedes: first.reference,
    })

    const projection = whyProjectionForRecord(first, [first, second], page([first, second]))
    expect(projection.recalculation).toContain('Exact revision 2 supersedes this record')
    expect(projection.recalculation).toContain('broader maintenance effect is not projected')
  })

  it('surfaces exact Feedback proposals but does not invent arbitrary correction authority', () => {
    const shift = record('shift', 'material-change')
    const feedback = record('feedback', 'challenge', {
      title: 'Feedback proposal: source weighting',
      provenance: [shift.reference],
    })

    const challenge = challengeProjectionForRecord(shift, [shift, feedback])
    expect(challenge.reasons).toEqual([
      'This claim is outdated',
      'The entity mapping is wrong',
      'ACE missed a source',
      'A source is over-weighted',
    ])
    expect(challenge.existingProposals).toEqual([
      expect.objectContaining({ title: 'Feedback proposal: source weighting', kind: 'feedback' }),
    ])
    expect(challenge.submission).toMatchObject({
      available: true,
      reason: expect.stringContaining('exact revision'),
    })
    expect(challenge.futureEffect).toContain('does not claim that it changed authority')
  })
})

describe('load, stale, unavailable, and recovery semantics', () => {
  const loadedPage = page([record('brief', 'current')])

  it('distinguishes initial loading, unavailable, empty, degraded, and retained last-loaded pictures', () => {
    expect(intelligenceViewState(null, true, null)).toBe('loading_initial')
    expect(intelligenceViewState(null, false, new Error('unavailable'))).toBe('unavailable')
    expect(intelligenceViewState(page([]), false, null)).toBe('empty')
    expect(intelligenceViewState(page([], { state: 'degraded' }), false, null)).toBe('degraded')
    expect(intelligenceViewState(loadedPage, true, null)).toBe('refreshing')
    expect(intelligenceViewState(loadedPage, false, new Error('refresh failed'))).toBe('last_loaded')
    expect(intelligenceViewState(loadedPage, false, null)).toBe('loaded')
  })
})
