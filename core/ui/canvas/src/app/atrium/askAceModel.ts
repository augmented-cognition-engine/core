import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'

import { intelligenceStoryForRecord } from './experienceModel'
import { rankResourcesForQuestion } from './intelligenceModel'

export interface AskAceAnswer {
  readonly conclusion: string
  readonly whyItMatters: string | null
  readonly whenItChanged: string | null
  readonly evidence: readonly IntelligenceResourceRecord[]
  readonly limitation: string
}

function requestedSection(question: string): 'what_changed' | 'why_it_matters' | 'how_we_know' | 'when_it_changed' {
  const normalized = question.toLocaleLowerCase()
  if (/\b(evidence|source|citation|how (?:do|did|can) (?:we|you) know)\b/.test(normalized)) return 'how_we_know'
  if (/\bwhy\b/.test(normalized)) return 'why_it_matters'
  if (/^\s*when\b|\bwhen did\b/.test(normalized)) return 'when_it_changed'
  return 'what_changed'
}

function sectionBody(
  record: IntelligenceResourceRecord,
  id: 'what_changed' | 'why_it_matters' | 'how_we_know' | 'when_it_changed',
): string | null {
  return intelligenceStoryForRecord(record).find((section) => section.id === id)?.body ?? null
}

export function answerQuestionFromResources(
  question: string,
  items: readonly IntelligenceResourceRecord[],
): AskAceAnswer | null {
  const evidence = rankResourcesForQuestion(question, items, 5)
  const primary = evidence[0]
  if (primary === undefined) return null

  const requested = requestedSection(question)
  const conclusion = sectionBody(primary, requested)
    ?? sectionBody(primary, 'what_changed')
    ?? primary.summary
    ?? primary.title

  const limitation = primary.availability === 'degraded'
    ? 'The leading record is incomplete. ACE is showing the supported portion and preserving the missing-context warning.'
    : primary.provenance.length === 0
      ? 'This answer is limited to a root record with no projected upstream evidence link.'
      : 'This answer is limited to the governed records currently available; ACE has not inferred beyond them.'

  return {
    conclusion,
    whyItMatters: sectionBody(primary, 'why_it_matters'),
    whenItChanged: sectionBody(primary, 'when_it_changed'),
    evidence,
    limitation,
  }
}

