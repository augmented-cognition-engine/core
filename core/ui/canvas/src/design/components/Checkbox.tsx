// core/ui/canvas/src/design/components/Checkbox.tsx
//
// Layer 4 behavioral wrapper over @radix-ui/react-checkbox. Renders the
// hairline-bordered box + accent fill on check, with optional label and
// description text. Composed inline in form rows.
//
// Variants:
//   - default: square box + adjacent label/description
//   - card:    the whole row is a clickable card with the box on the
//              left, used for selecting a single option from a list of
//              card-shaped alternatives
import * as RadixCheckbox from '@radix-ui/react-checkbox'
import type { ReactNode } from 'react'

export type CheckboxVariant = 'default' | 'card'

export interface CheckboxProps {
  checked: boolean
  onChange: (checked: boolean) => void
  /** The primary label. Required for accessibility — if visually
   *  hidden, pass `ariaLabel` instead and omit this. */
  label?: ReactNode
  /** Optional secondary text shown smaller under the label. */
  description?: ReactNode
  variant?: CheckboxVariant
  disabled?: boolean
  /** Used when `label` is omitted (rare). */
  ariaLabel?: string
  dataTest?: string
}

export function Checkbox({
  checked,
  onChange,
  label,
  description,
  variant = 'default',
  disabled = false,
  ariaLabel,
  dataTest,
}: CheckboxProps) {
  const box = (
    <RadixCheckbox.Root
      checked={checked}
      onCheckedChange={(v) => onChange(v === true)}
      disabled={disabled}
      aria-label={label === undefined ? ariaLabel : undefined}
      data-test={dataTest}
      style={{
        width: 16,
        height: 16,
        borderRadius: 'var(--ace-radius-sm)',
        border: checked
          ? '1px solid var(--ace-accent)'
          : '1px solid var(--ace-line-strong)',
        background: checked ? 'var(--ace-accent)' : 'var(--ace-surface-raised)',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: disabled ? 'not-allowed' : 'pointer',
        outline: 'none',
        transition:
          'background var(--ace-motion-micro) var(--ace-ease-out), border-color var(--ace-motion-micro) var(--ace-ease-out)',
        flex: '0 0 auto',
      }}
    >
      <RadixCheckbox.Indicator>
        <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden>
          <path
            d="M3 8 L7 12 L13 4"
            fill="none"
            stroke="var(--ace-accent-ink)"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </RadixCheckbox.Indicator>
    </RadixCheckbox.Root>
  )

  if (label === undefined) return box

  const labelBlock = (
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
  )

  if (variant === 'card') {
    return (
      <label
        style={{
          display: 'flex',
          gap: 'var(--ace-space-3)',
          alignItems: 'flex-start',
          padding: 'var(--ace-space-3) var(--ace-space-4)',
          background: checked ? 'var(--ace-surface-tint)' : 'var(--ace-surface-raised)',
          border: checked ? '1px solid var(--ace-accent)' : '1px solid var(--ace-line)',
          borderRadius: 'var(--ace-radius-md)',
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.6 : 1,
          transition:
            'background var(--ace-motion-micro) var(--ace-ease-out), border-color var(--ace-motion-micro) var(--ace-ease-out)',
        }}
      >
        {box}
        {labelBlock}
      </label>
    )
  }

  return (
    <label
      style={{
        display: 'inline-flex',
        gap: 'var(--ace-space-2)',
        alignItems: 'flex-start',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.6 : 1,
      }}
    >
      {box}
      {labelBlock}
    </label>
  )
}
