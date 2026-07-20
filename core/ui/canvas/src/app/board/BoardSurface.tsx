// core/ui/canvas/src/app/board/BoardSurface.tsx
//
// The 2D board. tldraw canvas with custom shape utils for contribution
// notes and ghosted placeholders. Phase 1: fixture-driven, no sync.
//
// Layout strategy: lenses are positioned in a loose scatter — three
// across the top (architecture / security / data), two below
// (ux / product_strategy). Architecture's note connects to Data's via
// a tldraw arrow tinted with Architecture's lens accent. The scatter is
// deterministic so the board looks the same on reload; later phases
// will move positions into the Yjs doc so they persist across users.
//
// Chrome: hideUi={true} — no toolbar, no style panel, no main menu, no
// page menu. Pan + zoom + select still work. This is "canvas-only mode"
// per the spec.
import { useCallback } from 'react'
import {
  createShapeId,
  type Editor,
  getSnapshot,
  loadSnapshot,
  Tldraw,
  type TLArrowShape,
  type TLShapePartial,
} from 'tldraw'
import 'tldraw/tldraw.css'

import type { ContributionState, PresenceParticipant } from '../state'
import { subscribeAgentContributions } from './agentSubscription'
import { ContributionNoteShapeUtil } from './ContributionNoteShape'
import { ContributionPlaceholderShapeUtil } from './ContributionPlaceholderShape'
import { getBoardPersistence } from './persistence'
import type {
  ContributionNoteShape,
  ContributionPlaceholderShape,
} from './shapes'

import './board.css'

interface BoardSurfaceProps {
  contributions: ContributionState[]
  /** Roster from presence — used to render ghosted lanes for voices
   *  that haven't fired yet (e.g. product_strategy at 'not yet'). */
  roster?: PresenceParticipant[]
}

// Layout: three across the top, two below. Positions are deterministic
// so the board looks the same on every load. Phase 2 moves these into
// the Yjs doc so a user-dragged position persists.
const LAYOUT: Record<string, { x: number; y: number; w: number; h: number }> = {
  architecture:     { x:  60, y:  60, w: 280, h: 200 },
  security:         { x: 380, y: 100, w: 280, h: 200 },
  data:             { x: 700, y:  60, w: 280, h: 200 },
  ux:               { x: 220, y: 360, w: 280, h: 240 },
  product_strategy: { x: 540, y: 380, w: 280, h: 160 },
}

const FALLBACK_LAYOUT = { x: 0, y: 0, w: 280, h: 200 }

const customShapeUtils = [
  ContributionNoteShapeUtil,
  ContributionPlaceholderShapeUtil,
]

export function BoardSurface({ contributions, roster }: BoardSurfaceProps) {
  const handleMount = useCallback(
    (editor: Editor) => {
      if (import.meta.env.DEV) {
        ;(window as unknown as { __aceEditor?: Editor }).__aceEditor = editor
      }
      void hydrateAndBind(editor, contributions, roster ?? [])
    },
    [contributions, roster],
  )

  return (
    <div className="ace-board" aria-label="Team board">
      <Tldraw
        shapeUtils={customShapeUtils}
        hideUi
        onMount={handleMount}
        autoFocus={false}
      />
    </div>
  )
}

// ── Persistence wiring ────────────────────────────────────────────────
//
// On mount we (1) wait for IndexedDB to load any stored Yjs state into
// the doc; (2) either restore the snapshot or seed from fixtures; (3)
// listen for user-initiated store changes and persist them back (rAF-
// batched so a drag doesn't write 60×/sec).
//
// The seed path also writes the initial snapshot immediately so a
// first-run reload restores the layout instead of re-seeding (which
// would clobber any drag the user made before the first persist).

async function hydrateAndBind(
  editor: Editor,
  contributions: ContributionState[],
  roster: PresenceParticipant[],
) {
  const persistence = getBoardPersistence()
  await persistence.ready

  const snapshot = persistence.loadSnapshot()
  if (snapshot !== null) {
    loadSnapshot(editor.store, snapshot as Parameters<typeof loadSnapshot>[1])
    editor.zoomToFit({ animation: { duration: 0 } })
  } else {
    seedBoard(editor, contributions, roster)
    persistence.saveSnapshot(getSnapshot(editor.store))
  }

  // Persist document changes, rAF-batched so a drag doesn't write per
  // pixel. No source filter — Phase 4 will land agent-driven changes
  // that come in as `'remote'` source and still need to persist.
  let pendingFrame: number | null = null
  // When applying a peer snapshot we don't want the resulting tldraw
  // store mutations to immediately echo back as a saveSnapshot (which
  // would write essentially the same bytes back into the Y.Map and
  // burn a network round-trip for nothing). suspendPersistUntil holds
  // the listener off for one frame after a remote apply.
  let suspendPersist = false

  editor.store.listen(
    () => {
      if (suspendPersist) return
      if (pendingFrame !== null) return
      pendingFrame = requestAnimationFrame(() => {
        pendingFrame = null
        persistence.saveSnapshot(getSnapshot(editor.store))
      })
    },
    { scope: 'document' },
  )

  // Subscribe to remote peer writes — when another tab or an agent
  // (Phase 4+) writes a new snapshot to the Y.Map, apply it to the
  // local tldraw store. LOCAL_ORIGIN filtering inside persistence
  // prevents our own writes from echoing back through this path.
  persistence.onRemoteSnapshot((snapshot) => {
    suspendPersist = true
    try {
      loadSnapshot(editor.store, snapshot as Parameters<typeof loadSnapshot>[1])
    } finally {
      // Release on the next frame so the cascading store events fire
      // first (and are skipped), then normal persist resumes.
      requestAnimationFrame(() => {
        suspendPersist = false
      })
    }
  })

  // Agent participant bridge — materialize entries from the
  // agent_contributions Y.Array into tldraw shapes. Bridge writes
  // come in as ordinary store mutations and persist through the
  // normal save listener above.
  subscribeAgentContributions(editor, persistence.doc)
}

