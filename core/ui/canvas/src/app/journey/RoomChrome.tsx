// app/journey/RoomChrome.tsx
//
// The room's page header — gives the room the same surface-identity bar
// every other page has (title + subtitle on the left), and the same
// header button set on the right as the page shells, so the chrome is
// identical across every surface:
//   - Live badge      — the partner is in motion
//   - Notifications    — Sentinel intel (the bell + count, same as Shell)
//   - Theme toggle     — light / dark
//   - ACE flyout       — the iris; kick off a new brainstorm
//
// The previous-sessions switcher does NOT live here — it sits in the
// PipelineStrip (the step panel), since re-entering a past deliberation is
// a move through the work, not surface chrome. See SessionsMenu.

import { Bell, MoonStar, Sun } from 'lucide-react'

import { Button } from '@/design/shadcn/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/design/shadcn/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/design/shadcn/ui/tooltip'

import { KernelIntel } from '../ext/defaults/KernelIntel'
import { extensionSlot } from '../ext/registry'
import { AceFlyout } from './AceFlyout'
import { useTheme } from './useTheme'

// Intel-panel slot: an extension with live monitoring surfaces registers
// its panel through the ext seam; the kernel renders a neutral default
// when none is registered. The demo finding-count badge only shows when
// an extension intel source is actually wired.
const extIntel = extensionSlot('intel')
const Intel = extIntel ?? KernelIntel

export function RoomChrome() {
  const { theme, toggle: toggleTheme } = useTheme()

  return (
    <header className="flex items-center gap-3 h-14 px-6 border-b border-border bg-background shrink-0">
      {/* Surface identity — matches the topbar every other page has. */}
      <div className="min-w-0">
        <div className="text-sm font-semibold tracking-tight truncate">Atrium</div>
        <div className="text-[11px] text-muted-foreground truncate">
          a live view into how ACE reasons
        </div>
      </div>

      {/* Right cluster — identical button set to the page shells:
          notifications · theme · ACE. (Live status lives in the sidebar
          footer, so it's not repeated here.) */}
      <div className="ml-auto flex items-center gap-2">
        {/* Notifications — intel from the registered monitor panel. */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Notifications"
              className="relative cursor-pointer"
            >
              <Bell />
              {extIntel !== undefined && (
                <span className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full bg-primary text-primary-foreground text-[10px] font-semibold inline-flex items-center justify-center">
                  14
                </span>
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" sideOffset={8} className="w-80 max-h-[60vh] overflow-y-auto">
            <Intel />
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Theme toggle */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
              onClick={toggleTheme}
              className="cursor-pointer"
            >
              {theme === 'dark' ? <Sun /> : <MoonStar />}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            {theme === 'dark' ? 'light mode' : 'dark mode'}
          </TooltipContent>
        </Tooltip>

        {/* ACE — the iris; kick off a new brainstorm. */}
        <AceFlyout />
      </div>
    </header>
  )
}
