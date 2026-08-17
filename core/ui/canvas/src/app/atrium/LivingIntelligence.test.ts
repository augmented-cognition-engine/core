import { describe, expect, it } from 'vitest'

import type {
  IntelligenceResourceKind,
  IntelligenceResourcePage,
  IntelligenceResourceRecord,
} from '@/api/intelligenceResourcesApi'

import { domainHealthFromResources, domainHealthGroupLabels, whyStepsForRecord } from './LivingIntelligence'

const availableAt = '2026-08-14T18:00:00.000Z'

function record(
  kind: IntelligenceResourceKind,
  id: string,
  title: string,
  options: {
    readonly summary?: string
    readonly payload?: unknown
    readonly provenance?: IntelligenceResourceRecord['provenance']
    readonly subjectRefs?: string[]
    readonly availability?: IntelligenceResourceRecord['availability']
    readonly supersedes?: IntelligenceResourceRecord['supersedes']
  } = {},
): IntelligenceResourceRecord {
  return {
    contract: 'ace.intelligence.resource-plane-record/v1alpha1',
    reference: {
      contract: 'ace.intelligence.resource-plane-reference/v1alpha1',
      product_id: 'product:world-ai-command-center',
      resource_kind: kind,
      resource_id: `${kind}:${id}`,
      resource_digest: `sha256:${id.padEnd(64, 'a').slice(0, 64)}`,
      resource_contract: `ace.test.${kind}/v1`,
      revision: 1,
      as_of: availableAt,
      available_at: availableAt,
    },
    availability: options.availability ?? 'available',
    title,
    summary: options.summary ?? null,
    subject_refs: options.subjectRefs ?? [],
    provenance: options.provenance ?? [],
    supersedes: options.supersedes ?? null,
    payload: options.payload ?? {},
    degraded_reason_refs: [],
  }
}

function page(items: IntelligenceResourceRecord[]): IntelligenceResourcePage {
  return {
    contract: 'ace.intelligence.resource-plane-page/v1alpha1',
    query_id: 'resource_query:test',
    query_digest: `sha256:${'b'.repeat(64)}`,
    product_id: 'product:world-ai-command-center',
    actor_ref: 'principal:test',
    as_of: availableAt,
    available_at: availableAt,
    evaluated_at: availableAt,
    state: 'complete',
    items,
    next_cursor: null,
    degraded_reason_refs: [],
    page_id: 'resource_page:test',
    page_digest: `sha256:${'c'.repeat(64)}`,
  }
}

