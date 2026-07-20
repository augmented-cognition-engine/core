// core/ui/canvas/src/app/CanvasSurface.tsx
//
// The collaborative workspace. NOT a single column of flowing prose
// (that read as an article). Instead: a 2-column layout where the
// partner's voice + attention moments live in the center, and the
// team's contributions live as pinned cards in the right rail.
//
// Layout:
//   ┌─────────────────────────────────────────────────────────────┐
//   │ Presence ribbon (full width)                                │
//   ├──────────────────────────────────┬──────────────────────────┤
//   │ PARTNER COLUMN (center)          │ TEAM RAIL (right)        │
//   │ - Brief-me-back lede             │ - Eyebrow: team · N of M │
//   │ - Attention callouts (live)      │ - Architecture card      │
//   │ - Convergence beat (when landed) │ - Security card          │
//   │                                  │ - Data card              │
//   │ "Where the user is being addressed" │ - UX card (live caret)   │
//   │                                  │ - Product Strategy (idle)│
//   └──────────────────────────────────┴──────────────────────────┘
//
// Voices have positions. The room is spatial, not linear.
import type { ReactNode } from 'react'

import { Aphorism, Card, Eyebrow } from '../design/components'
import { AttentionCallout } from './AttentionCallout'
import { BriefMeBack } from './BriefMeBack'
import { BoardSurface } from './board/BoardSurface'
import { ChatPanel } from './board/ChatPanel'
import { getBoardPersistence } from './board/persistence'
import { ClosingAsk } from './ClosingAsk'
import { CogArrow } from './CogArrow'
import { CogSection } from './CogSection'
import { ConvergenceBeat } from './ConvergenceBeat'
import { PresenceRibbon } from './PresenceRibbon'
import { TeamReadout } from './TeamReadout'
import type { BriefMeBackState, CanvasState } from './state'

interface CanvasSurfaceProps {
  state: CanvasState
  /** Optional brief-me-back surfaced from the parent so the workspace
   *  can integrate the lede into the partner column rather than
   *  rendering it above the workspace. */
  brief?: BriefMeBackState
}

export function CanvasSurface({ state, brief }: CanvasSurfaceProps) {
  const hasContributions =
    state.contributions !== undefined && state.contributions.length > 0
  const hasSections = state.sections.length > 0
  if (!state.inFlight || (!hasContributions && !hasSections)) {
    return <EmptyCanvas placeholder={state.placeholder} />
  }

  let nextIndex = 0
  const stageIndex = () => nextIndex++

  // Workspace mode — team has contributions, render 2-column layout.
  if (hasContributions) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--ace-space-4)' }}>
        {state.presence !== undefined && (
          <Staged index={stageIndex()}>
            <PresenceRibbon state={state.presence} />
          </Staged>
        )}

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 0.7fr) minmax(0, 1.5fr) 360px',
            gap: 'var(--ace-space-6)',
            alignItems: 'start',
          }}
        >
          {/* Center column — partner's voice + where the user is addressed */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--ace-space-5)',
              minWidth: 0,
            }}
          >
            {brief !== undefined && (
              <Staged index={stageIndex()}>
                <BriefMeBack state={brief} />
              </Staged>
            )}

            {state.readoutHeader !== undefined && (
              <Staged index={stageIndex()}>
                <div
                  style={{
                    fontFamily: 'var(--ace-font-sans)',
                    fontSize: 'var(--ace-text-xs)',
                    fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
                    letterSpacing: 'var(--ace-track-widest)',
                    textTransform: 'uppercase',
                    color: 'var(--ace-ink-muted)',
                  }}
                >
                  {state.readoutHeader}
                </div>
              </Staged>
            )}

            {state.attention !== undefined &&
              state.attention.length > 0 &&
              state.attention.map((req) => (
                <Staged key={req.id} index={stageIndex()}>
                  <AttentionCallout request={req} />
                </Staged>
              ))}

            {state.convergence !== undefined && (
              <Staged index={stageIndex()}>
                <ConvergenceBeat state={state.convergence} />
              </Staged>
            )}

            {state.closingAsk !== undefined && (
              <Staged index={stageIndex()}>
                <ClosingAsk state={state.closingAsk} />
              </Staged>
            )}
          </div>

          {/* Center — the 2D board. Voices live as positioned shapes
              on the tldraw canvas; agents drop notes via the canvas
              bridge (Phase 4). */}
          <Staged index={stageIndex()}>
            <BoardSurface
              contributions={state.contributions!}
              roster={state.presence?.participants}
            />
          </Staged>

          {/* Right — the conversation channel. Agents post attention
              requests + notes via the canvas bridge messages array;
              the user's reply goes back into the same Y.Array and the
              bridge routes it for follow-up action (Phase 5). */}
          <Staged index={stageIndex()}>
            <ChatPanel doc={getBoardPersistence().doc} />
          </Staged>
        </div>
      </div>
    )
  }

  // Legacy phase-driven mode (Frame → Diverge → Converge as CogSection stack).
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {state.presence !== undefined && (
        <Staged index={stageIndex()}>
          <PresenceRibbon state={state.presence} />
        </Staged>
      )}
      {state.sections.map((section, i) => {
        const next = state.sections[i + 1]
        return (
          <Staged key={section.id} index={stageIndex()}>
            <CogSection section={section} />
            {next !== undefined && section.arrowCaption !== undefined && (
              <CogArrow caption={section.arrowCaption} />
            )}
          </Staged>
        )
      })}
      {state.convergence !== undefined && (
        <Staged index={stageIndex()}>
          <ConvergenceBeat state={state.convergence} />
        </Staged>
      )}
      {state.closingAsk !== undefined && (
        <Staged index={stageIndex()}>
          <ClosingAsk state={state.closingAsk} />
        </Staged>
      )}
    </div>
  )
}

function Staged({ index, children }: { index: number; children: ReactNode }) {
  return (
    <div
      className="ace-stage-arrival"
      style={{ ['--cog-index' as string]: String(index) }}
    >
      {children}
    </div>
  )
}

function EmptyCanvas({ placeholder }: { placeholder?: ReactNode }) {
  return (
    <Card variant="default" padding="lg">
      <Eyebrow>The canvas is quiet</Eyebrow>
      <div style={{ marginTop: 'var(--ace-space-2)' }}>
        <Aphorism>
          {placeholder ??
            'No deliberation in flight. The partner is warm and listening — ask the team a question to start one.'}
        </Aphorism>
      </div>
    </Card>
  )
}

// TeamReadout is still exported via the module for parents that want
// the flowing-prose render; the default CanvasSurface no longer uses
// it. Suppress unused-import lint by re-exporting.
export { TeamReadout }
