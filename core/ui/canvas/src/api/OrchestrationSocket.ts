// frontend/src/api/OrchestrationSocket.ts
/// <reference types="vite/client" />
import type { OrchestrationEvent } from '../types/canvas'

type EventHandler = (event: OrchestrationEvent) => void

export class OrchestrationSocket {
  private ws: WebSocket | null = null
  private sessionId: string
  private handlers: EventHandler[] = []
  private retryDelay = 1000
  private maxDelay = 30000
  private closed = false
  private lastRunId: string | null = null
  private lastTaskId: string | null = null

  constructor(sessionId: string) {
    this.sessionId = sessionId
  }

  connect() {
    if (this.closed) return
    if (this.ws && this.ws.readyState !== WebSocket.CLOSED) return
    const wsBase = import.meta.env.VITE_WS_URL ?? `ws://${window.location.host}`
    const url = `${wsBase}/canvas/sessions/${this.sessionId}/orchestration`
    this.ws = new WebSocket(url)

    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as OrchestrationEvent
        if (data.task_id) this.lastTaskId = data.task_id
        if (data.run_id) this.lastRunId = data.run_id
        this.handlers.forEach((h) => h(data))
      } catch {
        // ignore malformed messages
      }
    }

    this.ws.onclose = () => {
      if (this.closed) return
      setTimeout(() => {
        this.retryDelay = Math.min(this.retryDelay * 2, this.maxDelay)
        this.connect()
        if (this.lastRunId && this.lastTaskId) {
          this.ws?.addEventListener(
            'open',
            () => {
              // TODO(M3): legacy path — not wired to the seq resume cursor; superseded by useOrchestrationSession
              this.send({ type: 'resume', run_id: this.lastRunId!, last_task_id: this.lastTaskId! })
            },
            { once: true },
          )
        }
      }, this.retryDelay)
    }

    this.ws.onopen = () => {
      this.retryDelay = 1000
    }
  }

  send(message: Record<string, unknown>) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    }
  }

  sendMessage(content: string, parentDecisionId?: string) {
    this.send({ type: 'message', content, parent_decision_id: parentDecisionId })
  }

  onEvent(handler: EventHandler) {
    this.handlers.push(handler)
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler)
    }
  }

  close() {
    this.closed = true
    this.ws?.close()
  }
}
