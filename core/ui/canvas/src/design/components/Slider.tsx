// core/ui/canvas/src/design/components/Slider.tsx
//
// A bounded numeric knob, with its value always visible.
//
// WHY A SLIDER AND NOT AN INPUT. These are READ PREFERENCES with a sane band — a profile
// width, a smoothing radius, a colour-intensity scale. A free-text number field invites a
// value nobody wants: a typo'd 900 is not a preference, it is a broken chart, and the
// person who typed it will not know which of the two they are looking at. A range cannot
// express a number outside the band, which is the entire point of using one.
//
// THE VALUE IS ALWAYS RENDERED. A naked slider tells you roughly where you are, and
// "roughly" is useless the moment you want to reproduce a view, describe it to someone, or
// notice it drifted. The number goes beside the track, in tabular figures so it does not
// jitter as you drag.

import type { ReactNode } from 'react'

export interface SliderProps {
  value: number
  min: number
  max: number
  step?: number
  onChange: (value: number) => void
  /** Rendered beside the track. Required unless `ariaLabel` is set. */
  label?: ReactNode
  /** Appended to the readout — a unit, never a second number. */
  suffix?: string
  disabled?: boolean
  ariaLabel?: string
  /** Track width. The readout sits outside it and is not included. */
  width?: number
  dataTest?: string
}

export function Slider({
  value,
  min,
  max,
  step = 1,
  onChange,
  label,
  suffix,
  disabled = false,
  ariaLabel,
  width = 72,
  dataTest,
}: SliderProps) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--ace-space-2)',
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {label && (
        <span
          style={{
            fontSize: 'var(--ace-text-xs)',
            textTransform: 'uppercase',
            letterSpacing: 'var(--ace-tracking-wide)',
            color: 'var(--ace-ink-faint)',
            whiteSpace: 'nowrap',
          }}
        >
          {label}
        </span>
      )}
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        aria-label={ariaLabel ?? (typeof label === 'string' ? label : undefined)}
        onChange={(e) => onChange(Number(e.target.value))}
        data-test={dataTest}
        style={{
          width: `${width}px`,
          accentColor: 'var(--ace-accent)',
          cursor: disabled ? 'not-allowed' : 'pointer',
        }}
      />
      <span
        style={{
          fontFamily: 'var(--ace-font-mono)',
          // Tabular figures — proportional digits make the readout jitter as you drag,
          // which reads as the VALUE being unstable rather than the type.
          fontVariantNumeric: 'tabular-nums',
          fontSize: 'var(--ace-text-xs)',
          color: 'var(--ace-ink)',
          minWidth: '2.4rem',
        }}
      >
        {value}
        {suffix ?? ''}
      </span>
    </span>
  )
}
