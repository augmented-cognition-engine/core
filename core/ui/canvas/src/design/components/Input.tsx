// core/ui/canvas/src/design/components/Input.tsx
//
// Shim over canonical shadcn Input. Preserves legacy controlled-value
// API + Enter-to-submit behavior so existing consumers (AskInput,
// AttentionCallout, BriefComposer, etc.) don't need changes.
import { forwardRef, type KeyboardEvent } from 'react'

import { Input as ShadcnInput } from '@/design/shadcn/ui/input'
import { cn } from '@/lib/utils'

export type InputVariant = 'default' | 'inline' | 'quiet'
export type InputSize = 'sm' | 'md'

export interface InputProps {
  value: string
  onChange: (value: string) => void
  onSubmit?: (value: string) => void
  placeholder?: string
  variant?: InputVariant
  size?: InputSize
  disabled?: boolean
  autoFocus?: boolean
  ariaLabel?: string
  /** `date` renders the platform's own date picker. It is a real type, not a text field
   *  with a format convention: a hand-typed date is a typo waiting to become a plausible
   *  wrong session, and the native control cannot express one. */
  type?: 'text' | 'email' | 'url' | 'search' | 'tel' | 'date'
  /** Bounded width (CSS length). Absent = fill the container, which is right in a form and
   *  wrong in a toolbar: an unbounded date picker eats the whole bar. */
  width?: string | number
  dataTest?: string
}

const VARIANT_CLASS: Record<InputVariant, string> = {
  default: '',
  inline: 'border-transparent bg-transparent shadow-none',
  quiet: 'border-transparent bg-muted/40',
}

const SIZE_CLASS: Record<InputSize, string> = {
  sm: 'h-8 text-xs',
  md: '',
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  {
    value,
    onChange,
    onSubmit,
    placeholder,
    variant = 'default',
    size = 'md',
    disabled = false,
    autoFocus = false,
    ariaLabel,
    type = 'text',
    width,
    dataTest,
  },
  ref,
) {
  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (onSubmit === undefined) return
    if (e.key !== 'Enter' || e.shiftKey) return
    const trimmed = value.trim()
    if (trimmed.length === 0) return
    e.preventDefault()
    onSubmit(trimmed)
  }
  return (
    <ShadcnInput
      ref={ref}
      type={type}
      value={value}
      placeholder={placeholder}
      disabled={disabled}
      autoFocus={autoFocus}
      aria-label={ariaLabel}
      data-test={dataTest}
      onChange={(e) => onChange(e.currentTarget.value)}
      onKeyDown={handleKeyDown}
      className={cn(VARIANT_CLASS[variant], SIZE_CLASS[size])}
      style={width === undefined ? undefined : { width: typeof width === 'number' ? `${width}px` : width }}
    />
  )
})
