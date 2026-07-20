// app/journey/StageGate.tsx
//
// Affordances at a current stage: respond at this level (steer the partner)
// or continue (wave them through to the next phase).
//
// Built against shadcn Button + Textarea + Separator.
import { ArrowRight, PaperPlaneTilt } from '@phosphor-icons/react'
import { useState } from 'react'

import { Button } from '@/design/shadcn/ui/button'
import { Separator } from '@/design/shadcn/ui/separator'
import { Textarea } from '@/design/shadcn/ui/textarea'

interface StageGateProps {
  respondPlaceholder?: string
  continueLabel?: string
  onRespond?: (text: string) => void
  onContinue?: () => void
}

export function StageGate({
  respondPlaceholder = 'respond at this stage…',
  continueLabel = 'continue →',
  onRespond,
  onContinue,
}: StageGateProps) {
  const [respondOpen, setRespondOpen] = useState(false)
  const [text, setText] = useState('')

  const submit = () => {
    if (text.trim().length === 0) return
    onRespond?.(text.trim())
    setText('')
    setRespondOpen(false)
  }

  return (
    <div className="flex flex-col gap-2 px-5 py-4">
      <Separator />
      {respondOpen ? (
        <div className="flex flex-col gap-2 pt-2">
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={respondPlaceholder}
            autoFocus
            rows={2}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                submit()
              }
              if (e.key === 'Escape') {
                setRespondOpen(false)
                setText('')
              }
            }}
          />
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="cursor-pointer"
              onClick={() => {
                setRespondOpen(false)
                setText('')
              }}
            >
              cancel
            </Button>
            <Button
              variant="default"
              size="sm"
              className="cursor-pointer"
              onClick={submit}
            >
              <PaperPlaneTilt size={14} weight="fill" />
              send to stage
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-3 pt-2">
          <button
            type="button"
            className="font-mono text-xs uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 rounded-sm px-1 -mx-1"
            onClick={() => setRespondOpen(true)}
          >
            respond at this stage…
          </button>
          <Button
            variant="default"
            size="sm"
            className="cursor-pointer"
            onClick={() => onContinue?.()}
          >
            {continueLabel}
            <ArrowRight size={14} weight="bold" />
          </Button>
        </div>
      )}
    </div>
  )
}
