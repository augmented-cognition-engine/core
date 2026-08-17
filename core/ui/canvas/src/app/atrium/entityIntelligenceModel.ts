import type {
  IntelligenceResourceKind,
  IntelligenceResourceRecord,
} from '@/api/intelligenceResourcesApi'

type JsonObject = Record<string, unknown>

export interface EntityAttributeProjection {
  readonly key: string
  readonly label: string
  readonly value: string
}

export interface EntityChangeProjection {
  readonly key: string
  readonly label: string
  readonly direction: 'increased' | 'decreased' | 'changed' | 'reported'
  readonly previous: string | null
  readonly current: string | null
  readonly detail: string
}

export interface EntityTimelineProjection {
  readonly record: IntelligenceResourceRecord
  readonly kindLabel: 'Material shift' | 'Signal' | 'Observation'
  readonly occurredAt: string
  readonly timeBasis: 'event effective' | 'source published' | 'observed' | 'detected' | 'as of'
}

export interface EntityRelationshipProjection {
  readonly record: IntelligenceResourceRecord
  readonly direction: 'upstream' | 'downstream'
  readonly label: 'Exact upstream record' | 'Exact derived record'
}

export interface EntityIntelligenceProjection {
  readonly entityRef: string
  readonly name: string
  readonly typeRef: string | null
  readonly current: IntelligenceResourceRecord
  readonly previous: IntelligenceResourceRecord | null
  readonly attributes: readonly EntityAttributeProjection[]
  readonly changes: readonly EntityChangeProjection[]
  readonly timeline: readonly EntityTimelineProjection[]
  readonly relationships: readonly EntityRelationshipProjection[]
  readonly evidence: readonly IntelligenceResourceRecord[]
  readonly conflicts: readonly IntelligenceResourceRecord[]
  readonly unknowns: readonly IntelligenceResourceRecord[]
  readonly confidence: number | null
}

const TIMELINE_KINDS = new Set<IntelligenceResourceKind>([
  'shift',
  'signal',
  'observation',
])

function jsonObject(value: unknown): JsonObject | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as JsonObject
    : null
}

function parsedJson(value: unknown): unknown {
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value) as unknown
  } catch {
    return value
  }
}

/** Decode the public resource plane's canonical-json wrapper without assuming a domain schema. */
export function canonicalResourcePayload(record: IntelligenceResourceRecord): JsonObject | null {
  const outer = jsonObject(record.payload)
  if (outer === null) return null
  const encoded = outer.value_json
  return encoded === undefined ? outer : jsonObject(parsedJson(encoded)) ?? outer
}

function canonicalAttributes(payload: JsonObject | null): JsonObject | null {
  if (payload === null) return null
  const attributes = jsonObject(payload.attributes)
  if (attributes === null) return null
  const decoded = attributes.value_json === undefined
    ? attributes
    : jsonObject(parsedJson(attributes.value_json))
  return decoded ?? attributes
}

function entityRef(record: IntelligenceResourceRecord): string | null {
  const payload = canonicalResourcePayload(record)
  const projected = payload?.entity_ref
  if (typeof projected === 'string' && projected.trim().length > 0) return projected.trim()
  return record.subject_refs.find((reference) => reference.startsWith('entity:')) ?? null
}

function entityTypeRef(record: IntelligenceResourceRecord): string | null {
  const value = canonicalResourcePayload(record)?.entity_type_ref
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null
}

