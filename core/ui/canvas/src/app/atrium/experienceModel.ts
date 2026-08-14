import type {
  IntelligenceResourcePage,
  IntelligenceResourceRecord,
} from '@/api/intelligenceResourcesApi'

const INITIALISMS = new Map([
  ['ace', 'ACE'],
  ['ai', 'AI'],
  ['api', 'API'],
  ['b2b', 'B2B'],
  ['cx', 'CX'],
  ['gtm', 'GTM'],
  ['ip', 'IP'],
])

function displayWord(word: string): string {
  const normalized = word.toLocaleLowerCase()
  return INITIALISMS.get(normalized) ?? `${normalized.charAt(0).toLocaleUpperCase()}${normalized.slice(1)}`
}

export function productDisplayName(productId: string | null | undefined): string {
  if (productId === null || productId === undefined) return 'Your Intelligence'
  const parts = productId.split(':')
  const readable = productId.includes(':') ? parts[parts.length - 1] ?? productId : productId
  const words = readable.split(/[-_/\s]+/).filter(Boolean)
  if (words.length === 0) return 'Your Intelligence'
  return words.map(displayWord).join(' ')
}

export function pageFreshness(page: IntelligenceResourcePage | null): string {
  if (page === null) return 'Awaiting first update'
  const date = new Date(page.evaluated_at)
  if (Number.isNaN(date.valueOf())) return 'Update time unavailable'
  return `Updated ${new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)}`
}

export function payloadText(payload: unknown, key: string): string | null {
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) return null
  const value = (payload as Record<string, unknown>)[key]
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null
}

export function payloadNumber(payload: unknown, key: string): number | null {
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) return null
  const value = (payload as Record<string, unknown>)[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export type IntelligenceStorySectionId =
  | 'what_changed'
  | 'why_it_matters'
  | 'how_we_know'
  | 'when_it_changed'

export interface IntelligenceStorySection {
  readonly id: IntelligenceStorySectionId
  readonly label: string
  readonly body: string
}

interface BriefClaimMaterial {
  readonly statement: string
}

interface BriefCitationMaterial {
  readonly citation_id: string
  readonly source_ref: string
}

const STORY_SECTIONS: readonly {
  readonly id: IntelligenceStorySectionId
  readonly label: string
}[] = [
  { id: 'what_changed', label: 'What changed' },
  { id: 'why_it_matters', label: 'Why it matters' },
  { id: 'how_we_know', label: 'How we know' },
  { id: 'when_it_changed', label: 'When it changed' },
]

function displayPayload(payload: unknown): Record<string, unknown> | null {
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) return null
  return payload as Record<string, unknown>
}

function canonicalPayloadMaterial(payload: unknown): Record<string, unknown> | null {
  const root = displayPayload(payload)
  if (root === null) return null
  const encoded = payloadText(root, 'value_json')
  if (encoded === null) return root
  try {
    return displayPayload(JSON.parse(encoded))
  } catch {
    return root
  }
}

function objectArray(payload: Record<string, unknown>, key: string): Record<string, unknown>[] {
  const value = payload[key]
  if (!Array.isArray(value)) return []
  return value.filter(
    (item): item is Record<string, unknown> => typeof item === 'object' && item !== null && !Array.isArray(item),
  )
}

function briefClaims(payload: Record<string, unknown>): BriefClaimMaterial[] {
  return objectArray(payload, 'claims').flatMap((item) => {
    const statement = payloadText(item, 'statement')
    return statement === null ? [] : [{ statement }]
  })
}

function briefCitations(payload: Record<string, unknown>): BriefCitationMaterial[] {
  return objectArray(payload, 'citations').flatMap((item) => {
    const citationId = payloadText(item, 'citation_id')
    const sourceRef = payloadText(item, 'source_ref')
    return citationId === null || sourceRef === null
      ? []
      : [{ citation_id: citationId, source_ref: sourceRef }]
  })
}

function listed(values: readonly string[], empty: string): string {
  if (values.length === 0) return empty
  const visible = values.slice(0, 3).map((value) => `“${value}”`).join('; ')
  return values.length > 3 ? `${visible}; and ${values.length - 3} more` : visible
}

