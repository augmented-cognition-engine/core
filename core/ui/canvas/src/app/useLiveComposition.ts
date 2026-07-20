// core/ui/canvas/src/app/useLiveComposition.ts
//
// Subscribes to the canvas WebSocket and returns the most recent L3
// composition.selected payload for the active session. When no composition
// has been emitted yet, returns null — consumers (typically <CompositionLens>)
// render their own empty state.
//
// This is the "orchestra becomes legible" wire: the substrate emits the
// canvas.composition.selected event on every CognitiveComposer.compose(),
// and this hook surfaces the payload into React state so the canvas surface
// can render it.
//
// Pattern:
//   const composition = useLiveComposition(sessionId)
//   return <CompositionLens payload={composition} />
//
// The hook also accepts an optional initial value so server-rendered or
// fixture-seeded composition can survive until the first live event lands —
// avoids a flash of empty state during demos and onboarding.
import { useEffect, useState } from 'react'

import { CanvasSocket } from '../api/canvasSocket'
import { LCE_COMPOSITION_SELECTED, type CompositionSelectedPayload } from '../types/canvas'

interface CompositionEventEnvelope {
  event_type?: string
  payload?: CompositionSelectedPayload | unknown
}

/** Type guard: does this message look like a composition.selected event with a usable payload? */
function isCompositionSelected(
  msg: Record<string, unknown>,
): msg is { event_type: string; payload: CompositionSelectedPayload } {
  const envelope = msg as CompositionEventEnvelope
  if (envelope.event_type !== LCE_COMPOSITION_SELECTED) return false
  const payload = envelope.payload
  if (payload === null || payload === undefined || typeof payload !== 'object') return false
  // Minimal shape check — meta_skills is the load-bearing field
  return Array.isArray((payload as CompositionSelectedPayload).meta_skills)
}

export interface UseLiveCompositionOptions {
  /** Initial composition to display until the first live event lands. Useful
   *  for fixtures, server-rendered pages, or demo seeding. */
  initial?: CompositionSelectedPayload | null
}

export function useLiveComposition(
  sessionId: string | null | undefined,
  options: UseLiveCompositionOptions = {},
): CompositionSelectedPayload | null {
  const [composition, setComposition] = useState<CompositionSelectedPayload | null>(
    options.initial ?? null,
  )

  useEffect(() => {
    if (sessionId === null || sessionId === undefined || sessionId === '') return

    const socket = new CanvasSocket(sessionId)
    const unsubscribe = socket.onMessage((msg) => {
      if (isCompositionSelected(msg)) {
        setComposition(msg.payload)
      }
    })
    socket.connect()

    return () => {
      unsubscribe()
      socket.close()
    }
  }, [sessionId])

  return composition
}
