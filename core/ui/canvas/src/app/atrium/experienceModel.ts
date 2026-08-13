import type { IntelligenceResourcePage } from '@/api/intelligenceResourcesApi'

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

  const encoded = payloadText(root, 'value_json')
  if (encoded === null) return []

  let material: Record<string, unknown> | null = null
  try {
    material = displayPayload(JSON.parse(encoded))
  } catch {
    return []
  }
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
