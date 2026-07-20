// core/ui/canvas/src/app/Workroom.tsx
//
// Workroom — the /board surface: the 2D board (voices as positioned shapes +
// a Yjs-backed chat channel) with topbar, vision, working panel, and footer.
// Reads from useAceCoreState (fixture-populated so first render is never cold).
//
// The old App() journey layout that used to sit at /room was retired when the
// committee surfaces collapsed into the one canonical Room (DeliberationCanvas
// at /room, warm-when-idle + live-when-you-ask). The DeliberationJourneyState
// type it projected lives on in types/canvas.ts and is still what the live
// orchestration reducer produces.
import { TooltipProvider } from '../design/components'
import { Footer } from './Footer'
import { Main } from './Main'
import { Topbar } from './Topbar'
import { useAceCoreState } from './useAceCoreState'

/** The multiplayer workroom — topbar + vision + the 2D board (voices as
 *  positioned shapes, Yjs-backed chat) + working panel + footer. Mounted at
 *  /board so the living board is a reachable, first-class surface. */
export function Workroom() {
  const state = useAceCoreState()
  return (
    <TooltipProvider>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
          background: 'var(--ace-surface-canvas)',
          color: 'var(--ace-ink)',
          overflow: 'hidden',
        }}
      >
        <Topbar state={state.topbar} />
        <Main
          vision={state.vision}
          briefMeBack={state.briefMeBack}
          canvas={state.canvas}
          composition={state.composition}
          sessionId={state.sessionId}
        />
        <Footer state={state.footer} />
      </div>
    </TooltipProvider>
  )
}
