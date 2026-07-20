// core/ui/canvas/src/app/board/messages.ts
//
// Shared schema for chat-panel messages that live on the Y.Doc as a
// Y.Array<BoardMessage>. Backend (core/engine/canvas_bridge/messages.py)
// writes attention-requests and agent-notes; the chat panel reads + the
// user's reply input writes user-reply entries back.
//
// Keep this in sync with the AgentChatMessage dataclass on the backend.
import { useEffect, useState } from 'react'
import * as Y from 'yjs'

export type BoardMessageType =
  | 'attention-request'   // agent asks the user for a call
  | 'user-reply'          // user's response in flow
  | 'agent-note'          // agent posts a side note (not a question)

export interface BoardMessage {
  id: string
  type: BoardMessageType
  /** Display label — "Partner", "Architecture", "You" */
  speaker: string
  /** CSS color (hex or var()) — drives avatar ring + edge mark */
  accent: string
  /** Single-character avatar mark */
  glyph: string
  /** Message body — plain text. The chat panel wraps in serif for
   *  prose-feeling reads. */
  body: string
  /** Editorial timestamp like "just now" or "1 min ago".
   *  Backend writes ISO; this is the display string. */
  postedAt: number
  /** Attention-request only — what triggered the agent to ask. */
  triggeredBy?: string
  /** Agent id (for non-user messages) — lets backend route routes
   *  for follow-up actions. */
  fromAgentId?: string
  /** True for user-reply messages */
  fromUser?: boolean
  /** user-reply only — id of the attention-request being answered. */
  inReplyToId?: string
}

const MESSAGES_KEY = 'chat_messages'

export function getMessagesArray(doc: Y.Doc): Y.Array<BoardMessage> {
  return doc.getArray<BoardMessage>(MESSAGES_KEY)
}

/** React hook — re-renders on Y.Array mutations. Snapshots into a
 *  plain JS array so React's reconciliation works against value
 *  equality. */
export function useMessages(doc: Y.Doc): BoardMessage[] {
  const [messages, setMessages] = useState<BoardMessage[]>(() => {
    return getMessagesArray(doc).toArray()
  })

  useEffect(() => {
    const arr = getMessagesArray(doc)
    const observer = () => setMessages(arr.toArray())
    arr.observe(observer)
    // Catch up in case the array changed between initial state and
    // observer attach.
    setMessages(arr.toArray())
    return () => arr.unobserve(observer)
  }, [doc])

  return messages
}

/** Append a user-reply to the messages array. Backend bridge
 *  subscribes and may route the reply to an agent for a follow-up. */
export function postUserReply(
  doc: Y.Doc,
  body: string,
  inReplyToId?: string,
): void {
  const msg: BoardMessage = {
    id: `user-${crypto.randomUUID()}`,
    type: 'user-reply',
    speaker: 'You',
    accent: 'var(--ace-ink)',
    glyph: 'E', // matches presence ribbon's user initial
    body,
    postedAt: Date.now(),
    fromUser: true,
    inReplyToId,
  }
  getMessagesArray(doc).push([msg])
}
