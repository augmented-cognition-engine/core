// core/ui/canvas/src/design/components/Switch.tsx
//
// Layer 4 behavioral wrapper over @radix-ui/react-switch. Distinct from
// Checkbox: a switch is for an on/off setting that takes effect
// immediately; a checkbox is for a selection that takes effect on form
// submit. Use Switch for "enable proactive line", "show advanced
// details"; use Checkbox for selecting from a list.
import * as RadixSwitch from '@radix-ui/react-switch'
import type { ReactNode } from 'react'

export interface SwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  /** Primary label. Required for accessibility unless `ariaLabel` is set. */
  label?: ReactNode
  /** Optional secondary text shown smaller under the label. */
  description?: ReactNode
  disabled?: boolean
  ariaLabel?: string
  dataTest?: string
}

const TRACK_WIDTH = 32
const TRACK_HEIGHT = 18
const THUMB_SIZE = 14
const THUMB_PADDING = (TRACK_HEIGHT - THUMB_SIZE) / 2

export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled = false,
  ariaLabel,
  dataTest,
}: SwitchProps) {
  const track = (
    <RadixSwitch.Root
      checked={checked}
      onCheckedChange={onChange}
      disabled={disabled}
      aria-label={label === undefined ? ariaLabel : undefined}
      data-test={dataTest}
      style={{
        width: TRACK_WIDTH,
        height: TRACK_HEIGHT,
        borderRadius: 'var(--ace-radius-pill)',
        background: checked ? 'var(--ace-accent)' : 'var(--ace-line-strong)',
        position: 'relative',
        border: 'none',
        cursor: disabled ? 'not-allowed' : 'pointer',
        outline: 'none',
        transition: 'background var(--ace-motion-micro) var(--ace-ease-out)',
        flex: '0 0 auto',
      }}
    >
      <RadixSwitch.Thumb
        style={{
          display: 'block',
          width: THUMB_SIZE,
          height: THUMB_SIZE,
          borderRadius: 'var(--ace-radius-pill)',
          background: 'var(--ace-surface-raised)',
          boxShadow: 'var(--ace-shadow-sm)',
          transform: checked
            ? `translateX(${TRACK_WIDTH - THUMB_SIZE - THUMB_PADDING}px) translateY(${THUMB_PADDING}px)`
            : `translateX(${THUMB_PADDING}px) translateY(${THUMB_PADDING}px)`,
          transition: 'transform var(--ace-motion-lift) var(--ace-ease-out)',
        }}
      />
    </RadixSwitch.Root>
  )

  if (label === undefined) return track

  return (
    <label
      style={{
        display: 'inline-flex',
        gap: 'var(--ace-space-3)',
        alignItems: 'flex-start',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.6 : 1,
      }}
    >
      {track}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
        <span
          style={{
            fontFamily: 'var(--ace-font-sans)',
            fontSize: 'var(--ace-text-md)',
            color: 'var(--ace-ink)',
            fontWeight: 'var(--ace-weight-medium)' as unknown as number,
          }}
        >
          {label}
        </span>
        {description !== undefined && (
          <span
            style={{
              fontFamily: 'var(--ace-font-sans)',
              fontSize: 'var(--ace-text-sm)',
              color: 'var(--ace-ink-muted)',
              lineHeight: 'var(--ace-leading-snug)',
            }}
          >
            {description}
          </span>
        )}
      </div>
    </label>
  )
}
