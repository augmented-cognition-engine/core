// core/ui/canvas/src/app/LiveBrain.tsx
//
// LiveBrain — the reasoning canvas rendering REAL substrate output: beliefs whose
// canvas ground just shifted, re-derived by ACE against the changed evidence. The
// first slice of "the brain visualized, for real": the data is the actual
// grounds -> metabolism -> shadow re-derivation loop, exported from the live graph
// (scripts/export_live_brain.py). The transport is a snapshot for now; the live
// WebSocket the useAceCoreState seam anticipates is the next slice. Composed only
// from ACE design-system components.
import { useEffect, useState } from 'react'

import { Button, Card, Chip, Eyebrow, TooltipProvider } from '../design/components'
import { SidebarInset, SidebarProvider } from '../design/shadcn/ui/sidebar'
import { KernelNav } from './ext/defaults/KernelNav'
import { extensionSlot } from './ext/registry'

// Same sidebar chrome as the room (/room) — the live beliefs render as a
// first-class reasoning-canvas surface, not a bare page.
const Nav = extensionSlot('nav') ?? KernelNav

interface Belief {
  belief: string
  prior_confidence: number
  proposed_confidence: number
  still_supported: boolean
  rationale: string
  ground: string
}

const pct = (n: number) => `${Math.round(n * 100)}%`

// Live backend when VITE_BRAIN_LIVE_URL is set (scripts/brain_live_host.py),
// else the committed snapshot — the seam's fixture -> live progression.
const SRC = (import.meta.env.VITE_BRAIN_LIVE_URL as string | undefined) ?? '/live-brain.json'
const CTX = SRC.replace('/brain-live', '/context')

export function LiveBrain() {
  const [beliefs, setBeliefs] = useState<Belief[] | null>(null)
  const [live, setLive] = useState(false)
  const [sel, setSel] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () =>
    fetch(SRC)
      .then((r) => r.json())
      .then((d) => {
        setBeliefs((d.beliefs as Belief[]) ?? [])
        setLive(d.source === 'live')
      })
      .catch(() => setBeliefs([]))

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const submit = async () => {
    if (!sel || !text.trim()) return
    setBusy(true)
    try {
      await fetch(CTX, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ belief: sel, text }),
      })
      setText('')
      await load()
    } finally {
      setBusy(false)
    }
  }

  return (
    <TooltipProvider>
      <SidebarProvider>
        <Nav />
        <SidebarInset className="h-svh overflow-y-auto bg-muted/40">
          <div className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-10">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <Eyebrow>the brain, visualized</Eyebrow>
          {live && <Chip variant="strong">live</Chip>}
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">Re-evaluating itself</h1>
        <p className="text-sm text-muted-foreground">
          Beliefs whose canvas ground just shifted — re-derived by ACE against the changed
          evidence. Real output of the grounds → metabolism → re-derivation loop, not a fixture.
        </p>
      </div>

      {live && (
        <Card padding="md" className="flex flex-col gap-3">
          <Eyebrow>drop context</Eyebrow>
          <select
            value={sel}
            onChange={(e) => setSel(e.target.value)}
            className="rounded-md border bg-background px-3 py-2 text-sm text-foreground"
          >
            <option value="">Which belief does this evidence bear on?</option>
            {beliefs?.map((b) => (
              <option key={b.belief} value={b.belief}>
                {b.belief}
              </option>
            ))}
          </select>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Drop new evidence — what buyers actually said, the test result, a competitor move…"
            rows={3}
            className="rounded-md border bg-background px-3 py-2 text-sm text-foreground"
          />
          <div>
            <Button onClick={submit} disabled={busy || !sel || !text.trim()}>
              {busy ? 'Re-evaluating…' : 'Re-evaluate against this'}
            </Button>
          </div>
        </Card>
      )}

      {beliefs === null && <p className="text-sm text-muted-foreground">Loading…</p>}
      {beliefs?.length === 0 && (
        <p className="text-sm text-muted-foreground">No restless beliefs right now.</p>
      )}

      <div className="flex flex-col gap-4">
        {beliefs?.map((b) => {
          const up = b.proposed_confidence >= b.prior_confidence
          return (
            <Card key={b.belief} padding="lg" className="flex flex-col gap-3">
              <div className="flex items-start justify-between gap-4">
                <h3 className="text-base font-semibold leading-snug text-foreground">{b.belief}</h3>
                <Chip variant={b.still_supported ? 'strong' : 'subtle'}>
                  {b.still_supported ? 'still supported' : 'undercut'}
                </Chip>
              </div>

              <div className="flex items-center gap-3">
                <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  confidence
                </span>
                <span className="text-sm text-muted-foreground line-through tabular-nums">
                  {pct(b.prior_confidence)}
                </span>
                <span className="text-muted-foreground">→</span>
                <span className="text-2xl font-bold tabular-nums text-foreground">
                  {pct(b.proposed_confidence)}
                </span>
                <span className="text-xs text-muted-foreground">{up ? 'strengthened' : 'weakened'}</span>
              </div>

              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className={up ? 'h-full rounded-full bg-primary' : 'h-full rounded-full bg-destructive'}
                  style={{ width: pct(b.proposed_confidence) }}
                />
              </div>

              <p className="text-sm text-muted-foreground">{b.rationale}</p>
              <p className="text-xs italic text-muted-foreground/80">ground: {b.ground}</p>
            </Card>
          )
        })}
      </div>
          </div>
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  )
}