function humanize(value: string): string {
  return value
    .replace(/^[^:]+:/, '')
    .split(/[-_/\s]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toLocaleUpperCase()}${part.slice(1)}`)
    .join(' ')
}

function displayScalar(value: unknown): string | null {
  if (typeof value === 'string') return value.trim().length > 0 ? value.trim() : null
  if (typeof value === 'number' && Number.isFinite(value)) return new Intl.NumberFormat().format(value)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (value === null) return 'Unknown'
  if (Array.isArray(value) && value.every((item) => ['string', 'number', 'boolean'].includes(typeof item))) {
    return value.slice(0, 4).map(String).join(' · ')
  }
  return null
}

function attributeEntries(record: IntelligenceResourceRecord): EntityAttributeProjection[] {
  const attributes = canonicalAttributes(canonicalResourcePayload(record))
  if (attributes === null) return []
  return Object.entries(attributes)
    .flatMap(([key, value]) => {
      const displayed = displayScalar(value)
      return displayed === null ? [] : [{ key, label: humanize(key), value: displayed }]
    })
    .sort((left, right) => left.label.localeCompare(right.label))
}

function rawAttributes(record: IntelligenceResourceRecord): JsonObject {
  return canonicalAttributes(canonicalResourcePayload(record)) ?? {}
}

function explicitConfidence(record: IntelligenceResourceRecord): number | null {
  const value = canonicalResourcePayload(record)?.confidence
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
    ? value
    : null
}

function snapshotChanges(
  current: IntelligenceResourceRecord,
  previous: IntelligenceResourceRecord | null,
): EntityChangeProjection[] {
  if (previous === null) return []
  const currentAttributes = rawAttributes(current)
  const previousAttributes = rawAttributes(previous)
  return [...new Set([...Object.keys(currentAttributes), ...Object.keys(previousAttributes)])]
    .sort()
    .flatMap((key) => {
      const currentValue = currentAttributes[key]
      const previousValue = previousAttributes[key]
      if (JSON.stringify(currentValue) === JSON.stringify(previousValue)) return []
      const displayedCurrent = displayScalar(currentValue)
      const displayedPrevious = displayScalar(previousValue)
      if (displayedCurrent === null || displayedPrevious === null) return []
      const direction = typeof currentValue === 'number' && typeof previousValue === 'number'
        ? currentValue > previousValue
          ? 'increased'
          : currentValue < previousValue
            ? 'decreased'
            : 'changed'
        : 'changed'
      return [{
        key,
        label: humanize(key),
        direction,
        previous: displayedPrevious,
        current: displayedCurrent,
        detail: `${displayedPrevious} → ${displayedCurrent}`,
      }]
    })
}

function recordKey(record: IntelligenceResourceRecord): string {
  return `${record.reference.resource_id}:${record.reference.revision}`
}

function referenceKey(reference: IntelligenceResourceRecord['reference']): string {
  return `${reference.resource_id}:${reference.revision}`
}

function isSubjectScoped(record: IntelligenceResourceRecord, subject: string): boolean {
  return record.subject_refs.includes(subject)
}

function explicitRelationships(
  current: IntelligenceResourceRecord,
  items: readonly IntelligenceResourceRecord[],
): EntityRelationshipProjection[] {
  const byReference = new Map(items.map((item) => [recordKey(item), item]))
  const upstream = current.provenance.flatMap((reference) => {
    const record = byReference.get(referenceKey(reference))
    return record === undefined ? [] : [{
      record,
      direction: 'upstream' as const,
      label: 'Exact upstream record' as const,
    }]
  })
  const currentKey = recordKey(current)
  const downstream = items.flatMap((record) =>
    record.provenance.some((reference) => referenceKey(reference) === currentKey)
      ? [{
          record,
          direction: 'downstream' as const,
          label: 'Exact derived record' as const,
        }]
      : [],
  )
  return [...upstream, ...downstream]
    .sort((left, right) => Date.parse(right.record.reference.as_of) - Date.parse(left.record.reference.as_of))
}

function projectedTime(record: IntelligenceResourceRecord): {
  occurredAt: string
  timeBasis: EntityTimelineProjection['timeBasis']
} {
  const payload = canonicalResourcePayload(record)
  const candidates: readonly [keyof JsonObject, EntityTimelineProjection['timeBasis']][] = [
    ['event_effective_at', 'event effective'],
    ['source_published_at', 'source published'],
    ['observed_at', 'observed'],
    ['detected_at', 'detected'],
  ]
  for (const [key, timeBasis] of candidates) {
    const value = payload?.[key]
    if (typeof value === 'string' && !Number.isNaN(Date.parse(value))) {
      return { occurredAt: value, timeBasis }
    }
  }
  return { occurredAt: record.reference.as_of, timeBasis: 'as of' }
}

function timelineForEntity(
  subject: string,
  items: readonly IntelligenceResourceRecord[],
): EntityTimelineProjection[] {
  return items
    .filter((item) => TIMELINE_KINDS.has(item.reference.resource_kind) && isSubjectScoped(item, subject))
    .map((record) => {
      const time = projectedTime(record)
      const kindLabel = record.reference.resource_kind === 'shift'
        ? 'Material shift' as const
        : record.reference.resource_kind === 'signal'
          ? 'Signal' as const
          : 'Observation' as const
      return { record, kindLabel, ...time }
    })
    .sort((left, right) => Date.parse(right.occurredAt) - Date.parse(left.occurredAt))
}

function reportedChanges(
  subject: string,
  items: readonly IntelligenceResourceRecord[],
): EntityChangeProjection[] {
  return items
    .filter((item) => item.reference.resource_kind === 'shift' && isSubjectScoped(item, subject))
    .sort((left, right) => Date.parse(right.reference.as_of) - Date.parse(left.reference.as_of))
    .slice(0, 3)
    .map((record) => ({
      key: recordKey(record),
      label: record.title,
      direction: 'reported' as const,
      previous: null,
      current: null,
      detail: record.summary ?? 'A subject-scoped Shift is admitted without a display summary.',
    }))
}

function linkedLimits(
  kind: 'conflict' | 'uncertainty',
  subject: string,
  snapshots: readonly IntelligenceResourceRecord[],
  items: readonly IntelligenceResourceRecord[],
): IntelligenceResourceRecord[] {
  const snapshotKeys = new Set(snapshots.map(recordKey))
  return items.filter((item) =>
    item.reference.resource_kind === kind
    && (
      isSubjectScoped(item, subject)
      || item.provenance.some((reference) => snapshotKeys.has(referenceKey(reference)))
    ),
  )
}

function projectionForSnapshots(
  subject: string,
  snapshots: readonly IntelligenceResourceRecord[],
  items: readonly IntelligenceResourceRecord[],
): EntityIntelligenceProjection {
  const ordered = [...snapshots].sort(
    (left, right) => Date.parse(right.reference.as_of) - Date.parse(left.reference.as_of),
  )
  const current = ordered[0]
  if (current === undefined) throw new Error('entity projection requires a current snapshot')
  const previous = ordered[1] ?? null
  const snapshotDelta = snapshotChanges(current, previous)
  const relationships = explicitRelationships(current, items)
  const nameAttribute = attributeEntries(current).find((attribute) => attribute.key.toLocaleLowerCase() === 'name')
  return {
    entityRef: subject,
    name: nameAttribute?.value ?? humanize(current.title || subject),
    typeRef: entityTypeRef(current),
    current,
    previous,
    attributes: attributeEntries(current),
    changes: snapshotDelta.length > 0 ? snapshotDelta : reportedChanges(subject, items),
    timeline: timelineForEntity(subject, items),
    relationships,
    evidence: relationships
      .filter((relationship) => relationship.direction === 'upstream')
      .map((relationship) => relationship.record),
    conflicts: linkedLimits('conflict', subject, ordered, items),
    unknowns: linkedLimits('uncertainty', subject, ordered, items),
    confidence: explicitConfidence(current),
  }
}

export function projectEntityIntelligence(
  items: readonly IntelligenceResourceRecord[],
): EntityIntelligenceProjection[] {
  const visible = items.filter((item) => item.availability !== 'tombstoned')
  const grouped = new Map<string, IntelligenceResourceRecord[]>()
  visible
    .filter((item) => item.reference.resource_kind === 'entity')
    .forEach((item) => {
      const subject = entityRef(item)
      if (subject === null) return
      grouped.set(subject, [...(grouped.get(subject) ?? []), item])
    })
  return [...grouped.entries()]
    .map(([subject, snapshots]) => projectionForSnapshots(subject, snapshots, visible))
    .sort((left, right) => left.name.localeCompare(right.name))
}