/** Explain one immutable Brief revision against the immediately prior Brief. */
export function briefRevisionStory(
  current: IntelligenceResourceRecord,
  previous: IntelligenceResourceRecord | undefined,
): IntelligenceStorySection[] {
  if (
    previous === undefined
    || current.reference.resource_kind !== 'brief'
    || previous.reference.resource_kind !== 'brief'
    || current.reference.product_id !== previous.reference.product_id
  ) return intelligenceStoryForRecord(current)

  const currentPayload = canonicalPayloadMaterial(current.payload)
  const previousPayload = canonicalPayloadMaterial(previous.payload)
  if (currentPayload === null || previousPayload === null) return intelligenceStoryForRecord(current)

  const currentStatements = new Set(briefClaims(currentPayload).map((claim) => claim.statement))
  const previousStatements = new Set(briefClaims(previousPayload).map((claim) => claim.statement))
  const addedClaims = [...currentStatements].filter((statement) => !previousStatements.has(statement)).sort()
  const retiredClaims = [...previousStatements].filter((statement) => !currentStatements.has(statement)).sort()

  const currentCitations = briefCitations(currentPayload)
  const previousCitations = briefCitations(previousPayload)
  const currentCitationIds = new Set(currentCitations.map((citation) => citation.citation_id))
  const previousCitationIds = new Set(previousCitations.map((citation) => citation.citation_id))
  const addedSources = [...new Set(
    currentCitations
      .filter((citation) => !previousCitationIds.has(citation.citation_id))
      .map((citation) => citation.source_ref),
  )].sort()
  const retiredEvidenceCount = previousCitations.filter(
    (citation) => !currentCitationIds.has(citation.citation_id),
  ).length

  const currentLineageIds = new Set(current.provenance.map((item) => item.resource_id))
  const previousLineageIds = new Set(previous.provenance.map((item) => item.resource_id))
  const addedLineageCount = [...currentLineageIds].filter((item) => !previousLineageIds.has(item)).length
  const retiredLineageCount = [...previousLineageIds].filter((item) => !currentLineageIds.has(item)).length

  const whatChanged = addedClaims.length === 0 && retiredClaims.length === 0
    ? 'The supported claim set is unchanged; this revision refreshes its exact evidence and timing.'
    : `New grounded claims: ${listed(addedClaims, 'none')}. Retired grounded claims: ${listed(retiredClaims, 'none')}.`
  const why = `This revision incorporates ${addedLineageCount} newly available upstream record${addedLineageCount === 1 ? '' : 's'} and leaves ${retiredLineageCount} prior record${retiredLineageCount === 1 ? '' : 's'} outside its new evidence closure.`
  const how = `Newly cited sources: ${listed(addedSources, 'none')}. ${retiredEvidenceCount} earlier citation${retiredEvidenceCount === 1 ? '' : 's'} no longer ${retiredEvidenceCount === 1 ? 'supports' : 'support'} the latest Brief.`
  const when = `The prior Brief was current as of ${previous.reference.as_of}; this revision is current as of ${current.reference.as_of} and became available at ${current.reference.available_at}.`

  return [
    { id: 'what_changed', label: 'What changed', body: whatChanged },
    { id: 'why_it_matters', label: 'Why this revision exists', body: why },
    { id: 'how_we_know', label: 'Evidence change', body: how },
    { id: 'when_it_changed', label: 'When it changed', body: when },
  ]
}

