// app/journey/AceFlyout.tsx
//
// Popover anchored to the ACE button in page chrome. Kicks off a NEW
// brainstorm session — submit text + ACE opens the room with that topic
// as L1, carrying the current page as the lens source.
//
// What's distinctive:
//   1. Page-aware suggestions — the user lands with prompts derived from
//      what's on the page, not a blank box. Reduces cold-start friction.
//   2. The submit doesn't navigate to a fresh room — it kicks off ACE
//      *about the current surface*, so the lens source banner stays
//      meaningful.
//
// Built against shadcn Popover + Button + Textarea + phosphor icons.

import { ArrowRight, Lightbulb, PaperPlaneTilt } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { Button } from '@/design/shadcn/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/design/shadcn/ui/popover'
import { Textarea } from '@/design/shadcn/ui/textarea'

import { ACEMark } from './ACEMark'
import { deriveActiveContext, useAceContext } from './aceContext'

interface AceFlyoutProps {
  /** Optional custom trigger. Defaults to a Button with the ACEMark. */
  trigger?: ReactNode
}

export function AceFlyout({ trigger }: AceFlyoutProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const ctx = useAceContext()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  const active = ctx.active ?? deriveActiveContext(location.pathname)
  const suggestions = active?.suggestions ?? []

  // Focus textarea when opened.
  useEffect(() => {
    if (open && textareaRef.current !== null) {
      const t = setTimeout(() => textareaRef.current?.focus(), 60)
      return () => clearTimeout(t)
    }
  }, [open])

  function kickoff(topic: string) {
    if (topic.trim().length === 0) return
    navigate('/atrium', {
      state: {
        from: active?.pathname ?? location.pathname,
        surface: active?.surface,
        label: active?.label,
        topic: topic.trim(),
      },
    })
    setOpen(false)
    setText('')
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        {trigger ?? (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Kick off a brainstorm with ACE"
            className="cursor-pointer relative"
          >
            <ACEMark size={20} variant="iris" />
          </Button>
        )}
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={8}
        className="w-[24rem] p-0 overflow-hidden"
      >
        {/* Header */}
        <div className="px-4 pt-4 pb-2 border-b border-border">
          <div className="flex items-center gap-2">
            <ACEMark size={18} variant="iris" />
            <div className="flex flex-col leading-tight">
              <span className="font-mono text-[10px] uppercase tracking-widest text-primary/80">
                start a brainstorm
              </span>
              {active !== null && (
                <span className="font-mono text-[11px] text-muted-foreground">
                  with {active.label} in view
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Page-aware suggestions */}
        {suggestions.length > 0 && (
          <div className="px-4 py-3 space-y-2 border-b border-border/60 bg-muted/30">
            <div className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              <Lightbulb size={11} weight="duotone" className="text-amber-600 dark:text-amber-400" />
              based on this page
            </div>
            <ul className="space-y-1.5">
              {suggestions.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    onClick={() => kickoff(s)}
                    className="group flex items-start gap-2 w-full text-left rounded-md px-2 py-1.5 cursor-pointer hover:bg-background transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                  >
                    <ArrowRight
                      size={12}
                      weight="bold"
                      className="mt-0.5 shrink-0 text-muted-foreground/60 group-hover:text-primary transition-colors duration-200"
                    />
                    <span className="font-heading text-xs leading-snug text-foreground/85 group-hover:text-foreground">
                      {s}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Free-text input */}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            kickoff(text)
          }}
          className="px-4 py-3 space-y-2"
        >
          <Textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="…or write your own"
            rows={2}
            className="resize-none min-h-16"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                kickoff(text)
              }
            }}
          />
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-[10px] text-muted-foreground">
              ⌘↩ to send
            </span>
            <Button
              type="submit"
              variant="default"
              size="sm"
              disabled={text.trim().length === 0}
              className="cursor-pointer"
            >
              <PaperPlaneTilt size={12} weight="fill" />
              kick off
            </Button>
          </div>
        </form>
      </PopoverContent>
    </Popover>
  )
}