// ── Board seeding ─────────────────────────────────────────────────────
//
// On mount, walk the roster and contributions to populate the board with
// one shape per voice (note for landed/in-flight, placeholder for not-
// yet). Then add an arrow from architecture's note to data's note so
// the spatial relationship is visible. After seeding, frame the bounds
// so the board opens with the team in view.

function seedBoard(
  editor: Editor,
  contributions: ContributionState[],
  roster: PresenceParticipant[],
) {
  // Skip seeding if the board already has shapes (e.g. HMR re-mount).
  if (editor.getCurrentPageShapeIds().size > 0) {
    editor.zoomToFit({ animation: { duration: 0 } })
    return
  }

  const byLens = new Map(contributions.map((c) => [c.lens, c]))

  // The roster includes user + partner — filter to voices only. If
  // roster is empty, fall back to the contributions themselves.
  const rosterVoices = roster.filter(
    (p) => p.isUser !== true && p.isPartner !== true,
  )
  const voiceList: Array<{
    lens: string
    speaker: string
    accent: string
    hint?: string
  }> =
    rosterVoices.length > 0
      ? rosterVoices.map((v) => ({
          lens: v.id,
          speaker: v.name,
          accent: v.accent,
          hint: v.lastAt ?? 'not yet',
        }))
      : contributions.map((c) => ({
          lens: c.lens,
          speaker: c.speaker,
          accent: c.accent,
        }))

  const shapesToCreate: TLShapePartial[] = []
  const shapeIdByLens = new Map<string, ReturnType<typeof createShapeId>>()

  for (const voice of voiceList) {
    const layout = LAYOUT[voice.lens] ?? FALLBACK_LAYOUT
    const contribution = byLens.get(voice.lens)

    if (contribution !== undefined) {
      const id = createShapeId(`contribution-${voice.lens}`)
      shapeIdByLens.set(voice.lens, id)
      shapesToCreate.push({
        id,
        type: 'contribution-note',
        x: layout.x,
        y: layout.y,
        props: {
          w: layout.w,
          h: layout.h,
          lens: contribution.lens,
          speaker: contribution.speaker,
          accent: contribution.accent,
          framing: contribution.framing,
          landedAt: contribution.landedAt,
          inFlight: contribution.inFlight,
          thinkingAbout: contribution.thinkingAbout,
        },
      } satisfies TLShapePartial<ContributionNoteShape>)
    } else {
      const id = createShapeId(`placeholder-${voice.lens}`)
      shapeIdByLens.set(voice.lens, id)
      shapesToCreate.push({
        id,
        type: 'contribution-placeholder',
        x: layout.x,
        y: layout.y,
        props: {
          w: layout.w,
          h: layout.h,
          lens: voice.lens,
          speaker: voice.speaker,
          accent: voice.accent,
          hint: voice.hint ?? 'not yet',
        },
      } satisfies TLShapePartial<ContributionPlaceholderShape>)
    }
  }

  editor.createShapes(shapesToCreate)

  // Architecture → Data arrow, tinted with Architecture's accent (spec §4.1).
  // tldraw's built-in arrow uses its own color enum; we use 'grey' as the
  // closest neutral and rely on the engineered-light theme overrides to
  // soften it. (A future phase can bind the arrow color to the source
  // lens accent via tldraw bindings.)
  const archId = shapeIdByLens.get('architecture')
  const dataId = shapeIdByLens.get('data')
  if (archId !== undefined && dataId !== undefined) {
    const archLayout = LAYOUT.architecture
    const dataLayout = LAYOUT.data
    const arrowId = createShapeId('arrow-architecture-data')
    editor.createShape<TLArrowShape>({
      id: arrowId,
      type: 'arrow',
      x: archLayout.x + archLayout.w,
      y: archLayout.y + archLayout.h / 2,
      props: {
        start: { x: 0, y: 0 },
        end: {
          x: dataLayout.x - (archLayout.x + archLayout.w),
          y: dataLayout.y + dataLayout.h / 2 - (archLayout.y + archLayout.h / 2),
        },
        bend: -80,
        color: 'grey',
        size: 'm',
        arrowheadEnd: 'arrow',
        arrowheadStart: 'none',
      },
    })
  }

  // Frame the team. Small padding so the cards have visual breathing room.
  editor.zoomToFit({ animation: { duration: 0 } })
}
