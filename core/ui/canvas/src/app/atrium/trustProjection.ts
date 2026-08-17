import type {
  IntelligenceResourceKind,
  IntelligenceResourcePage,
  IntelligenceResourceRecord,
  IntelligenceResourceReference,
} from '@/api/intelligenceResourcesApi'

export type TrustSupport =
  | 'measured'
  | 'derived'
  | 'observed'
  | 'not_supported'
  | 'unavailable'

export interface DomainHealthDimension {
  readonly label: string
  readonly value: string
  readonly detail: string
  readonly support: TrustSupport
  readonly attention?: boolean
}

export interface DomainHealthProjection {
  readonly dimensions: readonly DomainHealthDimension[]
  readonly pageState: 'not_loaded' | 'loaded' | 'degraded'
  readonly lastLoadedAt: string | null
  readonly limitations: readonly string[]
}

export interface WhyStage {
  readonly label: 'Observation' | 'Resolved entities' | 'Material event' | 'Signal' | 'Assessment'
  readonly body: string
  readonly support: 'supported' | 'degraded' | 'unknown' | 'unavailable'
}

export interface WhyEvidenceItem {
  readonly title: string
  readonly kind: IntelligenceResourceKind
  readonly availability: IntelligenceResourceRecord['availability'] | 'not_loaded'
  readonly availableAt: string
}

export interface WhyProjection {
  readonly stages: readonly WhyStage[]
  readonly supportingEvidence: readonly WhyEvidenceItem[]
  readonly conflictingEvidence: readonly WhyEvidenceItem[]
  readonly unknowns: readonly string[]
  readonly confidence: {
    readonly value: string
    readonly support: TrustSupport
  }
  readonly recordAvailableAt: string
  readonly lastLoadedAt: string | null
  readonly recalculation: string
  readonly operatorBoundary: string
}

export type ConclusionChallengeReason =
  | 'This claim is outdated'
  | 'The entity mapping is wrong'
  | 'ACE missed a source'
  | 'A source is over-weighted'

export interface ConclusionChallengeProjection {
  readonly reasons: readonly ConclusionChallengeReason[]
  readonly existingProposals: readonly WhyEvidenceItem[]
  readonly submission: {
    readonly available: true
    readonly reason: string
  }
  readonly futureEffect: string
}

export type IntelligenceViewState =
  | 'loading_initial'
  | 'unavailable'
  | 'empty'
  | 'refreshing'
  | 'last_loaded'
  | 'degraded'
  | 'loaded'

