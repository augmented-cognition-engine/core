// core/ui/canvas/src/app/Topbar.tsx
//
// The full app-topbar from multiplayer.html, composed from design-system
// primitives. Reads from state.topbar — every value flows in as data,
// nothing is hardcoded.
//
// Layout (left → right):
//   ACE / reasoning OS                  (title block)
//   $0.024 · 142k tokens · this turn    (cost ticker — inline)
//   ⌖─◯─◇─◆─◇─◆                          (progress strip)
//   ◇ recipe deep_committee · Opus      (recipe chip)
//   ◉ 5 archetypes                       (roster row — discipline avatars)
//   ◉ sentinels · 4 findings             (sentinel chip)
//   7 memory                             (memory chip)
//                                  WARM  (warmth indicator)
import { Chip, Dialog, Pip, RosterRow, SeverityFinding, Tooltip } from '../design/components'
import type {
  CostTickerState,
  MemoryChipState,
  ProgressPhase,
  RecipeChipState,
  RosterMember,
  SentinelChipState,
  TopbarState,
} from './state'

interface TopbarProps {
  state: TopbarState
}

export function Topbar({ state }: TopbarProps) {
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--ace-space-4)',
        padding: 'var(--ace-space-2) var(--ace-space-6)',
        background: 'var(--ace-surface-canvas)',
        borderBottom: '1px solid var(--ace-line-soft)',
        fontFamily: 'var(--ace-font-sans)',
        flex: '0 0 auto',
        minHeight: 48,
      }}
    >
      {/* Title block — ACE / reasoning OS */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--ace-space-2)' }}>
        <span
          style={{
            fontFamily: 'var(--ace-font-serif)',
            fontSize: 'var(--ace-text-xl)',
            color: 'var(--ace-ink)',
            fontWeight: 'var(--ace-weight-medium)' as unknown as number,
            letterSpacing: 'var(--ace-track-tight)',
          }}
        >
          {state.title}
        </span>
        <span
          style={{
            fontSize: 'var(--ace-text-sm)',
            color: 'var(--ace-ink-muted)',
            fontFamily: 'var(--ace-font-serif)',
            fontStyle: 'italic',
          }}
        >
          {state.subtitle}
        </span>
      </div>

      <Divider />

      {/* Cost ticker — honest readout of resource use */}
      <CostTicker state={state.cost} />

      <Divider />

      {/* Progress strip — phases of the current chain */}
      <ProgressStrip phases={state.phases} />

      <Divider />

      {/* Recipe chip — which cognitive chain the partner picked */}
      <RecipeChip state={state.recipe} />

      <Divider />

      {/* Roster — discipline avatars of the team in the room */}
      <RosterStrip members={state.roster} />

      <Divider />

      {/* Sentinel chip — L8 background activity */}
      <SentinelChip state={state.sentinel} />

      {/* Memory chip — what ACE has captured about how you think */}
      <MemoryChip state={state.memory} />

      <span style={{ flex: '1 1 auto' }} />

      {/* Warmth indicator — partner-never-asks: the alternative isn't off */}
      <Tooltip
        content="The partner is always running. Warm = ambient, not waiting to be initiated."
      >
        <span
          style={{
            fontSize: 'var(--ace-text-xs)',
            fontWeight: 'var(--ace-weight-bold)' as unknown as number,
            letterSpacing: 'var(--ace-track-wide)',
            textTransform: 'uppercase',
            color: 'var(--ace-voice-accent)',
            padding: '2px var(--ace-space-2)',
            borderRadius: 'var(--ace-radius-sm)',
            background:
              'color-mix(in oklab, var(--ace-voice-accent) 12%, transparent)',
            border:
              '1px solid color-mix(in oklab, var(--ace-voice-accent) 32%, transparent)',
            fontFamily: 'var(--ace-font-sans)',
            cursor: 'default',
          }}
        >
          {state.warmthLabel}
        </span>
      </Tooltip>
    </header>
  )
}

// ---------------------------------------------------------------------------
// Internal topbar components — each takes state, no hardcoded values.
// ---------------------------------------------------------------------------

function Divider() {
  return (
    <span
      aria-hidden
      style={{
        width: 1,
        height: 20,
        background: 'var(--ace-line-soft)',
        flex: '0 0 auto',
      }}
    />
  )
}

