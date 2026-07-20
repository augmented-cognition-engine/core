// core/ui/canvas/src/app/board/persistence.ts
//
// Local Yjs-backed persistence for the ACE board. Phase 2 of the
// canvas-path-c spec — Yjs is the substrate, IndexedDB is the local
// transport. Phase 3 will add a y-websocket provider on top of the
// same Y.Doc so the same persistence module gains realtime sync
// without the surface caring.
//
// Storage model (Phase 2):
//
//   Y.Doc
//     └─ Y.Map('board')
//          └─ 'tldraw-snapshot' → TLEditorSnapshot (full document snapshot)
//
// This is a "snapshot-in-a-map" pattern, not a structural CRDT binding
// of the tldraw store to Yjs. It's correct for single-user local
// persistence — last-write-wins is fine when only one client writes at
// a time. Phase 4+ may upgrade to a per-shape Y.Map binding if multi-
// writer conflict resolution becomes load-bearing; for two browser tabs
// of the same user (Phase 3 acceptance), snapshot-LWW already works.
//
// Module-level singleton: there's exactly one board per page, and we
// want HMR + React-18-strict-mode double-mount to share the same Y.Doc
// + IndexedDB connection. Page unload tears it down naturally.
import { IndexeddbPersistence } from 'y-indexeddb'
import { WebsocketProvider } from 'y-websocket'
import * as Y from 'yjs'

export interface BoardPersistence {
  doc: Y.Doc
  indexedDb: IndexeddbPersistence
  /** WebSocket provider for cross-client sync (Phase 3+).
   *  Null when sync is disabled (e.g. VITE_ACE_BOARD_WS=off). */
  websocket: WebsocketProvider | null
  /** Resolves once IndexedDB has loaded any stored state into the doc. */
  ready: Promise<void>
  /** Read the current snapshot from the Yjs map (or null if none). */
  loadSnapshot: () => unknown | null
  /** Write a snapshot into the Yjs map (triggers IndexedDB persist).
   *  Wrapped in a transaction tagged with our local origin so the
   *  remote-snapshot observer can filter our own writes back out. */
  saveSnapshot: (snapshot: unknown) => void
  /** Subscribe to snapshots written by *other* peers (origin !== local).
   *  Returns an unsubscribe fn. Local writes via ``saveSnapshot`` are
   *  filtered out, so applying the snapshot back to the editor won't
   *  oscillate. */
  onRemoteSnapshot: (cb: (snapshot: unknown) => void) => () => void
  /** Wipe local state — exposed for dev iteration via window.aceBoardReset. */
  clear: () => Promise<void>
}

/** Transaction origin tag for our own writes to the Y.Map. The remote
 *  snapshot observer compares against this to filter out echoes. */
export const LOCAL_ORIGIN = Symbol('ace-board-local-write')

// Bump the version suffix to invalidate stored state during dev when
// the fixture layout meaningfully changes. Phase 3+ will derive this
// from the URL or backend; for now it's a single shared room.
const ROOM = 'ace-board-v1'
const SNAPSHOT_KEY = 'tldraw-snapshot'

// Default WebSocket endpoint for the Yjs sync server. Resolves via
// ``VITE_ACE_BOARD_WS_URL`` if set; otherwise points at the FastAPI
// canvas endpoint behind Vite's dev proxy fallback (ws://localhost:8000).
// Set ``VITE_ACE_BOARD_WS=off`` to disable sync entirely (single-client
// mode — useful for tests).
function resolveWebsocketUrl(): string | null {
  const explicit = import.meta.env.VITE_ACE_BOARD_WS_URL
  if (explicit !== undefined && explicit !== '') {
    return String(explicit)
  }
  const flag = import.meta.env.VITE_ACE_BOARD_WS
  if (flag === 'off') return null
  // Default: same origin — Vite dev server proxies /canvas/* to the
  // FastAPI backend (see vite.config.ts), and prod serves the SPA from
  // the same host as the backend. Routing through the same origin
  // avoids cross-port CORS and keeps URLs portable.
  if (typeof window === 'undefined') return null
  const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProto}//${window.location.host}/canvas/ws`
}

let singleton: BoardPersistence | null = null

export function getBoardPersistence(): BoardPersistence {
  if (singleton !== null) return singleton

  const doc = new Y.Doc()
  const indexedDb = new IndexeddbPersistence(ROOM, doc)
  const boardMap = doc.getMap<unknown>('board')

  // Yjs sync: y-websocket attaches to the same Doc as IndexedDB. Updates
  // from peers come in as Y.applyUpdate calls, fire the doc's observers,
  // and IndexedDB persists them as a side effect. No additional plumbing.
  const wsUrl = resolveWebsocketUrl()
  let websocket: WebsocketProvider | null = null
  if (wsUrl !== null) {
    try {
      websocket = new WebsocketProvider(wsUrl, ROOM, doc, {
        // Connect right away. Reconnection backoff is built-in.
        connect: true,
      })
    } catch (err) {
      // Surface but don't crash — board still works locally.
      // eslint-disable-next-line no-console
      console.warn('[board] websocket sync disabled:', err)
      websocket = null
    }
  }

  // ``ready`` resolves when local cache is loaded. We don't await the
  // websocket sync — the board renders from the IndexedDB snapshot
  // immediately and the websocket merges its updates in as they arrive.
  const ready: Promise<void> = indexedDb.whenSynced.then(() => undefined)

  singleton = {
    doc,
    indexedDb,
    websocket,
    ready,
    loadSnapshot: () => {
      const value = boardMap.get(SNAPSHOT_KEY)
      return value ?? null
    },
    saveSnapshot: (snapshot) => {
      // Tag the transaction so the remote-snapshot observer can filter
      // our own write out (avoids local->remote->local echo loops).
      doc.transact(() => {
        boardMap.set(SNAPSHOT_KEY, snapshot)
      }, LOCAL_ORIGIN)
    },
    onRemoteSnapshot: (cb) => {
      const observer = (event: Y.YMapEvent<unknown>, txn: Y.Transaction) => {
        if (txn.origin === LOCAL_ORIGIN) return
        if (!event.changes.keys.has(SNAPSHOT_KEY)) return
        const snapshot = boardMap.get(SNAPSHOT_KEY)
        if (snapshot !== undefined) cb(snapshot)
      }
      boardMap.observe(observer)
      return () => boardMap.unobserve(observer)
    },
    clear: async () => {
      await indexedDb.clearData()
      doc.transact(() => boardMap.delete(SNAPSHOT_KEY), LOCAL_ORIGIN)
    },
  }

  // Dev escape hatch — wipe local state from the browser console.
  if (typeof window !== 'undefined') {
    ;(window as unknown as { aceBoardReset?: () => Promise<void> }).aceBoardReset =
      () => singleton!.clear().then(() => window.location.reload())
  }

  return singleton
}
