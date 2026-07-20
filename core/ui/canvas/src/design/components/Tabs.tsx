// core/ui/canvas/src/design/components/Tabs.tsx
//
// Layer 4 behavioral wrapper over @radix-ui/react-tabs. Configured via
// a `tabs` prop where each entry includes the panel content — surfaces
// don't compose Tab/Panel children, they pass a single config array.
// Simpler API than Radix's component composition; same accessibility.
//
// Radix handles: roving tab index, ARIA tablist/tab/tabpanel roles,
// keyboard navigation (arrow keys + Home/End), focus return.
//
// Variants:
//   - default:   bordered hairline panel, active tab tints with accent
//   - pill:      tabs are pill-shaped chips, active is filled
//   - underline: tabs sit on a baseline, active gains accent underline
import * as RadixTabs from '@radix-ui/react-tabs'
import type { CSSProperties, ReactNode } from 'react'

export type TabsVariant = 'default' | 'pill' | 'underline'

export interface TabConfig {
  id: string
  label: ReactNode
  /** Optional small muted text after the label (kbd shortcut, count). */
  hint?: ReactNode
  /** Content rendered when this tab is active. */
  content: ReactNode
}

export interface TabsProps {
  tabs: TabConfig[]
  activeTab: string
  onTabChange: (id: string) => void
  variant?: TabsVariant
  dataTest?: string
}

const LIST_STYLE: Record<TabsVariant, CSSProperties> = {
  default: {
    display: 'flex',
    gap: 'var(--ace-space-1)',
    padding: 'var(--ace-space-1)',
    background: 'var(--ace-surface-recessed)',
    borderRadius: 'var(--ace-radius-base)',
  },
  pill: {
    display: 'flex',
    gap: 'var(--ace-space-2)',
    flexWrap: 'wrap',
  },
  underline: {
    display: 'flex',
    gap: 'var(--ace-space-4)',
    borderBottom: '1px solid var(--ace-line)',
  },
}

const TRIGGER_BASE: CSSProperties = {
  fontFamily: 'var(--ace-font-sans)',
  fontSize: 'var(--ace-text-sm)',
  fontWeight: 'var(--ace-weight-medium)' as unknown as number,
  color: 'var(--ace-ink-soft)',
  background: 'transparent',
  border: 'none',
  cursor: 'pointer',
  outline: 'none',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 'var(--ace-space-2)',
  transition:
    'color var(--ace-motion-micro) var(--ace-ease-out), background var(--ace-motion-micro) var(--ace-ease-out)',
}

const TRIGGER_VARIANT: Record<TabsVariant, CSSProperties> = {
  default: {
    padding: 'var(--ace-space-1) var(--ace-space-3)',
    borderRadius: 'var(--ace-radius-sm)',
  },
  pill: {
    padding: 'var(--ace-space-1) var(--ace-space-3)',
    borderRadius: 'var(--ace-radius-pill)',
    border: '1px solid var(--ace-line)',
  },
  underline: {
    padding: 'var(--ace-space-2) 0',
    borderRadius: 0,
    marginBottom: -1,
  },
}

function activeStyles(variant: TabsVariant): CSSProperties {
  switch (variant) {
    case 'default':
      return {
        background: 'var(--ace-surface-raised)',
        color: 'var(--ace-ink)',
        boxShadow: 'var(--ace-shadow-sm)',
      }
    case 'pill':
      return {
        background: 'var(--ace-accent)',
        color: 'var(--ace-accent-ink)',
        borderColor: 'var(--ace-accent)',
      }
    case 'underline':
      return {
        color: 'var(--ace-ink)',
        borderBottom: '2px solid var(--ace-accent)',
        paddingBottom: 'calc(var(--ace-space-2) - 1px)',
      }
  }
}

export function Tabs({
  tabs,
  activeTab,
  onTabChange,
  variant = 'default',
  dataTest,
}: TabsProps) {
  return (
    <RadixTabs.Root
      value={activeTab}
      onValueChange={onTabChange}
      data-test={dataTest}
    >
      <RadixTabs.List style={LIST_STYLE[variant]}>
        {tabs.map((tab) => {
          const isActive = tab.id === activeTab
          return (
            <RadixTabs.Trigger
              key={tab.id}
              value={tab.id}
              style={{
                ...TRIGGER_BASE,
                ...TRIGGER_VARIANT[variant],
                ...(isActive ? activeStyles(variant) : {}),
              }}
            >
              <span>{tab.label}</span>
              {tab.hint !== undefined && (
                <span
                  style={{
                    fontSize: 'var(--ace-text-xs)',
                    color: isActive && variant === 'pill' ? 'var(--ace-accent-ink)' : 'var(--ace-ink-muted)',
                    fontFamily: 'var(--ace-font-mono)',
                  }}
                >
                  {tab.hint}
                </span>
              )}
            </RadixTabs.Trigger>
          )
        })}
      </RadixTabs.List>
      {tabs.map((tab) => (
        <RadixTabs.Content
          key={tab.id}
          value={tab.id}
          style={{ outline: 'none', paddingTop: 'var(--ace-space-4)' }}
        >
          {tab.content}
        </RadixTabs.Content>
      ))}
    </RadixTabs.Root>
  )
}
