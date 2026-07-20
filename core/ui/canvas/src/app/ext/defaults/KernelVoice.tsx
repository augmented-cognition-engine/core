// core/ui/canvas/src/app/ext/defaults/KernelVoice.tsx
//
// Kernel-default partner-voice line — rendered when no extension fills
// the `voice` slot. A quiet one-line readout of what the partner just
// noticed; extensions may register a branded implementation with richer
// motion (typewriter, ambient accents) through the ext seam.
import type { PartnerVoiceProps } from '../registry'

export function KernelVoice({ children, speaker = 'ACE' }: PartnerVoiceProps) {
  return (
    <div className="flex items-baseline gap-2.5 min-w-0">
      <span
        aria-hidden
        className="self-center size-1.5 shrink-0 rounded-full bg-[var(--ace-voice-accent)] animate-pulse"
      />
      <span className="shrink-0 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {speaker}
      </span>
      <span className="min-w-0 text-sm leading-snug text-foreground/90">
        {children}
      </span>
    </div>
  )
}
