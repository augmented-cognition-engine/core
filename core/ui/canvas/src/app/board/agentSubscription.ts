// core/ui/canvas/src/app/board/agentSubscription.ts
//
// Subscribe to the Yjs ``agent_contributions`` array — entries written
// by the Python canvas bridge in core/engine/canvas_bridge/ — and
// materialize each into a tldraw shape. New entries spawn new shapes;
// existing entries (matched by id) update their shape props in place
// so the inFlight → landed transition flows through.
//
// Why a separate Y.Array (not just adding to the tldraw snapshot
// directly): the backend doesn't have to know tldraw's internal
// record format. The bridge writes a small descriptive payload; the
// frontend, which owns the shape utils, knows how to turn that into a
// proper tldraw shape with the correct schema fields.
import {
  createShapeId,
  type Editor,
  type TLShapeId,
  type TLShapePartial,
} from 'tldraw'
import * as Y from 'yjs'

import type { ContributionNoteShape } from './shapes'

/** Payload shape that the Python bridge writes — must stay in sync
 *  with :class:`AgentContribution` in
 *  ``core/engine/canvas_bridge/bridge.py``. */
export interface AgentContributionPayload {
  id: string
  lens: string
  speaker: string
  accent: string
  framing: string
  inFlight?: boolean
  landedAt?: string
  thinkingAbout?: string
  x: number
  y: number
  w: number
  h: number
}

const SHAPE_ID_PREFIX = 'agent-'

function shapeIdForContribution(contributionId: string): TLShapeId {
  return createShapeId(`${SHAPE_ID_PREFIX}${contributionId}`)
}

function applyContribution(
  editor: Editor,
  payload: AgentContributionPayload,
): void {
  const shapeId = shapeIdForContribution(payload.id)
  const existing = editor.getShape(shapeId)

  const baseProps: ContributionNoteShape['props'] = {
    w: payload.w,
    h: payload.h,
    lens: payload.lens,
    speaker: payload.speaker,
    accent: payload.accent,
    framing: payload.framing,
    inFlight: payload.inFlight ?? false,
    landedAt: payload.landedAt,
    thinkingAbout: payload.thinkingAbout,
  }

  if (existing === undefined) {
    editor.createShape<ContributionNoteShape>({
      id: shapeId,
      type: 'contribution-note',
      x: payload.x,
      y: payload.y,
      props: baseProps,
    })
  } else {
    editor.updateShape<ContributionNoteShape>({
      id: shapeId,
      type: 'contribution-note',
      x: payload.x,
      y: payload.y,
      props: baseProps,
    } satisfies TLShapePartial<ContributionNoteShape>)
  }
}

function removeContribution(editor: Editor, contributionId: string): void {
  const shapeId = shapeIdForContribution(contributionId)
  if (editor.getShape(shapeId) !== undefined) {
    editor.deleteShape(shapeId)
  }
}

/** Subscribe the tldraw editor to the agent_contributions Y.Array.
 *
 *  On observation, reconcile the editor's agent-* shapes with the
 *  array's current contents:
 *    - entries in the array but not on the board → create
 *    - entries on the board but not in the array → delete
 *    - matching ids → update in place
 *
 *  Returns an unsubscribe fn.
 */
export function subscribeAgentContributions(
  editor: Editor,
  doc: Y.Doc,
): () => void {
  const contributions = doc.getArray<AgentContributionPayload>(
    'agent_contributions',
  )

  function reconcile(): void {
    const present = new Set<string>()
    for (const entry of contributions) {
      if (entry === null || entry === undefined) continue
      // Yjs Arrays can hold Y.Map-like objects when the Python side
      // writes a dict — pycrdt serializes those as plain JS objects.
      const payload = entry as AgentContributionPayload
      if (typeof payload.id !== 'string') continue
      present.add(payload.id)
      applyContribution(editor, payload)
    }

    // Remove any agent-* shapes whose contribution id is no longer in
    // the array (this lets the backend "clear" by emptying the array).
    const shapeIds = editor.getCurrentPageShapeIds()
    for (const shapeId of shapeIds) {
      if (!shapeId.startsWith(`shape:${SHAPE_ID_PREFIX}`)) continue
      const contribId = shapeId.slice(`shape:${SHAPE_ID_PREFIX}`.length)
      if (!present.has(contribId)) {
        removeContribution(editor, contribId)
      }
    }
  }

  // Initial reconcile (in case contributions exist before we subscribed).
  reconcile()

  const observer = () => reconcile()
  contributions.observe(observer)

  return () => contributions.unobserve(observer)
}
