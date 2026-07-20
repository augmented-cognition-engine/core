// frontend/src/design/components/Dialog.tsx
//
// Shim over canonical shadcn Dialog. Public API matches the legacy
// trigger-prop pattern so existing consumers (extension surfaces,
// canvas main app) don't need to change. The shadcn
// Dialog primitive at @/design/shadcn/ui/dialog provides all behavior
// (focus trap, scroll lock, escape, portal, ARIA).
import type { ReactElement, ReactNode } from 'react'

import {
  Dialog as ShadcnDialog,
  DialogClose as ShadcnDialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/design/shadcn/ui/dialog'

export interface DialogProps {
  trigger: ReactElement
  title: ReactNode
  description?: ReactNode
  children: ReactNode
  open?: boolean
  onOpenChange?: (open: boolean) => void
  width?: number | string
  titleVisuallyHidden?: boolean
  descriptionVisuallyHidden?: boolean
}

export function Dialog({
  trigger,
  title,
  description,
  children,
  open,
  onOpenChange,
  width,
  titleVisuallyHidden = false,
  descriptionVisuallyHidden = false,
}: DialogProps) {
  const widthStyle = width !== undefined
    ? { maxWidth: typeof width === 'number' ? `${width}px` : width }
    : undefined

  return (
    <ShadcnDialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent style={widthStyle} className={width !== undefined ? 'sm:max-w-none' : undefined}>
        <DialogHeader>
          <DialogTitle className={titleVisuallyHidden ? 'sr-only' : undefined}>{title}</DialogTitle>
          {description !== undefined && (
            <DialogDescription className={descriptionVisuallyHidden ? 'sr-only' : undefined}>
              {description}
            </DialogDescription>
          )}
        </DialogHeader>
        {children}
      </DialogContent>
    </ShadcnDialog>
  )
}

export function DialogClose({ children }: { children: ReactElement }) {
  return <ShadcnDialogClose asChild>{children}</ShadcnDialogClose>
}
