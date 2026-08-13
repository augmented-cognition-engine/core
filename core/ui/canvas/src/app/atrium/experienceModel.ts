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
