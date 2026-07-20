// frontend/src/api/canvasSocket.ts
/// <reference types="vite/client" />
type MessageHandler = (event: Record<string, unknown>) => void

export class CanvasSocket {
  private ws: WebSocket | null = null
  private sessionId: string
  private handlers: MessageHandler[] = []
  private retryDelay = 1000
  private maxDelay = 30000
  private closed = false

  constructor(sessionId: string) {
    this.sessionId = sessionId
  }

  connect() {
    if (this.closed) return
    if (this.ws && this.ws.readyState !== WebSocket.CLOSED) return
    const wsBase = import.meta.env.VITE_WS_URL ?? `ws://${window.location.host}`
    const url = `${wsBase}/canvas/sessions/${this.sessionId}/stream`
    this.ws = new WebSocket(url)

    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as Record<string, unknown>
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
      }, this.retryDelay)
    }

    this.ws.onopen = () => {
      this.retryDelay = 1000  // reset on successful connect
    }
  }

  onMessage(handler: MessageHandler) {
    this.handlers.push(handler)
    return () => { this.handlers = this.handlers.filter((h) => h !== handler) }
  }

  close() {
    this.closed = true
    this.ws?.close()
  }
}
