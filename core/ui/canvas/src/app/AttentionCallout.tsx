// core/ui/canvas/src/app/AttentionCallout.tsx
//
// "Heads up — the team needs you on X." Surface wiring around the
// design-system VoiceCallout primitive. The primitive owns the visual
// shape (avatar gutter, byline, accent edge, action row layout); this
// surface manages reply state and dispatches to request.onReply.
//
// One callout per request. Multiple stack vertically. No modal, no
// notification toast — conversation moments, not alerts.
import { useState } from 'react'

import { Button, Input, VoiceCallout } from '../design/components'
import type { AttentionRequestState } from './state'

interface AttentionCalloutProps {
  request: AttentionRequestState
}

export function AttentionCallout({ request }: AttentionCalloutProps) {
  const [text, setText] = useState('')
  const submit = (value: string) => {
    request.onReply(value)
    setText('')
  }
  return (
    <VoiceCallout
      from={{
        speaker: request.speaker,
        accent: request.accent,
        initial: request.initial,
      }}
      askedAt={request.askedAt}
      triggeredBy={request.triggeredBy}
      question={request.question}
    >
      <div style={{ flex: '1 1 280px', minWidth: 240 }}>
        <Input
          value={text}
          onChange={setText}
          onSubmit={submit}
          placeholder="push back, ask back, or tell them where you land…"
          ariaLabel={`reply to ${request.speaker}`}
        />
      </div>
      {request.quickActions?.map((a) => (
        <Button key={a.id} variant="secondary" size="md" onClick={a.onClick}>
          {a.label}
        </Button>
      ))}
    </VoiceCallout>
  )
}
