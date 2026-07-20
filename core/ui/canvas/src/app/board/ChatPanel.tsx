// core/ui/canvas/src/app/board/ChatPanel.tsx
//
// The conversation channel that runs alongside the 2D board. Backend
// agents post AttentionRequests + agent-notes into the messages Y.Array;
// the panel renders them top→bottom; user replies go back via the ask
// input. Reuses AttentionCallout for attention-request rendering so
// the "Partner → you · just now" vocabulary stays consistent with the
// pre-board canvas (commit f06487ad).
//
// Layout: docked-right column inside CanvasSurface's workspace grid.
// Separate scroll container so the board can pan/zoom independently of
// the conversation log.
import { useEffect, useRef, useState } from 'react'
import type * as Y from 'yjs'

import { AttentionCallout } from '../AttentionCallout'
import { Input } from '../../design/components'
import type { AttentionRequestState } from '../state'
import type { BoardMessage } from './messages'
import { postUserReply, useMessages } from './messages'

interface ChatPanelProps {
  doc: Y.Doc
}

export function ChatPanel({ doc }: ChatPanelProps) {
  const messages = useMessages(doc)
  const logRef = useRef<HTMLDivElement | null>(null)

  // Auto-scroll the log to the bottom on new messages — the freshest
  // exchange should always be visible without the user reaching.
  useEffect(() => {
    if (logRef.current === null) return
    logRef.current.scrollTop = logRef.current.scrollHeight
  }, [messages.length])

  return (
    <aside
      aria-label="Team conversation"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: 640,
        background: 'var(--ace-surface-raised)',
        borderRadius: 'var(--ace-radius-lg)',
        boxShadow: 'var(--ace-shadow-card)',
        overflow: 'hidden',
      }}
    >
      <header
        style={{
          padding: 'var(--ace-space-3) var(--ace-space-4)',
          fontFamily: 'var(--ace-font-sans)',
          fontSize: 'var(--ace-text-xs)',
          fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
          letterSpacing: 'var(--ace-track-widest)',
          textTransform: 'uppercase',
          color: 'var(--ace-ink-muted)',
          borderBottom: '1px solid var(--ace-line-soft)',
        }}
      >
        Conversation
      </header>

      <div
        ref={logRef}
        style={{
          flex: '1 1 auto',
          overflowY: 'auto',
          padding: 'var(--ace-space-4)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--ace-space-3)',
        }}
      >
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          messages.map((m) => (
            <MessageRow key={m.id} message={m} doc={doc} />
          ))
        )}
      </div>

      <ChatInput
        onSend={(body) => {
          postUserReply(doc, body, latestAttentionId(messages))
        }}
      />
    </aside>
  )
}

function EmptyState() {
  return (
    <div
      style={{
        textAlign: 'center',
        marginTop: 'var(--ace-space-12)',
        fontFamily: 'var(--ace-font-serif)',
        fontStyle: 'italic',
        color: 'var(--ace-ink-muted)',
        fontSize: 'var(--ace-text-md)',
        lineHeight: 'var(--ace-leading-relaxed)',
      }}
    >
      The team is reading along. <br />
      Speak when you have something to add — or wait, and they'll come to you.
    </div>
  )
}

function MessageRow({ message, doc }: { message: BoardMessage; doc: Y.Doc }) {
  if (message.type === 'attention-request') {
    // Map BoardMessage → AttentionRequestState and reuse the existing
    // AttentionCallout component (same vocabulary, same affordances).
    const request: AttentionRequestState = {
      id: message.id,
      speaker: message.speaker,
      accent: message.accent,
      initial: message.glyph,
      question: message.body,
      triggeredBy: message.triggeredBy,
      askedAt: formatRelativeTime(message.postedAt),
      onReply: (text) => postUserReply(doc, text, message.id),
    }
    return <AttentionCallout request={request} />
  }

  // user-reply or agent-note — simpler row treatment
  return <SimpleMessageRow message={message} />
}

function SimpleMessageRow({ message }: { message: BoardMessage }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'auto 1fr',
        gap: 'var(--ace-space-3)',
        padding: 'var(--ace-space-2) var(--ace-space-3)',
        background: message.fromUser
          ? 'var(--ace-surface-recessed)'
          : 'transparent',
        borderRadius: 'var(--ace-radius-base)',
      }}
    >
      <span
        aria-hidden
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 24,
          height: 24,
          borderRadius: '50%',
          background: 'var(--ace-surface-raised)',
          color: message.accent,
          fontFamily: 'var(--ace-font-sans)',
          fontSize: 'var(--ace-text-sm)',
          fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
          boxShadow: `0 0 0 1.25px ${message.accent}`,
        }}
      >
        {message.glyph}
      </span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
        <div
          style={{
            fontFamily: 'var(--ace-font-sans)',
            fontSize: 'var(--ace-text-xs)',
            color: message.accent,
            fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
            letterSpacing: 'var(--ace-track-wide)',
            textTransform: 'uppercase',
          }}
        >
          {message.speaker}
          <span
            style={{
              color: 'var(--ace-ink-muted)',
              marginLeft: 'var(--ace-space-2)',
              fontWeight: 'var(--ace-weight-regular)' as unknown as number,
              letterSpacing: 'var(--ace-track-normal)',
              textTransform: 'none',
            }}
          >
            · {formatRelativeTime(message.postedAt)}
          </span>
        </div>
        <p
          style={{
            margin: 0,
            fontFamily: 'var(--ace-font-serif)',
            fontSize: 'var(--ace-text-md)',
            lineHeight: 'var(--ace-leading-prose)',
            color: 'var(--ace-ink)',
          }}
        >
          {message.body}
        </p>
      </div>
    </div>
  )
}

function ChatInput({ onSend }: { onSend: (text: string) => void }) {
  const [text, setText] = useState('')
  const submit = (value: string) => {
    onSend(value)
    setText('')
  }
  return (
    <div
      style={{
        padding: 'var(--ace-space-3) var(--ace-space-4)',
        borderTop: '1px solid var(--ace-line-soft)',
        background: 'var(--ace-surface-raised)',
      }}
    >
      <Input
        value={text}
        onChange={setText}
        onSubmit={submit}
        placeholder="reply, ask, or redirect…"
        ariaLabel="reply to the team"
      />
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────

function latestAttentionId(messages: BoardMessage[]): string | undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].type === 'attention-request') return messages[i].id
  }
  return undefined
}

function formatRelativeTime(ts: number): string {
  const diffMs = Date.now() - ts
  const seconds = Math.floor(diffMs / 1000)
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return new Date(ts).toLocaleString()
}
