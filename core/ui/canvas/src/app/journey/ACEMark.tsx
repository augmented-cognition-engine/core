// app/journey/ACEMark.tsx
//
// The ACE partner mark — a small animated SVG that signals "the partner
// is here, attentive, thinking" without resorting to a literal AI-brain
// icon or branded letter avatar.
//
// Two variants available. Swap by changing the default export.
//
//   variant="iris"      Concentric arcs that breathe in and out, like
//                       an attentive eye. Reads as quiet presence.
//   variant="synaptic"  Small dots inside a circle flickering at
//                       randomized intervals, like background neurons
//                       firing. Reads as ambient cognition.
//
// Both honor prefers-reduced-motion via CSS, themable via semantic tokens.

interface ACEMarkProps {
  /** Diameter in px. Default 36. */
  size?: number
  /** Which mark variant to render. Defaults to 'iris'. */
  variant?: 'iris' | 'synaptic'
  className?: string
}

export function ACEMark({ size = 36, variant = 'iris', className }: ACEMarkProps) {
  if (variant === 'synaptic') return <SynapticMark size={size} className={className} />
  return <IrisMark size={size} className={className} />
}

// ---------------------------------------------------------------------------
// Iris — concentric breathing arcs
// ---------------------------------------------------------------------------

function IrisMark({ size, className }: { size: number; className?: string }) {
  const radius = size / 2
  const cx = radius
  const cy = radius

  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center align-middle ${className ?? ''}`}
      style={{ width: size, height: size }}
      aria-label="ACE partner — attentive"
      role="img"
    >
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} className="block">
        {/* Outer ring — boundary */}
        <circle
          cx={cx}
          cy={cy}
          r={radius - 1}
          className="fill-brand/5 stroke-brand/25"
          strokeWidth={1}
        />

        {/* Three breathing rings — each animates its radius with a phase offset
            so the iris pulses inward/outward like an attentive eye. */}
        <circle
          cx={cx}
          cy={cy}
          r={size * 0.36}
          className="fill-none stroke-brand"
          strokeWidth={1.25}
          style={{
            transformOrigin: 'center',
            animation: 'ace-iris-breath 3.6s ease-in-out 0s infinite',
            opacity: 0.85,
          }}
        />
        <circle
          cx={cx}
          cy={cy}
          r={size * 0.26}
          className="fill-none stroke-brand"
          strokeWidth={1.25}
          style={{
            transformOrigin: 'center',
            animation: 'ace-iris-breath 3.6s ease-in-out 0.45s infinite',
            opacity: 0.7,
          }}
        />
        <circle
          cx={cx}
          cy={cy}
          r={size * 0.16}
          className="fill-none stroke-brand"
          strokeWidth={1.25}
          style={{
            transformOrigin: 'center',
            animation: 'ace-iris-breath 3.6s ease-in-out 0.9s infinite',
            opacity: 0.55,
          }}
        />

        {/* Central dot — fixed anchor */}
        <circle cx={cx} cy={cy} r={size * 0.06} className="fill-brand" />
      </svg>

      <style>{`
        @keyframes ace-iris-breath {
          0%, 100% { transform: scale(1);    opacity: var(--ace-iris-op, 0.85); }
          50%      { transform: scale(0.78); opacity: 0.35; }
        }
        @media (prefers-reduced-motion: reduce) {
          [aria-label="ACE partner — attentive"] svg circle {
            animation: none !important;
          }
        }
      `}</style>
    </span>
  )
}

// ---------------------------------------------------------------------------
// Synaptic — flickering dots inside a circle
// ---------------------------------------------------------------------------

const SYNAPTIC_DOTS: Array<{ x: number; y: number; delay: number; duration: number }> = [
  { x: 0.32, y: 0.30, delay: 0.0, duration: 1.6 },
  { x: 0.62, y: 0.22, delay: 0.4, duration: 1.9 },
  { x: 0.74, y: 0.48, delay: 0.8, duration: 1.4 },
  { x: 0.58, y: 0.72, delay: 0.2, duration: 2.1 },
  { x: 0.30, y: 0.66, delay: 1.0, duration: 1.7 },
  { x: 0.48, y: 0.42, delay: 0.6, duration: 1.5 },
  { x: 0.22, y: 0.48, delay: 1.3, duration: 1.8 },
]

function SynapticMark({ size, className }: { size: number; className?: string }) {
  const radius = size / 2
  return (
    <span
      className={`inline-flex shrink-0 ${className ?? ''}`}
      style={{ width: size, height: size }}
      aria-label="ACE partner — thinking"
      role="img"
    >
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} className="block">
        {/* Outer ring — boundary */}
        <circle
          cx={radius}
          cy={radius}
          r={radius - 1}
          className="fill-primary/5 stroke-primary/25"
          strokeWidth={1}
        />

        {/* Synaptic dots — flicker at randomized intervals */}
        {SYNAPTIC_DOTS.map((d, i) => (
          <circle
            key={i}
            cx={d.x * size}
            cy={d.y * size}
            r={size * 0.055}
            className="fill-primary"
            style={{
              animation: `ace-synaptic-flicker ${d.duration}s ease-in-out ${d.delay}s infinite`,
            }}
          />
        ))}
      </svg>

      <style>{`
        @keyframes ace-synaptic-flicker {
          0%, 100% { opacity: 0.15; }
          40%      { opacity: 0.95; }
          55%      { opacity: 0.4;  }
          70%      { opacity: 0.85; }
        }
        @media (prefers-reduced-motion: reduce) {
          [aria-label="ACE partner — thinking"] svg circle[style] {
            animation: none !important;
            opacity: 0.5 !important;
          }
        }
      `}</style>
    </span>
  )
}
