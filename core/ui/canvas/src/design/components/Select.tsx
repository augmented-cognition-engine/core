// core/ui/canvas/src/design/components/Select.tsx
//
// Shim over canonical shadcn Select. Legacy options-array API preserved.
import type { ReactNode } from 'react'

import {
  Select as ShadcnSelect,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/design/shadcn/ui/select'

export type SelectVariant = 'default' | 'inline' | 'quiet'
export type SelectSize = 'sm' | 'md'

export interface SelectOption {
  value: string
  label: ReactNode
  hint?: ReactNode
}

export interface SelectProps {
  options: SelectOption[]
  value: string | undefined
  onChange: (value: string) => void
  placeholder?: string
  variant?: SelectVariant
  size?: SelectSize
  disabled?: boolean
  ariaLabel?: string
  dataTest?: string
}

export function Select({
  options,
  value,
  onChange,
  placeholder = 'Select…',
  size = 'md',
  disabled = false,
  ariaLabel,
  dataTest,
}: SelectProps) {
  return (
    <ShadcnSelect value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger
        aria-label={ariaLabel}
        data-test={dataTest}
        className={size === 'sm' ? 'h-8 text-xs' : ''}
      >
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((opt) => (
          <SelectItem key={opt.value} value={opt.value}>
            <span className="flex items-center justify-between gap-3 w-full">
              <span>{opt.label}</span>
              {opt.hint !== undefined && (
                <span className="text-xs text-muted-foreground font-mono">{opt.hint}</span>
              )}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </ShadcnSelect>
  )
}
