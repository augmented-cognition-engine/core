// core/ui/canvas/src/app/ext/defaults/KernelIntel.tsx
//
// Kernel-default intel panel — rendered inside the room's notifications
// dropdown when no extension fills the `intel` slot. Extensions with
// live monitoring surfaces (sentinels, foresight, etc.) register a
// richer panel through the ext seam.
import { Separator } from '@/design/shadcn/ui/separator'

export function KernelIntel() {
  return (
    <div className="px-2 py-2 space-y-3">
      <div className="flex items-center gap-2 px-1">
        <span className="text-sm font-semibold">Intel</span>
        <span className="ml-auto text-[10px] uppercase tracking-widest text-muted-foreground">
          always on
        </span>
      </div>

      <Separator />

      <p className="px-1 text-xs text-muted-foreground leading-snug">
        Nothing needs your attention right now. Findings from live
        monitors land here the moment they fire.
      </p>
    </div>
  )
}