function objectValue(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

/** Decode the canonical-json wrapper used by the public resource plane. */
export function canonicalPayloadObject(payload: unknown): Record<string, unknown> | null {
  const root = objectValue(payload)
  if (root === null) return null
  const encoded = root.value_json
  if (typeof encoded !== 'string') return root
  try {
    return objectValue(JSON.parse(encoded)) ?? root
  } catch {
    return root
  }
}

function payloadText(payload: unknown, key: string): string | null {
  const value = canonicalPayloadObject(payload)?.[key]
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null
}

function payloadBoolean(payload: unknown, key: string): boolean | null {
  const value = canonicalPayloadObject(payload)?.[key]
  return typeof value === 'boolean' ? value : null
}

function confidenceOf(record: IntelligenceResourceRecord): number | null {
  const value = canonicalPayloadObject(record.payload)?.confidence
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
    ? value
    : null
}

function referenceKey(reference: IntelligenceResourceReference): string {
  return [
    reference.product_id,
    reference.resource_kind,
    reference.resource_id,
    reference.revision,
    reference.resource_digest,
  ].join('|')
}

function visibleRecords(items: readonly IntelligenceResourceRecord[]): IntelligenceResourceRecord[] {
  return items.filter((item) => item.availability !== 'tombstoned')
}

interface LineageClosure {
  readonly loaded: readonly IntelligenceResourceRecord[]
  readonly missing: readonly IntelligenceResourceReference[]
}

/** Follow only exact product/kind/id/revision/digest edges admitted by the contract. */
export function exactLineageClosure(
  record: IntelligenceResourceRecord,
  items: readonly IntelligenceResourceRecord[],
): LineageClosure {
  const byReference = new Map(
    visibleRecords(items).map((item) => [referenceKey(item.reference), item]),
  )
  const loaded: IntelligenceResourceRecord[] = []
  const missing: IntelligenceResourceReference[] = []
  const visited = new Set<string>()
  const queue = [...record.provenance]

  while (queue.length > 0 && visited.size < 1_024) {
    const reference = queue.shift()
    if (reference === undefined) break
    const key = referenceKey(reference)
    if (visited.has(key)) continue
    visited.add(key)
    const upstream = byReference.get(key)
    if (upstream === undefined) {
      missing.push(reference)
      continue
    }
    loaded.push(upstream)
    queue.push(...upstream.provenance)
  }

  return { loaded, missing }
}

function recordsOfKind(
  items: readonly IntelligenceResourceRecord[],
  kind: IntelligenceResourceKind,
): IntelligenceResourceRecord[] {
  return items.filter((item) => item.reference.resource_kind === kind)
}

function unsupported(page: IntelligenceResourcePage | null, kind: IntelligenceResourceKind): boolean {
  return page?.degraded_reason_refs.some((reason) =>
    reason === `degraded_reason:unsupported-${kind}`,
  ) ?? false
}

function loadedTitles(items: readonly IntelligenceResourceRecord[]): string {
  const titles = items.slice(0, 3).map((item) => item.title)
  if (items.length > 3) titles.push(`${items.length - 3} more`)
  return titles.join(' · ')
}

function stage(
  label: WhyStage['label'],
  items: readonly IntelligenceResourceRecord[],
  missing: readonly IntelligenceResourceReference[],
  empty: string,
): WhyStage {
  if (items.length > 0) {
    return {
      label,
      body: loadedTitles(items),
      support: items.some((item) => item.availability === 'degraded') ? 'degraded' : 'supported',
    }
  }
  if (missing.length > 0) {
    return {
      label,
      body: `${missing.length} exact ${label.toLocaleLowerCase()} reference${missing.length === 1 ? '' : 's'} not loaded.`,
      support: 'unavailable',
    }
  }
  return { label, body: empty, support: 'unknown' }
}

function evidenceItem(record: IntelligenceResourceRecord): WhyEvidenceItem {
  return {
    title: record.title,
    kind: record.reference.resource_kind,
    availability: record.availability,
    availableAt: record.reference.available_at,
  }
}

function missingEvidenceItem(reference: IntelligenceResourceReference): WhyEvidenceItem {
  return {
    title: `${reference.resource_kind.replace(/_/g, ' ')} evidence not loaded`,
    kind: reference.resource_kind,
    availability: 'not_loaded',
    availableAt: reference.available_at,
  }
}

function exactRelatedRecords(
  record: IntelligenceResourceRecord,
  closure: LineageClosure,
  items: readonly IntelligenceResourceRecord[],
  kind: IntelligenceResourceKind,
): IntelligenceResourceRecord[] {
  const basis = new Set([
    referenceKey(record.reference),
    ...closure.loaded.map((item) => referenceKey(item.reference)),
  ])
  const upstreamSpecial = new Set(
    record.provenance
      .filter((reference) => reference.resource_kind === kind)
      .map(referenceKey),
  )
  return visibleRecords(items).filter((item) =>
    item.reference.resource_kind === kind
    && (
      upstreamSpecial.has(referenceKey(item.reference))
      || item.provenance.some((reference) => basis.has(referenceKey(reference)))
    ),
  )
}

function exactDirectDescendants(
  record: IntelligenceResourceRecord,
  items: readonly IntelligenceResourceRecord[],
  kind: IntelligenceResourceKind,
): IntelligenceResourceRecord[] {
  const target = referenceKey(record.reference)
  return visibleRecords(items).filter((item) =>
    item.reference.resource_kind === kind
    && item.provenance.some((reference) => referenceKey(reference) === target),
  )
}

function exactSupersedingRecord(
  record: IntelligenceResourceRecord,
  items: readonly IntelligenceResourceRecord[],
): IntelligenceResourceRecord | null {
  const key = referenceKey(record.reference)
  return visibleRecords(items).find((item) =>
    item.supersedes !== null && referenceKey(item.supersedes) === key,
  ) ?? null
}

/**
 * Expose the exact, non-effective correction proposal path. Recording feedback
 * never implies a change to authority, trust, ranking, or recalculation.
 */
export function challengeProjectionForRecord(
  record: IntelligenceResourceRecord,
  items: readonly IntelligenceResourceRecord[],
): ConclusionChallengeProjection {
  const closure = exactLineageClosure(record, items)
  const existingProposals = exactRelatedRecords(record, closure, items, 'feedback')
    .map(evidenceItem)

  return {
    reasons: [
      'This claim is outdated',
      'The entity mapping is wrong',
      'ACE missed a source',
      'A source is over-weighted',
    ],
    existingProposals,
    submission: {
      available: true,
      reason: 'ACE can record an attributed proposal against this exact revision. The proposal does not change the record or its downstream effects.',
    },
    futureEffect: existingProposals.length > 0
      ? 'A governed Feedback proposal is visible, but the resource plane does not claim that it changed authority, source trust, resolution, ranking, or recalculation.'
      : 'Recording feedback creates reviewable evidence only. Any future effect requires a separate governed maintenance decision and new material.',
  }
}

export function whyProjectionForRecord(
  record: IntelligenceResourceRecord,
  items: readonly IntelligenceResourceRecord[],
  page: IntelligenceResourcePage | null,
): WhyProjection {
  const closure = exactLineageClosure(record, items)
  const observationRecords = recordsOfKind(closure.loaded, 'observation')
  const entityRecords = recordsOfKind(closure.loaded, 'entity')
  const shiftRecords = recordsOfKind(closure.loaded, 'shift')
  const signalRecords = recordsOfKind(closure.loaded, 'signal')
  const missing = (kind: IntelligenceResourceKind) => closure.missing.filter(
    (reference) => reference.resource_kind === kind,
  )
  const materialRecords = record.reference.resource_kind === 'shift'
    ? [record, ...shiftRecords]
    : shiftRecords
  const signalBasis = record.reference.resource_kind === 'signal'
    ? [record, ...signalRecords]
    : [
        ...signalRecords,
        ...exactDirectDescendants(record, items, 'signal'),
      ]
  const confidence = confidenceOf(record)
  const conflicts = exactRelatedRecords(record, closure, items, 'conflict')
  const uncertainties = exactRelatedRecords(record, closure, items, 'uncertainty')
  const degraded = [record, ...closure.loaded].filter((item) => item.availability === 'degraded')
  const successor = exactSupersedingRecord(record, items)
  const stages: WhyStage[] = [
    stage(
      'Observation',
      observationRecords,
      missing('observation'),
      'No exact Observation is in the loaded lineage.',
    ),
    stage(
      'Resolved entities',
      entityRecords,
      missing('entity'),
      record.subject_refs.length > 0
        ? 'Entity references exist, but no resolved Entity Snapshot is in the loaded lineage.'
        : 'Entity resolution is not projected for this assessment.',
    ),
    stage(
      'Material event',
      materialRecords,
      missing('shift'),
      'A separate material event is not projected by the current resource contract.',
    ),
    stage(
      'Signal',
      signalBasis,
      missing('signal'),
      'No exact Signal is in the loaded lineage.',
    ),
    {
      label: 'Assessment',
      body: payloadText(record.payload, 'why_it_matters') ?? record.summary ?? record.title,
      support: record.availability === 'degraded' ? 'degraded' : 'supported',
    },
  ]

  const unknowns = [
    ...stages
      .filter((item) => item.support === 'unknown' || item.support === 'unavailable')
      .map((item) => `${item.label}: ${item.body}`),
    ...uncertainties.map((item) => item.summary ?? item.title),
    ...degraded.map((item) => `${item.title} is available with stated limits.`),
    ...(conflicts.length === 0
      ? [unsupported(page, 'conflict')
          ? 'Conflict records are unavailable in the current projection.'
          : 'No exact conflict record is loaded; this is not evidence that no conflict exists.']
      : []),
  ]

  return {
    stages,
    supportingEvidence: [
      ...closure.loaded
        .filter((item) => item.reference.resource_kind !== 'conflict' && item.reference.resource_kind !== 'uncertainty')
        .map(evidenceItem),
      ...closure.missing.map(missingEvidenceItem),
    ],
    conflictingEvidence: conflicts.map(evidenceItem),
    unknowns: [...new Set(unknowns)],
    confidence: confidence === null
      ? { value: 'Not projected for this assessment', support: 'not_supported' }
      : { value: `${Math.round(confidence * 100)}%`, support: 'measured' },
    recordAvailableAt: record.reference.available_at,
    lastLoadedAt: page?.evaluated_at ?? null,
    recalculation: successor === null
      ? 'No exact superseding revision is loaded; this does not establish that recalculation has not occurred.'
      : `Exact revision ${successor.reference.revision} supersedes this record and became available at ${successor.reference.available_at}. Its broader maintenance effect is not projected.`,
    operatorBoundary: 'Raw execution details and failure references belong in operator diagnostics, not this business derivation.',
  }
}

function lastSourceSuccess(sourceHealth: readonly IntelligenceResourceRecord[]): string | null {
  const values = sourceHealth
    .map((item) => payloadText(item.payload, 'last_success_at'))
    .filter((value): value is string => value !== null)
    .sort()
  return values.length === 0 ? null : values[values.length - 1] ?? null
}

function hasExactRevisionHistory(items: readonly IntelligenceResourceRecord[]): boolean {
  const keys = new Set(visibleRecords(items).map((item) => referenceKey(item.reference)))
  return visibleRecords(items).some((item) =>
    item.supersedes !== null && keys.has(referenceKey(item.supersedes)),
  )
}

export function domainHealthProjection(
  page: IntelligenceResourcePage | null,
  items: readonly IntelligenceResourceRecord[],
): DomainHealthProjection {
  const visible = visibleRecords(items)
  const sourceHealth = recordsOfKind(visible, 'source_health')
  const conflicts = recordsOfKind(visible, 'conflict')
  const entities = recordsOfKind(visible, 'entity')
  const maintenance = [
    ...recordsOfKind(visible, 'monitor'),
    ...recordsOfKind(visible, 'subscription'),
  ]
  const scoredRecords = visible.filter((item) => confidenceOf(item) !== null)
  const sourceHealthDegraded = sourceHealth.some((item) => item.availability === 'degraded')
  const sourceFreshnessVerified = sourceHealth.some((item) =>
    payloadBoolean(item.payload, 'freshness_verified') === true,
  )
  const sourceFreshness = sourceHealth
    .map((item) => payloadText(item.payload, 'freshness'))
    .filter((value): value is string => value !== null)
  const latestSourceSuccess = lastSourceSuccess(sourceHealth)
  const revisionHistory = hasExactRevisionHistory(visible)
  const maintenanceDegraded = maintenance.some((item) => item.availability === 'degraded')
  const maintenanceStates = maintenance
    .map((item) => payloadText(item.payload, 'state_after'))
    .filter((value): value is string => value !== null)
  const maintenanceFamiliesUnavailable = unsupported(page, 'monitor') || unsupported(page, 'subscription')

  const freshness: DomainHealthDimension = sourceHealth.length === 0
    ? {
        label: 'Freshness',
        value: 'Not measured',
        detail: 'The page load time is not a domain freshness measure; required update cadence is not projected.',
        support: 'not_supported',
      }
    : sourceHealthDegraded
      ? {
          label: 'Freshness',
          value: 'Partially unavailable',
          detail: latestSourceSuccess === null
            ? 'Some source-readiness records are degraded; no domain freshness measure is projected.'
            : `Some source-readiness records are degraded. Last recorded source admission succeeded at ${latestSourceSuccess}.`,
          support: 'unavailable',
          attention: true,
        }
      : sourceFreshnessVerified
        ? {
            label: 'Freshness',
            value: 'Source-level only',
            detail: 'One or more source records report verified freshness; no domain-wide cadence aggregation is contracted.',
            support: 'observed',
          }
        : {
            label: 'Freshness',
            value: sourceFreshness.includes('unverified') ? 'Unverified' : 'Not measured',
            detail: latestSourceSuccess === null
              ? 'Source readiness is recorded, but domain freshness is not verified.'
              : `Source readiness is recorded; the last recorded source admission succeeded at ${latestSourceSuccess}, but freshness is unverified.`,
            support: 'observed',
          }

  const dimensions: DomainHealthDimension[] = [
    {
      label: 'Coverage',
      value: 'Not measured',
      detail: 'The intended domain model and usable-evidence denominator are not projected; record or source counts are not coverage.',
      support: 'not_supported',
    },
    freshness,
    {
      label: 'Confidence',
      value: scoredRecords.length > 0 ? 'Record-level only' : 'Not projected',
      detail: scoredRecords.length > 0
        ? 'Some Entity, Signal, or Shift records carry exact confidence values; no domain-wide aggregation is contracted.'
        : 'No domain-wide confidence contract is projected.',
      support: scoredRecords.length > 0 ? 'observed' : 'not_supported',
    },
    conflicts.length > 0
      ? {
          label: 'Conflicts',
          value: `${conflicts.length} admitted`,
          detail: 'Explicit conflict records are loaded for inspection; this is a record count, not a quality score.',
          support: 'observed',
          attention: true,
        }
      : unsupported(page, 'conflict')
        ? {
            label: 'Conflicts',
            value: 'Unavailable',
            detail: 'The conflict resource family has no current projection contributor.',
            support: 'unavailable',
            attention: true,
          }
        : {
            label: 'Conflicts',
            value: 'Not evidenced',
            detail: 'No conflict record is loaded; absence from this page does not establish zero conflicts.',
            support: 'not_supported',
          },
    entities.length > 0
      ? {
          label: 'Resolution',
          value: 'Snapshot state only',
          detail: 'Resolved Entity Snapshots are loaded, but their presence does not establish resolution quality or unresolved volume.',
          support: 'observed',
        }
      : {
          label: 'Resolution',
          value: 'Not measured',
          detail: 'Entity Snapshot presence does not establish entity-resolution quality or unresolved volume.',
          support: 'not_supported',
        },
    sourceHealth.length === 0
      ? {
          label: 'Source health',
          value: 'Not projected',
          detail: 'Connection or source presence is not source health.',
          support: 'not_supported',
        }
      : sourceHealthDegraded
        ? {
            label: 'Source health',
            value: 'Partial readiness records',
            detail: 'Some source-readiness records are degraded. No aggregate healthy state is inferred.',
            support: 'unavailable',
            attention: true,
          }
        : {
            label: 'Source health',
            value: 'Readiness recorded',
            detail: 'Recorded-source admission and readiness are available; this does not establish aggregate source health.',
            support: 'observed',
          },
    maintenance.length === 0
      ? {
          label: 'Maintenance health',
          value: maintenanceFamiliesUnavailable ? 'Unavailable' : 'Not evidenced',
          detail: maintenanceFamiliesUnavailable
            ? 'One or more maintenance lifecycle resource families are unavailable in the current projection.'
            : 'No current Monitor or Subscription lifecycle is loaded; agent presence is not maintenance health.',
          support: maintenanceFamiliesUnavailable ? 'unavailable' : 'not_supported',
          attention: maintenanceFamiliesUnavailable || undefined,
        }
      : maintenanceDegraded
        ? {
            label: 'Maintenance health',
            value: 'Partial lifecycle records',
            detail: 'Some Monitor or Subscription lifecycle records are degraded; runtime liveness is not inferred.',
            support: 'unavailable',
            attention: true,
          }
        : maintenanceStates.some((state) => state === 'paused')
          ? {
              label: 'Maintenance health',
              value: 'Lifecycle paused',
              detail: 'An exact current Monitor or Subscription lifecycle is paused. Evaluation success and schedule adherence are not projected.',
              support: 'observed',
              attention: true,
            }
          : maintenanceStates.length === maintenance.length
            && maintenanceStates.every((state) => state === 'active')
            ? {
                label: 'Maintenance health',
                value: 'Active lifecycle recorded',
                detail: 'Current Monitor and Subscription lifecycle records are active; this does not establish runtime liveness or successful evaluation.',
                support: 'observed',
              }
            : {
                label: 'Maintenance health',
                value: 'Lifecycle state only',
                detail: 'Maintenance resources are loaded, but their exact lifecycle state is not projected consistently; runtime health remains unmeasured.',
                support: 'not_supported',
              },
    revisionHistory
      ? {
          label: 'Historical depth',
          value: 'Revision lineage only',
          detail: 'An exact predecessor revision is loaded, but comparable historical intelligence depth is not contracted.',
          support: 'observed',
        }
      : {
          label: 'Historical depth',
          value: 'Not projected',
          detail: 'Multiple unrelated Briefs do not establish history; comparable depth requires an explicit contract.',
          support: 'not_supported',
        },
  ]

  return {
    dimensions,
    pageState: page === null ? 'not_loaded' : page.state === 'degraded' ? 'degraded' : 'loaded',
    lastLoadedAt: page?.evaluated_at ?? null,
    limitations: page?.degraded_reason_refs.length
      ? ['Some requested resource families or records were unavailable when this picture was loaded.']
      : [],
  }
}

export function intelligenceViewState(
  page: IntelligenceResourcePage | null,
  loading: boolean,
  error: Error | null,
): IntelligenceViewState {
  if (page === null && loading) return 'loading_initial'
  if (page === null && error !== null) return 'unavailable'
  if (page !== null && error !== null) return 'last_loaded'
  if (page !== null && loading) return 'refreshing'
  if (page !== null && page.state === 'degraded') return 'degraded'
  if (page !== null && page.items.length === 0) return 'empty'
  return 'loaded'
}
