// core/ui/canvas/src/design/components/ProactiveLine.tsx
//
// Shim over canonical shadcn Alert. Typewriter reveal preserved as a
// custom hook; tone-glyph mapped to lucide icons via inline span.
import { useEffect, useState, type ReactNode } from 'react'
import { Sparkles } from 'lucide-react'

import { Alert, AlertDescription } from '@/design/shadcn/ui/alert'

export type ProactiveLineTone = 'observation' | 'offer' | 'question'

export interface ProactiveLineProps {
  tone?: ProactiveLineTone
  observation: ReactNode
  offer?: ReactNode
  children?: ReactNode
  onDismiss?: () => void
  typewriter?: boolean
  dataTest?: string
}

const TYPEWRITER_TICK_MS = 14

function useTypewriterReveal(text: ReactNode, enabled: boolean): { revealed: ReactNode; isAnimating: boolean } {
  const isString = typeof text === 'string'
  const [reveal, setReveal] = useState<string>(isString && enabled ? '' : (isString ? text : ''))
  const [isAnimating, setIsAnimating] = useState(isString && enabled)

  useEffect(() => {
    if (!enabled || !isString) {
      setReveal(isString ? (text as string) : '')
      setIsAnimating(false)
      return
    }
    const full = text as string
    setReveal('')
    setIsAnimating(true)
    let i = 0
    const timer = window.setInterval(() => {
      i += 1
      if (i >= full.length) {
        setReveal(full)
        setIsAnimating(false)
        window.clearInterval(timer)
        return
      }
      setReveal(full.slice(0, i))
    }, TYPEWRITER_TICK_MS)
    return () => window.clearInterval(timer)
  }, [text, enabled, isString])

  return { revealed: isString ? reveal : text, isAnimating }
}

export function ProactiveLine({
  observation,
  offer,
  children,
  typewriter = false,
  dataTest,
}: ProactiveLineProps) {
  const { revealed, isAnimating } = useTypewriterReveal(observation, typewriter)
  return (
    <Alert data-test={dataTest}>
      <Sparkles />
      <AlertDescription>
        <span>{revealed}</span>
        {isAnimating && (
          <span aria-hidden className="inline-block w-2 ml-0.5 text-primary animate-pulse">|</span>
        )}
        {offer !== undefined && !isAnimating && (
          <>
            {' '}<span className="text-foreground font-medium">{offer}</span>
          </>
        )}
        {children !== undefined && !isAnimating && (
          <div className="mt-2">{children}</div>
        )}
      </AlertDescription>
    </Alert>
  )
}