describe('Living Intelligence projections', () => {
  it('reports all eight Domain Health dimensions without fabricating quality scores', () => {
    const source = record('source', 'official-releases', 'Official release records')
    const items = [
      source,
      record('connection', 'public-web', 'Public web connection'),
      record('agent', 'analyst', 'Intelligence Analyst'),
      record('brief', 'current', 'Current Brief', { provenance: [source.reference] }),
      record('shift', 'invalid-confidence', 'Malformed confidence record', { payload: { confidence: 9 } }),
    ]

    const health = domainHealthFromResources(page(items), items)

    expect(health.map((item) => item.label)).toEqual([
      'Coverage',
      'Freshness',
      'Confidence',
      'Conflicts',
      'Resolution',
      'Source health',
      'Maintenance health',
      'Historical depth',
    ])
    expect(health.find((item) => item.label === 'Confidence')?.value).toBe('Not projected')
    expect(health.find((item) => item.label === 'Confidence')?.detail).toBe(
      'No domain-wide confidence contract is projected.',
    )
    expect(health.find((item) => item.label === 'Conflicts')).toMatchObject({
      value: 'Not evidenced',
      detail: 'No conflict record is loaded; absence from this page does not establish zero conflicts.',
    })
    expect(health.find((item) => item.label === 'Source health')).toMatchObject({
      value: 'Not projected',
    })
  })

  it('does not turn health-record presence or multiple Briefs into unsupported health and history claims', () => {
    const firstBrief = record('brief', 'first-topic', 'First topic Brief')
    const secondBrief = record('brief', 'second-topic', 'Second topic Brief')
    const healthRecord = record('source_health', 'feed-health', 'Feed health record')
    const items = [
      firstBrief,
      secondBrief,
      healthRecord,
      record('monitor', 'watch', 'Policy watch', {
        payload: { value_json: JSON.stringify({ state_after: 'active' }) },
      }),
    ]

    const health = domainHealthFromResources(page(items), items)

    expect(health.find((item) => item.label === 'Source health')).toMatchObject({
      value: 'Readiness recorded',
      literalStatus: undefined,
    })
    expect(health.find((item) => item.label === 'Maintenance health')).toMatchObject({
      value: 'Active lifecycle recorded',
    })
    expect(health.find((item) => item.label === 'Historical depth')).toMatchObject({
      value: 'Not projected',
    })

    healthRecord.availability = 'degraded'
    const degradedHealth = domainHealthFromResources(page(items), items)
    expect(degradedHealth.find((item) => item.label === 'Source health')).toMatchObject({
      value: 'Partial readiness records',
      literalStatus: 'warning',
    })
  })

  it('groups all eight dimensions without dropping or duplicating any of them', () => {
    const source = record('source', 'official-releases', 'Official release records')
    const items = [
      source,
      record('brief', 'current', 'Current Brief', { provenance: [source.reference] }),
    ]

    const groups = domainHealthGroupLabels(page(items), items)
    const allLabels = [...groups.attention, ...groups.supported, ...groups.notMeasured]

    expect(groups.attention).toEqual([])
    expect(new Set(allLabels).size).toBe(8)
    expect(allLabels.sort()).toEqual([
      'Confidence',
      'Conflicts',
      'Coverage',
      'Freshness',
      'Historical depth',
      'Maintenance health',
      'Resolution',
      'Source health',
    ])
  })

  it('foregrounds literal-attention dimensions ahead of supported and not-currently-measured ones', () => {
    const source = record('source', 'official-releases', 'Official release records')
    const conflict = record('conflict', 'pricing-vs-support', 'Pricing narrative disagreement')
    const healthRecord = record('source_health', 'feed-health', 'Feed health record', {
      availability: 'degraded',
    })
    const items = [source, conflict, healthRecord]

    const groups = domainHealthGroupLabels(page(items), items)

    // A degraded source_health record flips both Freshness and Source health
    // into attention, alongside the admitted Conflict — in canonical dimension order.
    expect(groups.attention).toEqual(['Freshness', 'Conflicts', 'Source health'])
    expect(groups.supported).not.toContain('Freshness')
    expect(groups.supported).not.toContain('Conflicts')
    expect(groups.supported).not.toContain('Source health')
    expect(groups.notMeasured).not.toContain('Freshness')
    expect(groups.notMeasured).not.toContain('Conflicts')
    expect(groups.notMeasured).not.toContain('Source health')

    const allLabels = [...groups.attention, ...groups.supported, ...groups.notMeasured]
    expect(new Set(allLabels).size).toBe(8)
  })

  it('builds a plain-language Why derivation from admitted relationships and keeps gaps explicit', () => {
    const source = record('source', 'official-releases', 'Official release records')
    const signal = record('signal', 'pricing', 'Provider pricing signal', {
      summary: 'Provider price changes entered the watch window.',
      provenance: [source.reference],
    })
    const shift = record('shift', 'economics', 'Inference economics changed', {
      subjectRefs: ['entity:model-economics'],
      provenance: [source.reference],
      payload: {
        what_changed: 'Published inference prices fell.',
        why_it_matters: 'Build-versus-buy assumptions changed.',
      },
    })

    const steps = whyStepsForRecord(shift, [source, signal, shift])

    expect(steps.map((step) => step.label)).toEqual([
      'Observation',
      'Resolved entities',
      'Material event',
      'Signal',
      'Assessment',
    ])
    expect(steps.find((step) => step.label === 'Signal')?.body).toBe(
      'No exact Signal is in the loaded lineage.',
    )
    expect(steps.find((step) => step.label === 'Assessment')?.body).toBe(
      'Build-versus-buy assumptions changed.',
    )
  })
})
