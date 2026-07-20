// frontend/src/design/components/LinkButton.tsx
//
// Tailwind-utility port — text-link with quiet underline.
import { forwardRef } from 'react'

export interface LinkButtonProps {
  children: React.ReactNode
  href: string
  external?: boolean
  dataTest?: string
}

export const LinkButton = forwardRef<HTMLAnchorElement, LinkButtonProps>(function LinkButton(
  { children, href, external = true, dataTest },
  ref,
) {
  return (
    <a
      ref={ref}
      href={href}
      target={external ? '_blank' : undefined}
      rel={external ? 'noopener noreferrer' : undefined}
      data-test={dataTest}
      className="inline-flex items-center gap-1 text-sm font-semibold text-foreground border-b border-border pb-0.5 hover:border-primary transition-colors no-underline"
    >
      {children}
    </a>
  )
})
