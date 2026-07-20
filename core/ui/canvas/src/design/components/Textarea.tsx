// core/ui/canvas/src/design/components/Textarea.tsx
//
// Shim over canonical shadcn Textarea. Preserves legacy controlled-value
// API + Cmd/Ctrl+Enter-to-submit + autoGrow behavior.
import { forwardRef, useEffect, useRef, type KeyboardEvent } from 'react'

import { Textarea as ShadcnTextarea } from '@/design/shadcn/ui/textarea'
import { cn } from '@/lib/utils'

export type TextareaVariant = 'default' | 'inline' | 'quiet'
export type TextareaSize = 'sm' | 'md'

export interface TextareaProps {
  value: string
  onChange: (value: string) => void
  onSubmit?: (value: string) => void
  placeholder?: string
  variant?: TextareaVariant
  size?: TextareaSize
  rows?: number
  autoGrow?: boolean
  maxRows?: number
  disabled?: boolean
  autoFocus?: boolean
  ariaLabel?: string
  dataTest?: string
}

const VARIANT_CLASS: Record<TextareaVariant, string> = {
  default: '',
  inline: 'border-transparent bg-transparent shadow-none',
  quiet: 'border-transparent bg-muted/40',
}

const SIZE_CLASS: Record<TextareaSize, string> = {
  sm: 'text-xs',
  md: '',
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea(
    {
      value,
      onChange,
      onSubmit,
      placeholder,
      variant = 'default',
      size = 'md',
      rows = 3,
      autoGrow = false,
      maxRows = 12,
      disabled = false,
      autoFocus = false,
      ariaLabel,
      dataTest,
    },
    ref,
  ) {
    const innerRef = useRef<HTMLTextAreaElement | null>(null)
    useEffect(() => {
      if (!autoGrow) return
      const el = innerRef.current
      if (el === null) return
      el.style.height = 'auto'
      const lineHeight = parseFloat(getComputedStyle(el).lineHeight || '20')
      const maxHeight = lineHeight * maxRows
      el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`
      el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden'
    }, [value, autoGrow, maxRows])

    const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (onSubmit === undefined) return
      if (e.key !== 'Enter') return
      if (!(e.metaKey || e.ctrlKey)) return
      const trimmed = value.trim()
      if (trimmed.length === 0) return
      e.preventDefault()
      onSubmit(trimmed)
    }

    const setRef = (el: HTMLTextAreaElement | null) => {
      innerRef.current = el
      if (typeof ref === 'function') ref(el)
      else if (ref !== null) ref.current = el
    }

    return (
      <ShadcnTextarea
        ref={setRef}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        autoFocus={autoFocus}
        aria-label={ariaLabel}
        data-test={dataTest}
        rows={autoGrow ? 1 : rows}
        onChange={(e) => onChange(e.currentTarget.value)}
        onKeyDown={handleKeyDown}
        className={cn(VARIANT_CLASS[variant], SIZE_CLASS[size], autoGrow ? 'resize-none' : 'resize-y')}
      />
    )
  },
)
