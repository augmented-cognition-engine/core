// core/ui/canvas/src/app/CogArrow.tsx
//
// Connector between cog-sections. Hand-sketched line + caption naming
// what happens at that hop (e.g. "frame the problem", "diverge",
// "converge", "next voice"). Editorial, not architectural.
//
// When `active`, the arrow + caption chroma-sweep — the next voice is
// in flight. The accent fades in and out on a ~6s ambient loop, the
// only motion at rest on the canvas during a deliberation.
interface CogArrowProps {
  caption: string
  active?: boolean
}

export function CogArrow({ caption, active = false }: CogArrowProps) {
  return (
    <div
      aria-hidden
      className={active ? 'ace-arrow--active' : undefined}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 4,
        padding: 'var(--ace-space-2) 0',
        color: active ? 'var(--ace-accent)' : 'var(--ace-ink-muted)',
        fontFamily: 'var(--ace-font-sans)',
        transition: 'color var(--ace-motion-flow) var(--ace-ease-organic)',
      }}
    >
      <span
        style={{
          fontSize: 'var(--ace-text-xs)',
          fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
          letterSpacing: 'var(--ace-track-wide)',
          textTransform: 'uppercase',
          padding: '2px var(--ace-space-2)',
          background: active ? 'var(--ace-accent-soft)' : 'var(--ace-surface-canvas)',
          border: `1px solid ${active ? 'var(--ace-accent)' : 'var(--ace-line-soft)'}`,
          borderRadius: 'var(--ace-radius-sm)',
          transition:
            'background var(--ace-motion-flow) var(--ace-ease-organic), border-color var(--ace-motion-flow) var(--ace-ease-organic)',
        }}
      >
        {caption}
      </span>
      <span
        style={{
          fontSize: 'var(--ace-text-base)',
          color: active ? 'var(--ace-accent)' : 'var(--ace-line-strong)',
          lineHeight: 1,
        }}
      >
        ↓
      </span>
    </div>
  )
}