function CostTicker({ state }: { state: CostTickerState }) {
  const tokensK = (state.tokensUsed / 1000).toFixed(1)
  return (
    <Tooltip content="Honest readout of this turn's compute. Tokens + dollars used by the committee so far.">
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'baseline',
          gap: 'var(--ace-space-2)',
          fontSize: 'var(--ace-text-sm)',
          color: 'var(--ace-ink-soft)',
          fontFamily: 'var(--ace-font-mono)',
          fontVariantNumeric: 'tabular-nums',
          cursor: 'default',
        }}
      >
        <b style={{ color: 'var(--ace-ink)', fontWeight: 'var(--ace-weight-semibold)' as unknown as number }}>
          ${state.costUsd.toFixed(3)}
        </b>
        <span style={{ color: 'var(--ace-ink-muted)' }}>·</span>
        <b style={{ color: 'var(--ace-ink)', fontWeight: 'var(--ace-weight-semibold)' as unknown as number }}>
          {tokensK}k
        </b>
        <span style={{ color: 'var(--ace-ink-muted)' }}>tokens</span>
        <span style={{ color: 'var(--ace-ink-muted)' }}>·</span>
        <span style={{ color: 'var(--ace-ink-muted)', fontStyle: 'italic', fontFamily: 'var(--ace-font-serif)' }}>
          {state.scope}
        </span>
      </span>
    </Tooltip>
  )
}

const PHASE_GLYPHS: Record<string, string> = {
  prep: '⌖',
  frame: '◯',
  prioritize: '◉',
  diverge: '◇',
  converge: '◆',
  synthesize: '✦',
  refine: '◐',
  evaluate: '◑',
}

function phaseGlyph(id: string, label: string): string {
  return PHASE_GLYPHS[id.toLowerCase()] ?? PHASE_GLYPHS[label.toLowerCase()] ?? '◦'
}

function ProgressStrip({ phases }: { phases: ProgressPhase[] }) {
  return (
    <div
      role="list"
      aria-label="cognitive chain progress"
      style={{ display: 'flex', alignItems: 'center', gap: 6 }}
    >
      {phases.map((p, i) => {
        const isDone = p.status === 'done'
        const isActive = p.status === 'active'
        return (
          <span key={p.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Tooltip content={`${p.label} — ${p.status}`}>
              <span
                role="listitem"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 20,
                  height: 20,
                  fontSize: 'var(--ace-text-sm)',
                  color: isDone
                    ? 'var(--ace-success)'
                    : isActive
                      ? 'var(--ace-voice-accent)'
                      : 'var(--ace-line-strong)',
                  opacity: isDone || isActive ? 1 : 0.45,
                  fontFamily: 'var(--ace-font-sans)',
                  cursor: 'default',
                  transition: 'color var(--ace-motion-snap) var(--ace-ease-snap), opacity var(--ace-motion-snap) var(--ace-ease-snap)',
                }}
              >
                {phaseGlyph(p.id, p.label)}
              </span>
            </Tooltip>
            {i < phases.length - 1 && (
              <span
                aria-hidden
                style={{
                  width: 12,
                  height: 1,
                  background:
                    phases[i + 1].status !== 'future'
                      ? 'var(--ace-line-strong)'
                      : 'var(--ace-line-soft)',
                }}
              />
            )}
          </span>
        )
      })}
    </div>
  )
}

function RecipeChip({ state }: { state: RecipeChipState }) {
  return (
    <Tooltip content="The cognitive chain ACE composed for this problem. Click to see alternatives + why this one won.">
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--ace-space-1)' }}>
        <Chip variant="subtle">
          <span style={{ color: 'var(--ace-voice-accent)', marginRight: 4 }}>◇</span>
          <span style={{ color: 'var(--ace-ink-muted)' }}>recipe</span>
          <code
            style={{
              fontFamily: 'var(--ace-font-mono)',
              fontSize: 'var(--ace-text-sm)',
              color: 'var(--ace-ink)',
              fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
              marginLeft: 4,
            }}
          >
            {state.name}
          </code>
          {state.modelHint !== undefined && (
            <>
              <span style={{ color: 'var(--ace-ink-muted)', margin: '0 4px' }}>·</span>
              <span style={{ color: 'var(--ace-ink-muted)', fontStyle: 'italic' }}>
                {state.modelHint}
              </span>
            </>
          )}
        </Chip>
      </span>
    </Tooltip>
  )
}