function unescapeCanonicalMarkdown(value: string): string {
  return value.replace(/\\([\\`*{}[\]()#+\-.!_>])/g, '$1').trim()
}

function claimBody(value: string): string {
  const supportMarkers = [' (cited supports:', ' (inference supports:']
  const markerIndexes = supportMarkers
    .map((marker) => value.indexOf(marker))
    .filter((index) => index >= 0)
  const end = markerIndexes.length === 0 ? value.length : Math.min(...markerIndexes)
  return unescapeCanonicalMarkdown(value.slice(0, end))
}

/** Project the stable What / Why / How / When grammar from an opaque resource payload. */
export function intelligenceStorySections(payload: unknown): IntelligenceStorySection[] {
  const root = displayPayload(payload)
  if (root === null) return []

  const direct = STORY_SECTIONS.flatMap(({ id, label }) => {
    const body = payloadText(root, id)
    return body === null ? [] : [{ id, label, body }]
  })
  if (direct.length > 0) return direct

  const material = canonicalPayloadMaterial(root)
  const markdown = material === null ? null : payloadText(material, 'body_markdown')
  if (markdown === null) return []

  const byId = new Map<IntelligenceStorySectionId, IntelligenceStorySection>()
  let active: IntelligenceStorySectionId | null = null
  for (const line of markdown.split('\n')) {
    const heading = /^##\s+(.+?)\s*$/.exec(line)
    if (heading !== null) {
      const normalized = heading[1]?.trim().toLocaleLowerCase().replace(/\s+/g, '_')
      active = STORY_SECTIONS.some(({ id }) => id === normalized)
        ? (normalized as IntelligenceStorySectionId)
        : null
      continue
    }
    if (active === null || !line.startsWith('- ')) continue
    const definition = STORY_SECTIONS.find(({ id }) => id === active)
    const body = claimBody(line.slice(2))
    if (definition !== undefined && body.length > 0) {
      byId.set(active, { id: active, label: definition.label, body })
    }
    active = null
  }

  return STORY_SECTIONS.flatMap(({ id }) => {
    const section = byId.get(id)
    return section === undefined ? [] : [section]
  })
}

const DECISION_FACING_KINDS = new Set([
  'signal',
  'shift',
  'case',
  'brief',
  'decision',
  'action',
  'outcome',
  'feedback',
])

const INVARIANT_MATERIALITY: Readonly<Record<string, string>> = {
  signal: 'It met the configured relevance and routing criteria, so it now warrants attention.',
  shift: 'The watched state no longer matches its prior baseline, so the current picture may need reassessment.',
  case: 'ACE has bounded the question and assembled its evidence so it is ready for investigation.',
  brief: 'It brings the material change, evidence, timing, and uncertainty into one reviewable picture.',
  decision: 'A governed choice is now on record and can be traced to its evidence.',
  action: 'An authorized response is now part of the accountable decision path.',
  outcome: 'A result is now observable and can be compared with the intended decision.',
  feedback: 'This result can inform future ranking only through the governed learning path.',
}

const EVENT_TIME_KEYS = [
  'detected_at',
  'assembled_at',
  'decided_at',
  'authorized_at',
  'occurred_at',
  'observed_at',
  'generated_at',
] as const

function recordedTimeStory(record: IntelligenceResourceRecord): string {
  const material = canonicalPayloadMaterial(record.payload)
  const eventTime = material === null
    ? null
    : EVENT_TIME_KEYS
      .map((key) => payloadText(material, key))
      .find((value) => value !== null) ?? null
  if (eventTime !== null) return `ACE detected or assembled this at ${eventTime}.`
  return `The evidence picture is current as of ${record.reference.as_of}; a distinct event time was not supplied.`
}

/**
 * Give every decision-facing resource the same readable story without inventing
 * domain facts. Explicit domain material wins; generic fallbacks disclose when
 * materiality or event time has not yet been supplied.
 */
export function intelligenceStoryForRecord(
  record: IntelligenceResourceRecord,
): IntelligenceStorySection[] {
  const explicit = intelligenceStorySections(record.payload)
  if (explicit.length > 0) return explicit
  if (!DECISION_FACING_KINDS.has(record.reference.resource_kind)) return []

  const what = record.summary ?? record.title
  const why = payloadText(record.payload, 'why_it_matters')
    ?? INVARIANT_MATERIALITY[record.reference.resource_kind]
  const evidenceCount = record.provenance.length

  return [
    { id: 'what_changed', label: 'What changed', body: what },
    {
      id: 'why_it_matters',
      label: 'Why it matters',
      body: why ?? 'Its decision relevance has not yet been established.',
    },
    {
      id: 'how_we_know',
      label: 'How we know',
      body: evidenceCount === 0
        ? 'No upstream evidence link is projected for this record.'
        : `${evidenceCount} governed evidence link${evidenceCount === 1 ? '' : 's'} support this record.`,
    },
    {
      id: 'when_it_changed',
      label: 'When it changed',
      body: recordedTimeStory(record),
    },
  ]
}
