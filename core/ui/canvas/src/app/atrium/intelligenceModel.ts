import type {
  IntelligenceResourceKind,
  IntelligenceResourceRecord,
} from '@/api/intelligenceResourcesApi'

export const SUPPORTED_RESOURCE_KINDS = [
  'connection',
  'source',
  'entity',
  'observation',
  'signal',
  'shift',
  'case',
  'brief',
  'monitor',
  'subscription',
  'agent',
  'decision',
  'action',
  'outcome',
  'feedback',
  'evidence_lineage',
  'context_manifest',
  'memory_use',
  'builder_profile',
  'builder_session',
] as const satisfies readonly IntelligenceResourceKind[]

export const EXPLICITLY_DEGRADED_RESOURCE_KINDS = [
  'source_health',
  'uncertainty',
  'conflict',
  'semantic_revision',
] as const satisfies readonly IntelligenceResourceKind[]

export interface ResourceGroups {
  readonly intelligence: IntelligenceResourceRecord[]
  readonly opportunities: IntelligenceResourceRecord[]
  readonly agents: IntelligenceResourceRecord[]
  readonly connections: IntelligenceResourceRecord[]
  readonly strategy: IntelligenceResourceRecord[]
  readonly attention: IntelligenceResourceRecord[]
}

const GROUP_KINDS = {
  intelligence: new Set<IntelligenceResourceKind>([
    'brief',
    'signal',
    'shift',
    'entity',
    'observation',
    'evidence_lineage',
  ]),
  opportunities: new Set<IntelligenceResourceKind>(['case', 'shift', 'signal']),
  agents: new Set<IntelligenceResourceKind>([
    'agent',
    'context_manifest',
    'memory_use',
    'monitor',
    'subscription',
  ]),
  connections: new Set<IntelligenceResourceKind>([
    'connection',
    'source',
    'source_health',
  ]),
  strategy: new Set<IntelligenceResourceKind>([
    'decision',
    'action',
    'outcome',
    'feedback',
  ]),
}

function newestFirst(a: IntelligenceResourceRecord, b: IntelligenceResourceRecord): number {
  return Date.parse(b.reference.available_at) - Date.parse(a.reference.available_at)
}

export function groupResources(items: readonly IntelligenceResourceRecord[]): ResourceGroups {
  const visible = items.filter((item) => item.availability !== 'tombstoned')
  const forKinds = (kinds: Set<IntelligenceResourceKind>) =>
    visible.filter((item) => kinds.has(item.reference.resource_kind)).sort(newestFirst)

  return {
    intelligence: forKinds(GROUP_KINDS.intelligence),
    opportunities: forKinds(GROUP_KINDS.opportunities),
    agents: forKinds(GROUP_KINDS.agents),
    connections: forKinds(GROUP_KINDS.connections),
    strategy: forKinds(GROUP_KINDS.strategy),
    attention: visible
      .filter(
        (item) =>
          item.availability === 'degraded' ||
          item.reference.resource_kind === 'shift' ||
          item.reference.resource_kind === 'case' ||
          item.reference.resource_kind === 'feedback',
      )
      .sort(newestFirst),
  }
}

function searchableText(record: IntelligenceResourceRecord): string {
  let payload = ''
  try {
    payload = JSON.stringify(record.payload)
  } catch {
    payload = ''
  }
  return [
    record.title,
    record.summary ?? '',
    record.reference.resource_kind,
    ...record.subject_refs,
    payload,
  ]
    .join(' ')
    .toLocaleLowerCase()
}

function queryTerms(query: string): string[] {
  const stopTerms = new Set([
    'about', 'and', 'are', 'can', 'did', 'does', 'for', 'from', 'happened',
    'how', 'into', 'that', 'the', 'this', 'was', 'were', 'what', 'when',
    'where', 'which', 'who', 'why', 'you',
  ])
  return query
    .toLocaleLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((term) => term.length > 2 && !stopTerms.has(term))
}

export function rankResourcesForQuestion(
  query: string,
  items: readonly IntelligenceResourceRecord[],
  limit = 5,
): IntelligenceResourceRecord[] {
  const terms = queryTerms(query)
  if (terms.length === 0) return []
  const normalizedQuery = query.toLocaleLowerCase()

  function intentBoost(kind: IntelligenceResourceKind): number {
    if (/\b(changed|change|shift|moved|movement|latest)\b/.test(normalizedQuery)) {
      if (kind === 'shift') return 6
      if (kind === 'signal') return 2
    }
    if (/\b(evidence|source|citation|brief)\b/.test(normalizedQuery) && kind === 'brief') return 4
    if (/\b(opportunity|opportunities|opening)\b/.test(normalizedQuery) && kind === 'case') return 4
    return 0
  }

  return items
    .filter((item) => item.availability !== 'tombstoned')
    .map((item) => {
      const haystack = searchableText(item)
      const title = item.title.toLocaleLowerCase()
      const matched = terms.filter((term) => haystack.includes(term)).length
      const titleMatches = terms.filter((term) => title.includes(term)).length
      const kindBoost = ['brief', 'shift', 'case', 'decision'].includes(
        item.reference.resource_kind,
      )
        ? 1
        : 0
      return {
        item,
        score: matched === 0 ? 0 : matched * 2 + titleMatches * 3 + kindBoost + intentBoost(item.reference.resource_kind),
      }
    })
    .filter(({ score }) => score > 0)
    .sort(
      (a, b) =>
        b.score - a.score ||
        Date.parse(b.item.reference.available_at) -
          Date.parse(a.item.reference.available_at),
    )
    .slice(0, limit)
    .map(({ item }) => item)
}

export function kindLabel(kind: IntelligenceResourceKind): string {
  return kind
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export function compactReference(reference: string): string {
  const [, readable = reference] = reference.split(':', 2)
  return readable.length > 28 ? `${readable.slice(0, 25)}…` : readable
}
