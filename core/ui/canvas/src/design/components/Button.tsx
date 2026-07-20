// frontend/src/design/components/Button.tsx
//
// Shim over canonical shadcn Button. Legacy variant names mapped to
// canonical (primary→default, secondary→outline, ghost→ghost).
import { forwardRef, type ReactNode } from 'react'

import { Button as ShadcnButton } from '@/design/shadcn/ui/button'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost'
export type ButtonSize = 'sm' | 'md'

export interface ButtonProps {
  children: ReactNode
  variant?: ButtonVariant
  size?: ButtonSize
  icon?: string
  title?: string
  disabled?: boolean
  onClick?: () => void
  type?: 'button' | 'submit'
  ariaLabel?: string
}

const VARIANT_MAP: Record<ButtonVariant, 'default' | 'outline' | 'ghost'> = {
  primary: 'default',
  secondary: 'outline',
  ghost: 'ghost',
}

const SIZE_MAP: Record<ButtonSize, 'sm' | 'default'> = {
  sm: 'sm',
  md: 'default',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    children,
    variant = 'secondary',
    size = 'md',
    icon,
    title,
    disabled = false,
    onClick,
    type = 'button',
    ariaLabel,
  },
  ref,
) {
  return (
    <ShadcnButton
      ref={ref}
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={ariaLabel}
      variant={VARIANT_MAP[variant]}
      size={SIZE_MAP[size]}
    >
      {icon !== undefined && <span aria-hidden>{icon}</span>}
      {children}
    </ShadcnButton>
  )
})
