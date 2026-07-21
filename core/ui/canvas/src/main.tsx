// core/ui/canvas/src/main.tsx
//
// ACE core entry point. Kernel routes:
//   /                          → redirect into Atrium
//   /atrium                    → Atrium (the canonical partner Canvas)
//   /room                      → legacy alias for Atrium
//   /deliberation              → DeliberationCanvas (the live committee)
//   /landscape                 → ProductMap (read-only Living Product Graph)
//   /showcase                  → V14Showcase (chrome reference)
//   ?mode=showcase             → DesignSystemShowcase (dev reference)
//
// Extension routes mount AFTER the kernel routes, discovered through
// the ext seam (src/app/ext/registry.tsx) — the kernel never names an
// extension path. With no extensions present the canvas runs with the
// routes above only.
//
// AcknowledgmentProvider wraps the whole tree so any surface can fire
// acknowledgments via useAcknowledgment().
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { Workroom } from './app/Workroom'
import { DeliberationCanvas } from './app/DeliberationCanvas'
import { LiveBrain } from './app/LiveBrain'
import { ProductMap } from './app/ProductMap'
import { extensionRoutes } from './app/ext/registry'
import { AceContextProvider } from './app/journey/aceContext'
import { AcknowledgmentProvider, TooltipProvider } from './design/components'
import { DesignSystemShowcase } from './design/showcase/DesignSystemShowcase'
import { V14Showcase } from './app/showcase/V14Showcase'
import './index.css'
// Legacy --ace-* token definitions used by canvas surfaces that still
// inline `style={{ ... var(--ace-X) ... }}`. tokens.css is namespaced
// (only defines --ace-*) and does not conflict with the canonical preset.
import './design/tokens.css'

const params = new URLSearchParams(window.location.search)
const isShowcase = params.get('mode') === 'showcase'

function Root() {
  if (isShowcase) return <DesignSystemShowcase />
  return (
    <TooltipProvider>
      <AcknowledgmentProvider>
        <BrowserRouter>
          <AceContextProvider>
          <Routes>
            {/* Atrium lives at a named URL so the address bar reflects
                the surface; `/` just redirects in. */}
            <Route path="/" element={<Navigate to="/atrium" replace />} />
            {/* Atrium — the one canonical partnership Canvas. DeliberationCanvas
                renders warm when idle (the room is never cold on arrival) and goes
                live when you pose a question (?topic → useOrchestrationSession →
                POST /canvas/sessions → orchestration WS). The old separate
                /deliberation surface is collapsed into Atrium. */}
            <Route path="/atrium" element={<DeliberationCanvas />} />
            {/* Legacy alias retained for existing extension and session links. */}
            <Route path="/room" element={<DeliberationCanvas />} />
            {/* Legacy alias for existing ?topic / ?session deep-links — the same
                canonical surface, so the committee never has two homes. */}
            <Route path="/deliberation" element={<DeliberationCanvas />} />
            {/* The multiplayer workroom — the 2D tldraw board with voices as
                positioned shapes + the Yjs chat channel. Previously only
                reachable as App's no-journey fallback (never triggered, since
                the fixture always sets journey); now a first-class surface.
                Named /board for the same /canvas-proxy reason above. */}
            <Route path="/board" element={<Workroom />} />
            {/* The brain, visualized — REAL substrate output (beliefs re-derived
                when their canvas ground shifts). First live slice; snapshot transport. */}
            <Route path="/brain" element={<LiveBrain />} />
            {/* Read-only operator view over the bounded G1 Living Product Graph.
                This route exposes no write, execution, extension, or model authority. */}
            <Route path="/landscape" element={<ProductMap />} />
            <Route path="/showcase" element={<V14Showcase />} />
            {/* Extension-contributed routes (pages, legacy aliases). */}
            {extensionRoutes().map((r) => (
              <Route key={r.path} path={r.path} element={r.element} />
            ))}
            {/* Anything else falls back to the canvas. */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </AceContextProvider>
        </BrowserRouter>
      </AcknowledgmentProvider>
    </TooltipProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
