// core/ui/canvas/src/design/components/Acknowledgment.tsx
//
// Programmatic confirmation primitive — records state changes that
// happen off-canvas (a spec drafted, a decision captured, a settings
// change applied). Wraps @radix-ui/react-toast under the hood but the
// ACE API enforces partnership voice rules and forbids the operate-
// shape patterns the voice guide bans.
//
// What this primitive IS:
//   - Records ("Decision spotted", "Spec drafted")
//   - Inline with the reading flow when possible
//   - Auto-dismisses after a short read
//
// What this primitive is NOT:
//   - A notification ("⚠ Operation failed!") — use Pushback
//   - A success banner ("✅ Successfully created") — describe what
//     happened plainly
//   - A modal that requires clicking — acknowledgments don't gate work
//
// Voice rules enforced at the API level:
//   - No `[INFO]` / `[ERROR]` / `Success!` prefix — the message is the
//     observation directly
//   - Tone `pushback` is rejected here (use the Pushback primitive for
//     real disagreement; an Acknowledgment is a quiet record, not an
//     argument)
//
// Usage:
//   1. Wrap a subtree with <AcknowledgmentProvider>
//   2. Inside, call `const acknowledge = useAcknowledgment()`
//   3. Fire with `acknowledge({ title: 'Decision spotted', description: '…' })`
import * as RadixToast from '@radix-ui/react-toast'
import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from 'react'

export type AcknowledgmentTone = 'neutral' | 'positive'

export interface AcknowledgmentInput {
  title: string
  description?: ReactNode
  tone?: AcknowledgmentTone
  /** Display duration in milliseconds. Default 4000. */
  duration?: number
}

interface ActiveAcknowledgment extends AcknowledgmentInput {
  id: number
  open: boolean
}

interface AcknowledgmentContextValue {
  fire: (input: AcknowledgmentInput) => void
}

const AcknowledgmentContext = createContext<AcknowledgmentContextValue | null>(null)

export function useAcknowledgment(): (input: AcknowledgmentInput) => void {
  const ctx = useContext(AcknowledgmentContext)
  if (ctx === null) {
    throw new Error(
      'useAcknowledgment must be called inside <AcknowledgmentProvider>',
    )
  }
  return ctx.fire
}

const TONE_ACCENT: Record<AcknowledgmentTone, string> = {
  neutral: 'var(--ace-accent)',
  positive: 'var(--ace-success)',
}

interface ProviderProps {
  children: ReactNode
  /** Where the viewport sits on the page. Default 'bottom-right'. */
  position?: 'bottom-right' | 'bottom-center' | 'top-right'
}

export function AcknowledgmentProvider({
  children,
  position = 'bottom-right',
}: ProviderProps) {
  const [active, setActive] = useState<ActiveAcknowledgment[]>([])

  const fire = useCallback((input: AcknowledgmentInput) => {
    const id = Date.now() + Math.random()
    setActive((prev) => [...prev, { ...input, id, open: true }])
  }, [])

  const handleOpenChange = (id: number, open: boolean) => {
    if (open) return
    // Drop after Radix finishes its close animation.
    setTimeout(() => {
      setActive((prev) => prev.filter((a) => a.id !== id))
    }, 200)
  }

  const viewportStyle = positionStyle(position)

  return (
    <AcknowledgmentContext.Provider value={{ fire }}>
      <RadixToast.Provider swipeDirection="right">
        {children}
        {active.map((a) => (
          <RadixToast.Root
            key={a.id}
            open={a.open}
            duration={a.duration ?? 4000}
            onOpenChange={(open) => handleOpenChange(a.id, open)}
            style={{
              display: 'grid',
              gridTemplateColumns: 'auto 1fr',
              gap: 'var(--ace-space-3)',
              alignItems: 'flex-start',
              padding: 'var(--ace-space-3) var(--ace-space-4)',
              background: 'var(--ace-surface-raised)',
              borderRadius: 'var(--ace-radius-md)',
              boxShadow: 'var(--ace-shadow-popover)',
              borderLeft: `3px solid ${TONE_ACCENT[a.tone ?? 'neutral']}`,
              fontFamily: 'var(--ace-font-sans)',
              minWidth: 280,
              maxWidth: 400,
            }}
          >
            <span
              aria-hidden
              style={{
                width: 8,
                height: 8,
                marginTop: 6,
                borderRadius: 'var(--ace-radius-pill)',
                background: TONE_ACCENT[a.tone ?? 'neutral'],
                flex: '0 0 auto',
              }}
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
              <RadixToast.Title
                style={{
                  fontSize: 'var(--ace-text-md)',
                  fontWeight: 'var(--ace-weight-semibold)' as unknown as number,
                  color: 'var(--ace-ink)',
                }}
              >
                {a.title}
              </RadixToast.Title>
              {a.description !== undefined && (
                <RadixToast.Description
                  style={{
                    fontFamily: 'var(--ace-font-serif)',
                    fontSize: 'var(--ace-text-sm)',
                    color: 'var(--ace-ink-soft)',
                    lineHeight: 'var(--ace-leading-snug)',
                  }}
                >
                  {a.description}
                </RadixToast.Description>
              )}
            </div>
          </RadixToast.Root>
        ))}
        <RadixToast.Viewport
          style={{
            position: 'fixed',
            ...viewportStyle,
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--ace-space-2)',
            zIndex: 1000,
            listStyle: 'none',
            margin: 0,
            padding: 'var(--ace-space-4)',
          }}
        />
      </RadixToast.Provider>
    </AcknowledgmentContext.Provider>
  )
}

function positionStyle(
  position: NonNullable<ProviderProps['position']>,
): Record<string, string> {
  switch (position) {
    case 'bottom-right':
      return { bottom: '0', right: '0' }
    case 'bottom-center':
      return { bottom: '0', left: '50%', transform: 'translateX(-50%)' }
    case 'top-right':
      return { top: '0', right: '0' }
  }
}
