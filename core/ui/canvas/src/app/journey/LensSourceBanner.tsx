// app/journey/LensSourceBanner.tsx
//
// When the user opens the room from a specific surface (e.g. a foresight page),
// this banner sits above the TopicHeader to communicate that the
// deliberation is *about that surface* — not floating in isolation.
//
// "ACE is not a destination — it's a lens." The lens is being used on
// something; the banner names that something.
//
// Built against shadcn semantic tokens + phosphor icons.

import { ArrowUUpLeft, Eye } from '@phosphor-icons/react'
import { useNavigate } from 'react-router-dom'

interface LensSourceBannerProps {
  /** Display label of the surface ACE is reasoning about. */
  label: string
  /** Original pathname so we can offer "back to source". */
  pathname: string
}

export function LensSourceBanner({ label, pathname }: LensSourceBannerProps) {
  const navigate = useNavigate()
  return (
    <div className="flex items-center justify-between gap-3 px-8 py-1.5 bg-foreground/[0.04] border-b border-foreground/10">
      <div className="flex items-center gap-2 min-w-0">
        <Eye size={14} weight="duotone" className="text-brand shrink-0" />
        <span className="font-mono text-[10px] uppercase tracking-widest text-brand/80 shrink-0">
          lens · on
        </span>
        <span className="font-mono text-xs text-foreground truncate">
          {label}
        </span>
        <span className="font-mono text-[10px] text-muted-foreground/70 truncate hidden sm:inline">
          {pathname}
        </span>
      </div>
      <button
        type="button"
        onClick={() => navigate(pathname)}
        className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 rounded-sm px-1"
      >
        <ArrowUUpLeft size={10} weight="bold" />
        back to {label.toLowerCase()}
      </button>
    </div>
  )
}
