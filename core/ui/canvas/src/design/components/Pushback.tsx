// core/ui/canvas/src/design/components/Pushback.tsx
//
// A voice disagreeing with the user. Codifies the partnership voice
// rule from voice-style-guide.md:
//
//     "I'd push back here — we agreed..."   ← exception: dissent
//
// Composes VoiceCallout with tone locked to "pushback". The two
// required structural pieces — the dissent statement (first-person
// signal) and the "we agreed" reference (partnership anchor) — are
// explicit props instead of free-form children so the shape of a
// pushback is invariant across surfaces.
//
// NOT red. NOT a validation error. NOT a system gate. Pushback is
// peer disagreement, rendered with editorial weight, expecting a
// reply not a dismissal.
import type { ReactNode } from 'react'

import { VoiceCallout, type VoiceCalloutFrom } from './VoiceCallout'

export interface PushbackProps {
  from: VoiceCalloutFrom
  /** The first-person dissent statement. Always starts with "I'd push
   *  back" or equivalent. */
  disagreement: string
  /** The "we agreed" reference — what shared decision/principle the
   *  pushback anchors to. */
  reference: string
  /** Optional follow-up question to keep the conversation moving. */
  question?: string
  /** Optional action row (Input + Buttons for the reply). */
  children?: ReactNode
  askedAt?: string
  dataTest?: string
}

export function Pushback({
  from,
  disagreement,
  reference,
  question,
  children,
  askedAt,
  dataTest,
}: PushbackProps) {
  return (
    <VoiceCallout
      from={from}
      tone="pushback"
      askedAt={askedAt}
      dataTest={dataTest}
      question={
        <>
          <span>{disagreement}</span>
          <span style={{ color: 'var(--ace-ink-soft)' }}> — {reference}.</span>
          {question !== undefined && <span> {question}</span>}
        </>
      }
    >
      {children}
    </VoiceCallout>
  )
}
