// core/ui/canvas/src/design/components/ScoreHero.tsx
//
// Tailwind-utility port — big tabular-nums value + caption + trend.
import type { ReactNode } from 'react'

export interface ScoreHeroTrend {
  direction: 'up' | 'down' | 'flat'
  delta?: ReactNode
}

export interface ScoreHeroProps {
  value: ReactNode
  caption: ReactNode
  trend?: ScoreHeroTrend
  size?: 'md' | 'lg'
  tone?: string
  dataTest?: string
}

const TREND_GLYPH: Record<ScoreHeroTrend['direction'], string> = {
  up: '↑',
  down: '↓',
  flat: '→',
}

const TREND_CLASS: Record<ScoreHeroTrend['direction'], string> = {
  up: 'text-chart-1',
  down: 'text-destructive',
  flat: 'text-muted-foreground',
}

const SIZE_CLASS = {
  md: 'text-3xl',
  lg: 'text-5xl',
} as const

export function ScoreHero({ value, caption, trend, size = 'md', tone, dataTest }: ScoreHeroProps) {
  const numStyle = tone !== undefined ? { color: tone } : undefined
  return (
    <div data-test={dataTest} className="flex flex-col gap-1 items-start">
      <div
        style={numStyle}
        className={`${SIZE_CLASS[size]} font-bold tabular-nums leading-tight tracking-tight`}
      >
        {value}
      </div>
      <div className="inline-flex items-center gap-2">
        <div className="text-[10px] uppercase tracking-widest font-semibold text-muted-foreground">
          {caption}
        </div>
        {trend !== undefined && (
          <span className={`text-xs font-medium ${TREND_CLASS[trend.direction]}`}>
            {TREND_GLYPH[trend.direction]} {trend.delta}
          </span>
        )}
      </div>
    </div>
  )
}