function RosterStrip({ members }: { members: RosterMember[] }) {
  return (
    <Tooltip content={`The team in the room: ${members.map((m) => m.lens).join(' · ')}`}>
      <span style={{ display: 'inline-flex', cursor: 'default' }}>
        <RosterRow lenses={members.map((m) => m.lens)} size="sm" />
      </span>
    </Tooltip>
  )
}

function SentinelChip({ state }: { state: SentinelChipState }) {
  const severityColor =
    state.topSeverity === 'high'
      ? 'var(--ace-warning)'
      : state.topSeverity === 'medium'
        ? 'var(--ace-tone-medium)'
        : state.topSeverity === 'low'
          ? 'var(--ace-success)'
          : 'var(--ace-ink-muted)'

  const chip = (
    <Chip variant="subtle" onClick={() => {}}>
      <Pip tone={severityColor} size="xs" />
      <span style={{ color: 'var(--ace-ink-muted)', marginLeft: 4 }}>sentinels</span>
      {state.findingCount > 0 && (
        <>
          <span style={{ color: 'var(--ace-ink-muted)', margin: '0 4px' }}>·</span>
          <span
            style={{
              color: severityColor,
              fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
              fontVariantNumeric: 'tabular-nums',
              fontFamily: 'var(--ace-font-mono)',
            }}
          >
            {state.findingCount}
          </span>
          <span style={{ color: 'var(--ace-ink-muted)', marginLeft: 3 }}>
            {state.findingCount === 1 ? 'finding' : 'findings'}
          </span>
        </>
      )}
    </Chip>
  )

  // If there are no findings to drill into, render the chip alone with a tooltip.
  if (state.findings === undefined || state.findings.length === 0) {
    return (
      <Tooltip content="L8 sentinel layer — runs continuously.">
        <span style={{ display: 'inline-flex', alignItems: 'center', cursor: 'default' }}>
          {chip}
        </span>
      </Tooltip>
    )
  }

  // Otherwise, the chip opens a Dialog with the findings drawer.
  return (
    <Dialog
      trigger={
        <span style={{ display: 'inline-flex', alignItems: 'center', cursor: 'pointer' }}>
          {chip}
        </span>
      }
      title="L8 Sentinel layer"
      description={`${state.engineCount ?? state.findings.length} engines · running 24/7${
        state.lastSweep !== undefined ? ` · last sweep ${state.lastSweep}` : ''
      }`}
      width={520}
    >
      <SentinelDrawer findings={state.findings} />
    </Dialog>
  )
}

function SentinelDrawer({ findings }: { findings: NonNullable<SentinelChipState['findings']> }) {
  const grouped = new Map<string, typeof findings>()
  for (const f of findings) {
    const list = grouped.get(f.category) ?? []
    list.push(f)
    grouped.set(f.category, list)
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--ace-space-4)' }}>
      {[...grouped.entries()].map(([category, items]) => (
        <div key={category}>
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 'var(--ace-space-2)',
              marginBottom: 'var(--ace-space-2)',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--ace-font-serif)',
                fontSize: 'var(--ace-text-md)',
                fontWeight: 'var(--ace-weight-medium)' as unknown as number,
                color: 'var(--ace-ink)',
              }}
            >
              {category}
            </span>
            <span style={{ color: 'var(--ace-ink-muted)', fontSize: 'var(--ace-text-xs)' }}>
              {items.length} {items.length === 1 ? 'finding' : 'findings'}
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--ace-space-2)' }}>
            {items.map((f) => (
              <SentinelFindingRow key={f.id} finding={f} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function SentinelFindingRow({
  finding,
}: {
  finding: NonNullable<SentinelChipState['findings']>[number]
}) {
  return (
    <SeverityFinding
      severity={finding.severity}
      headline={finding.headline}
      detail={finding.detail}
      meta={finding.okr}
    />
  )
}

function MemoryChip({ state }: { state: MemoryChipState }) {
  return (
    <Tooltip
      content={`Patterns ACE has captured about how you think — ${state.patternCount} so far.`}
    >
      <span style={{ display: 'inline-flex', cursor: 'default' }}>
        <Chip variant="subtle">
          <span
            style={{
              color: 'var(--ace-voice-accent)',
              fontWeight: 'var(--ace-weight-bold)' as unknown as number,
              fontVariantNumeric: 'tabular-nums',
              fontFamily: 'var(--ace-font-mono)',
            }}
          >
            {state.patternCount}
          </span>
          <span style={{ color: 'var(--ace-ink-muted)', marginLeft: 4 }}>memory</span>
        </Chip>
      </span>
    </Tooltip>
  )
}
