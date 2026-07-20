// app/journey/TopRightChrome.tsx
//
// Globally-mounted top-right utility chrome. OS-style cluster: theme
// toggle, ACE entry (the room lens), settings/help. Lives on every
// route via main.tsx — survives navigation.
//
// The ACE button carries the *current page* as the lens source when
// clicked. "ACE is not a destination — it's a lens you bring to a
// surface." Clicking ACE from a foresight page opens the room
// reasoning about foresight, not from a cold start.
//
// ⌘J / Ctrl+J is the keyboard shortcut for the ACE action.
//
// Deliberately quiet — no live "in motion" indicators here; this is
// utility chrome, not a status panel.

import { Command, MoonStars, Question, Sun } from '@phosphor-icons/react'
import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { Button } from '@/design/shadcn/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/design/shadcn/ui/popover'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/design/shadcn/ui/tooltip'

import { ACEMark } from './ACEMark'
import { deriveActiveContext, useAceContext } from './aceContext'
import { useTheme } from './useTheme'

export function TopRightChrome() {
  const location = useLocation()
  const navigate = useNavigate()
  const ctx = useAceContext()
  const { theme, toggle: toggleTheme } = useTheme()
  const onAtrium = location.pathname === '/atrium' || location.pathname === '/room'

  const active = ctx.active ?? deriveActiveContext(location.pathname)

  function openLens() {
    if (active === null) {
      navigate('/atrium')
      return
    }
    navigate('/atrium', {
      state: {
        from: active.pathname ?? location.pathname,
        surface: active.surface,
        label: active.label,
        question: active.question,
      },
    })
  }

  // ⌘J / Ctrl+J — open the lens with the current surface as source.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key.toLowerCase() === 'j' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        openLens()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.surface, active?.question, location.pathname])

  return (
    <div
      role="toolbar"
      aria-label="Global chrome"
      className="fixed top-3 right-4 z-50 flex items-center gap-1 rounded-full border border-border bg-background/95 backdrop-blur-md px-1.5 py-1 shadow-md ring-1 ring-foreground/5"
    >
      {/* Theme toggle */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            className="cursor-pointer"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
          >
            {theme === 'dark' ? (
              <Sun size={14} weight="duotone" />
            ) : (
              <MoonStars size={14} weight="duotone" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          {theme === 'dark' ? 'light mode' : 'dark mode'}
        </TooltipContent>
      </Tooltip>

      {/* Divider */}
      <span aria-hidden className="h-4 w-px bg-border" />

      {/* ACE — the lens. Always visible. On `/` it's a no-op-ish (already
          in the room) but kept for consistency so the chrome feels stable
          across routes. */}
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={openLens}
            disabled={onAtrium}
            aria-label={onAtrium ? 'ACE (you are in Atrium)' : `Open Atrium on ${active?.label ?? 'this surface'}`}
            className="inline-flex items-center justify-center h-7 w-7 rounded-full cursor-pointer hover:bg-muted/60 transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 disabled:opacity-50 disabled:cursor-default"
          >
            <ACEMark size={20} variant="iris" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="flex items-center gap-2">
          {onAtrium ? (
            <span>you are in Atrium</span>
          ) : (
            <>
              <span>open Atrium · on {active?.label ?? 'this surface'}</span>
              <span className="inline-flex items-center gap-0.5 font-mono text-[10px] text-muted-foreground">
                <Command size={10} weight="bold" />J
              </span>
            </>
          )}
        </TooltipContent>
      </Tooltip>

      {/* Divider */}
      <span aria-hidden className="h-4 w-px bg-border" />

      {/* Settings / help — stub popover for now */}
      <Popover>
        <PopoverTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            className="cursor-pointer"
            aria-label="Settings and help"
          >
            <Question size={14} weight="duotone" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-72">
          <div className="space-y-2">
            <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Settings · Help
            </div>
            <ul className="space-y-1 text-sm">
              <li className="flex items-center justify-between gap-2 text-muted-foreground">
                <span>open the lens</span>
                <span className="font-mono text-[11px] inline-flex items-center gap-0.5">
                  <Command size={10} weight="bold" />J
                </span>
              </li>
              <li className="flex items-center justify-between gap-2 text-muted-foreground">
                <span>toggle theme</span>
                <span className="font-mono text-[11px]">click sun/moon</span>
              </li>
            </ul>
            <p className="pt-2 text-xs text-muted-foreground leading-snug">
              ACE is a reasoning framework, not a destination. The lens
              follows you across every surface — click ACE to maximize it
              with the current page as input.
            </p>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}
