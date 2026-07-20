// core/ui/canvas/src/app/ProactivePanel.tsx
//
// Four background-activity surfaces, rendered after the deliberation
// to show that ACE keeps working even when the user isn't asking
// anything. Per the partnership thesis: the partner is always running,
// and these surfaces are how that becomes visible.
//
//   - SentinelFinding   (L8 — drift / contradiction / missed handoff)
//   - NewMemoryCard     (L7 — pattern captured from this turn's outcome)
//   - PatternEmerge     (L7 — cross-deliberation pattern)
//   - CalibrationSpark  (L9 — prediction track record)
import { Card, Eyebrow, Pip, Sparkline } from '../design/components'
import type {
  CalibrationSparkState,
  NewMemoryState,
  PatternEmergeState,
  ProactivePanelState,
  SentinelFindingState,
} from './state'

interface ProactivePanelProps {
  state: ProactivePanelState
}

export function ProactivePanel({ state }: ProactivePanelProps) {
  const hasAny =
    state.sentinel !== undefined ||
    state.newMemory !== undefined ||
    state.patternEmerge !== undefined ||
    state.calibration !== undefined
  if (!hasAny) return null

  return (
    <section
      style={{
        marginTop: 'var(--ace-space-8)',
        paddingTop: 'var(--ace-space-4)',
        borderTop: '1px solid var(--ace-line-soft)',
      }}
    >
      <div style={{ marginBottom: 'var(--ace-space-3)' }}>
        <Eyebrow>Background activity · what the partner has been working on</Eyebrow>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 'var(--ace-space-3)',
          alignItems: 'start',
        }}
      >
        {state.sentinel !== undefined && <SentinelFinding state={state.sentinel} />}
        {state.newMemory !== undefined && <NewMemoryCard state={state.newMemory} />}
        {state.patternEmerge !== undefined && (
          <PatternEmerge state={state.patternEmerge} />
        )}
      </div>

      {state.calibration !== undefined && (
        <div style={{ marginTop: 'var(--ace-space-3)' }}>
          <CalibrationSpark state={state.calibration} />
        </div>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// SentinelFinding — L8
// ---------------------------------------------------------------------------

function SentinelFinding({ state }: { state: SentinelFindingState }) {
  const tone =
    state.severity === 'high'
      ? 'var(--ace-warning)'
      : state.severity === 'medium'
        ? 'var(--ace-tone-medium)'
        : 'var(--ace-success)'
  return (
    <Card variant="default" padding="md">
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--ace-space-2)',
          marginBottom: 'var(--ace-space-2)',
        }}
      >
        <Pip tone={tone} size="xs" />
        <Eyebrow tone={tone}>sentinel · noticed</Eyebrow>
      </div>
      <BodyText>{state.headline}</BodyText>
      <Foot>runs continuously · last sweep {state.noticedAt}</Foot>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// NewMemoryCard — L7 capture
// ---------------------------------------------------------------------------

function NewMemoryCard({ state }: { state: NewMemoryState }) {
  return (
    <Card variant="default" padding="md">
      <Eyebrow>✦ new memory · captured</Eyebrow>
      <BodyText>{state.pattern}</BodyText>
      <Foot>{state.provenance}</Foot>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// PatternEmerge — L7 cross-deliberation pattern
// ---------------------------------------------------------------------------

function PatternEmerge({ state }: { state: PatternEmergeState }) {
  return (
    <Card variant="default" padding="md">
      <Eyebrow>⌖ noticed · L7 pattern emergence</Eyebrow>
      <BodyText>{state.observation}</BodyText>
      <Foot>{state.provenance}</Foot>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// CalibrationSpark — L9 prediction track record
// ---------------------------------------------------------------------------

function CalibrationSpark({ state }: { state: CalibrationSparkState }) {
  const n = state.values.length
  return (
    <Card variant="default" padding="md">
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 'var(--ace-space-3)',
          marginBottom: 'var(--ace-space-2)',
        }}
      >
        <Eyebrow>Calibration · the partner's prediction track record</Eyebrow>
        <span style={{ flex: '1 1 auto' }} />
        <span
          style={{
            fontFamily: 'var(--ace-font-mono)',
            fontVariantNumeric: 'tabular-nums',
            fontWeight: 'var(--ace-weight-bold)' as unknown as number,
            color: 'var(--ace-ink)',
            fontSize: 'var(--ace-text-lg)',
          }}
        >
          {state.average.toFixed(2)}
        </span>
        <span style={{ fontSize: 'var(--ace-text-xs)', color: 'var(--ace-ink-muted)' }}>
          n = {n}
        </span>
      </div>

      <Sparkline values={state.values} ariaLabel="calibration history" />

      {state.note !== undefined && (
        <div
          style={{
            marginTop: 'var(--ace-space-2)',
            fontSize: 'var(--ace-text-sm)',
            color: 'var(--ace-ink-muted)',
            lineHeight: 'var(--ace-leading-normal)',
            fontFamily: 'var(--ace-font-serif)',
            fontStyle: 'italic',
          }}
        >
          {state.note}
        </div>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Small presentational helpers — only used in this file.
// ---------------------------------------------------------------------------

function BodyText({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        marginTop: 'var(--ace-space-2)',
        fontSize: 'var(--ace-text-md)',
        color: 'var(--ace-ink-soft)',
        lineHeight: 'var(--ace-leading-normal)',
        fontFamily: 'var(--ace-font-serif)',
      }}
    >
      {children}
    </div>
  )
}

function Foot({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        marginTop: 'var(--ace-space-2)',
        paddingTop: 'var(--ace-space-1)',
        borderTop: '1px solid var(--ace-line-soft)',
        fontSize: 'var(--ace-text-xs)',
        color: 'var(--ace-ink-muted)',
        lineHeight: 'var(--ace-leading-normal)',
      }}
    >
      {children}
    </div>
  )
}
