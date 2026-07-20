// core/ui/canvas/src/app/Main.tsx
//
// The app-canvas region. Full-width workspace layout — the CanvasSurface
// internally splits into a partner-column + team-rail when the
// deliberation is multi-voice. Brief-me-back is folded into the partner
// column inside CanvasSurface, so there's no separate left-narrative /
// right-rail at this level.
//
// Vision anchor stays full-width above everything because the
// north-star frames every turn.
import { CompositionLens } from '../design/components/CompositionLens'
import type { CompositionSelectedPayload } from '../types/canvas'
import { CanvasSurface } from './CanvasSurface'
import { ReconciliationBanner } from './ReconciliationBanner'
import { VisionAnchor } from './VisionAnchor'
import { outcomeToBannerState, usePredictionOutcomes } from './usePredictionOutcomes'
import type {
  BriefMeBackState,
  CanvasState,
  VisionAnchorState,
} from './state'

interface MainProps {
  vision: VisionAnchorState
  briefMeBack: BriefMeBackState
  canvas: CanvasState
  composition?: CompositionSelectedPayload | null
  /** Active canvas session id — when set, the reconciliation banner follows
   *  live prediction.outcome.closed events instead of fixture state. */
  sessionId?: string | null
}

export function Main({ vision, briefMeBack, canvas, composition, sessionId }: MainProps) {
  // L9 lifecycle — when the reconciler closes a prediction for this session,
  // the close lands here and overrides the (fixture-fed) banner so the loop
  // closes visibly on the canvas.
  const { outcomes } = usePredictionOutcomes(sessionId)
  const latestOutcome = outcomes.length > 0 ? outcomes[outcomes.length - 1] : null
  const banner = latestOutcome !== null ? outcomeToBannerState(latestOutcome) : canvas.banner

  return (
    <div
      style={{
        flex: '1 1 auto',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--ace-surface-canvas)',
        overflow: 'auto',
        fontFamily: 'var(--ace-font-sans)',
      }}
    >
      {/* Reconciliation banner — top-of-canvas, when a prediction
          window is closing (live outcome wins over fixture state). */}
      {banner !== undefined && (
        <ReconciliationBanner state={banner} />
      )}

      {/* Full-width vision anchor band */}
      <VisionAnchor state={vision} />

      {/* Composition lens — the orchestra view. Renders the meta-skills
          self-nominating for the current task (L3 visibility). When no
          composition is in flight, the lens renders its own quiet empty
          state. Lives above the canvas surface so the user sees what's
          weighing in before the deliberation itself. */}
      {composition !== undefined && (
        <div style={{ padding: 'var(--ace-space-4) var(--ace-space-8) 0' }}>
          <CompositionLens payload={composition} />
        </div>
      )}

      {/* The workspace — partner column + team rail live inside */}
      <div
        style={{
          flex: '1 1 auto',
          padding: 'var(--ace-space-6) var(--ace-space-8)',
          minWidth: 0,
        }}
      >
        <CanvasSurface state={canvas} brief={briefMeBack} />
      </div>
    </div>
  )
}
