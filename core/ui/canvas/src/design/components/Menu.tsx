// frontend/src/design/components/Menu.tsx
//
// Layer 4 — behavioral wrapper over @radix-ui/react-dropdown-menu. Used
// for action menus on contributions, decision cards, the synthesis card,
// etc.: "Comment", "Rerun", "Add perspective", "Branch from here".
//
// Radix handles: keyboard nav, ARIA roles, focus return, portal positioning,
// nested submenus. Visuals are ACE: paper-card panel with row items that
// hover-tint subtly.
//
// Usage:
//   <Menu
//     trigger={<Button variant="ghost">More</Button>}
//     items={[
//       { id: 'comment', label: 'Comment', onSelect: () => … },
//       { id: 'rerun',   label: 'Rerun this lens', onSelect: () => … },
//       { type: 'separator' },
//       { id: 'branch',  label: 'Branch from here', onSelect: () => … },
//     ]}
//   />
//
// Component tokens (Layer 3):
//   --ace-menu-bg, --ace-menu-border, --ace-menu-shadow, --ace-menu-radius,
//   --ace-menu-padding, --ace-menu-item-padding, --ace-menu-item-radius,
//   --ace-menu-item-hover-bg
import * as RadixMenu from '@radix-ui/react-dropdown-menu'
import type { ReactElement, ReactNode } from 'react'

export type MenuItem =
  | {
      id: string
      label: ReactNode
      onSelect: () => void
      disabled?: boolean
      hint?: ReactNode
      type?: 'item'
    }
  | { type: 'separator'; id?: string }
  | { type: 'label'; id?: string; label: ReactNode }

export interface MenuProps {
  trigger: ReactElement
  items: MenuItem[]
  side?: 'top' | 'right' | 'bottom' | 'left'
  align?: 'start' | 'center' | 'end'
  sideOffset?: number
}

export function Menu({
  trigger,
  items,
  side = 'bottom',
  align = 'end',
  sideOffset = 6,
}: MenuProps) {
  return (
    <RadixMenu.Root>
      <RadixMenu.Trigger asChild>{trigger}</RadixMenu.Trigger>
      <RadixMenu.Portal>
        <RadixMenu.Content
          side={side}
          align={align}
          sideOffset={sideOffset}
          className="ace-menu"
          style={{
            background: 'var(--ace-menu-bg)',
            border: 'var(--ace-menu-border)',
            boxShadow: 'var(--ace-menu-shadow)',
            borderRadius: 'var(--ace-menu-radius)',
            padding: 'var(--ace-menu-padding)',
            minWidth: 200,
            color: 'var(--ace-ink)',
            fontFamily: 'var(--ace-font-sans)',
            fontSize: 'var(--ace-text-base)',
            zIndex: 900,
          }}
        >
          {items.map((item, i) => {
            if (item.type === 'separator') {
              return (
                <RadixMenu.Separator
                  key={item.id ?? `sep-${i}`}
                  style={{
                    height: 1,
                    background: 'var(--ace-line-soft)',
                    margin: 'var(--ace-space-1) 0',
                  }}
                />
              )
            }
            if (item.type === 'label') {
              return (
                <RadixMenu.Label
                  key={item.id ?? `label-${i}`}
                  style={{
                    padding: 'var(--ace-space-1) var(--ace-space-3)',
                    fontSize: 'var(--ace-text-xs)',
                    color: 'var(--ace-ink-muted)',
                    textTransform: 'uppercase',
                    letterSpacing: 'var(--ace-track-wide)',
                  }}
                >
                  {item.label}
                </RadixMenu.Label>
              )
            }
            return (
              <RadixMenu.Item
                key={item.id}
                disabled={item.disabled}
                onSelect={item.onSelect}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 'var(--ace-space-3)',
                  padding: 'var(--ace-menu-item-padding)',
                  borderRadius: 'var(--ace-menu-item-radius)',
                  cursor: item.disabled ? 'not-allowed' : 'pointer',
                  opacity: item.disabled ? 0.5 : 1,
                  outline: 'none',
                  userSelect: 'none',
                }}
                onMouseEnter={(e) => {
                  if (!item.disabled) {
                    e.currentTarget.style.background = 'var(--ace-menu-item-hover-bg)'
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'transparent'
                }}
                onFocus={(e) => {
                  if (!item.disabled) {
                    e.currentTarget.style.background = 'var(--ace-menu-item-hover-bg)'
                  }
                }}
                onBlur={(e) => {
                  e.currentTarget.style.background = 'transparent'
                }}
              >
                <span>{item.label}</span>
                {item.hint !== undefined && (
                  <span
                    style={{
                      fontSize: 'var(--ace-text-sm)',
                      color: 'var(--ace-ink-muted)',
                      fontFamily: 'var(--ace-font-mono)',
                    }}
                  >
                    {item.hint}
                  </span>
                )}
              </RadixMenu.Item>
            )
          })}
        </RadixMenu.Content>
      </RadixMenu.Portal>
    </RadixMenu.Root>
  )
}
