// core/ui/canvas/src/app/VisionAnchor.tsx
//
// The north-star band. Frames every turn in terms of the user's actual
// goal — the partnership thesis requires the canvas to know what the
// user is working toward, not just what they're doing right now.
//
// Workshop-vocabulary: the goal is a serif statement; progress against
// OKRs reads as inline editorial language at the end of the line —
// not as right-aligned SaaS-progress chips. Each OKR span hovers to
// reveal detail.
import { Popover } from '../design/components'
import type { OKRState, VisionAnchorState } from './state'

interface VisionAnchorProps {
  state: VisionAnchorState
}

export function VisionAnchor({ state }: VisionAnchorProps) {
  return (
    <div
      style={{
        padding: 'var(--ace-space-3) var(--ace-space-8)',
        background: 'var(--ace-north-star-bg)',
        borderBottom: '1px solid var(--ace-north-star-line)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--ace-space-1)',
        flex: '0 0 auto',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--ace-font-sans)',
          fontSize: 'var(--ace-text-xs)',
          fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
          letterSpacing: 'var(--ace-track-widest)',
          textTransform: 'uppercase',
          color: 'var(--ace-north-star-label)',
        }}
      >
        North star
      </div>

      <p
        style={{
          margin: 0,
          fontFamily: 'var(--ace-font-serif)',
          fontSize: 'var(--ace-text-prose)',
          lineHeight: 1.5,
          color: 'var(--ace-ink)',
          letterSpacing: '-0.005em',
        }}
      >
        {state.goal}
        {state.okrs.length > 0 && (
          <>
            {' — '}
            {state.okrs.map((okr, i) => (
              <span key={okr.id}>
                {i > 0 && ', '}
                <OKRInline okr={okr} />
              </span>
            ))}
            .
          </>
        )}
      </p>
    </div>
  )
}

function OKRInline({ okr }: { okr: OKRState }) {
  const pct = okr.progress !== undefined ? Math.round(okr.progress * 100) : null
  const tone =
    okr.status === 'at-risk'
      ? 'var(--ace-warning)'
      : okr.status === 'stalled'
        ? 'var(--ace-ink-muted)'
        : 'var(--ace-ink)'

  const text = (
    <span
      style={{
        color: 'var(--ace-ink-soft)',
        cursor: 'pointer',
        borderBottom: '1px dotted var(--ace-line-strong)',
      }}
    >
      {pct !== null ? `${pct}% to ` : ''}
      <span style={{ color: 'var(--ace-ink)' }}>{okr.label.toLowerCase()}</span>
      {pct === null && tone === 'var(--ace-warning)' && (
        <span style={{ color: tone, marginLeft: 4 }}>(at risk)</span>
      )}
    </span>
  )

  return (
    <Popover
      content={<OKRDetail okr={okr} tone={tone} />}
      side="bottom"
      align="start"
      width={360}
    >
      <span>{text}</span>
    </Popover>
  )
}

function OKRDetail({ okr, tone }: { okr: OKRState; tone: string }) {
  const pct = okr.progress !== undefined ? Math.round(okr.progress * 100) : null
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--ace-space-3)',
        fontFamily: 'var(--ace-font-sans)',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--ace-font-serif)',
          fontSize: 'var(--ace-text-lg)',
          color: 'var(--ace-ink)',
          fontWeight: 'var(--ace-weight-medium)' as unknown as number,
        }}
      >
        {okr.label}
      </div>

      {pct !== null && (
        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              justifyContent: 'space-between',
              marginBottom: 4,
              fontSize: 'var(--ace-text-xs)',
              color: 'var(--ace-ink-muted)',
              letterSpacing: 'var(--ace-track-wide)',
              textTransform: 'uppercase',
              fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
            }}
          >
            <span>{okr.status ?? 'advancing'}</span>
            <span
              style={{
                fontFamily: 'var(--ace-font-mono)',
                fontVariantNumeric: 'tabular-nums',
                color: tone,
              }}
            >
              {pct}%
            </span>
          </div>
          <div
            style={{
              height: 2,
              background: 'var(--ace-line-soft)',
              overflow: 'hidden',
            }}
          >
            <div style={{ width: `${pct}%`, height: '100%', background: tone }} />
          </div>
        </div>
      )}

      {okr.detail !== undefined && (
        <div
          style={{
            fontSize: 'var(--ace-text-md)',
            color: 'var(--ace-ink-soft)',
            lineHeight: 'var(--ace-leading-prose)',
            fontFamily: 'var(--ace-font-serif)',
          }}
        >
          {okr.detail}
        </div>
      )}

      {okr.recentCommits !== undefined && okr.recentCommits.length > 0 && (
        <div>
          <div
            style={{
              fontSize: 'var(--ace-text-xs)',
              color: 'var(--ace-ink-muted)',
              letterSpacing: 'var(--ace-track-wide)',
              textTransform: 'uppercase',
              fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
              marginBottom: 'var(--ace-space-2)',
            }}
          >
            Lately
          </div>
          <ul
            style={{
              margin: 0,
              padding: 0,
              listStyle: 'none',
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--ace-space-1)',
            }}
          >
            {okr.recentCommits.map((c) => (
              <li
                key={c.id}
                style={{
                  display: 'flex',
                  gap: 'var(--ace-space-3)',
                  fontSize: 'var(--ace-text-sm)',
                  fontFamily: 'var(--ace-font-serif)',
                }}
              >
                <span
                  style={{
                    color: 'var(--ace-ink-muted)',
                    fontFamily: 'var(--ace-font-mono)',
                    minWidth: 56,
                    fontSize: 'var(--ace-text-xs)',
                  }}
                >
                  {c.date}
                </span>
                <span style={{ color: 'var(--ace-ink-soft)' }}>{c.what}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
