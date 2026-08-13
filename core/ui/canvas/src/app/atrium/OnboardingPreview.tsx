import { useMemo, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Check,
  CircleDot,
  Compass,
  FlaskConical,
  Gauge,
  Radar,
  Scale,
  ShieldAlert,
  Sparkles,
} from 'lucide-react'

import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import { Card, CardContent } from '@/design/shadcn/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/design/shadcn/ui/dialog'
import type { IntelligenceOnboardingOutcome, IntelligenceOnboardingProfile } from './onboardingModel'

const ICONS: Record<string, typeof Compass> = {
  choice: Gauge,
  strategy: BarChart3,
  research: FlaskConical,
  risk: ShieldAlert,
  competition: Radar,
  custom: Compass,
}

function OutcomeIcon({ outcome }: { readonly outcome: IntelligenceOnboardingOutcome }) {
  const Icon = ICONS[outcome.icon_hint] ?? Compass
  return <Icon className="size-4" />
}

export function OnboardingPreview({ open, onOpenChange, profile }: { readonly open: boolean; readonly onOpenChange: (open: boolean) => void; readonly profile: IntelligenceOnboardingProfile }) {
  const [step, setStep] = useState(0)
  const [outcomeId, setOutcomeId] = useState(profile.outcomes[0]?.outcome_id ?? '')
  const [cadenceId, setCadenceId] = useState(profile.default_cadence_id)
  const outcome = useMemo(() => profile.outcomes.find((item) => item.outcome_id === outcomeId) ?? profile.outcomes[0], [outcomeId, profile.outcomes])

  function close(next: boolean) {
    onOpenChange(next)
    if (!next) setStep(0)
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="atrium-command-center dark max-h-[calc(100svh-2rem)] overflow-y-auto rounded-lg border-border bg-popover p-0 sm:max-w-4xl">
        <div className="border-b px-6 py-4 sm:px-8">
          <div className="flex items-center gap-2 font-mono text-[9px] font-semibold uppercase tracking-[0.17em] text-brand">
            <Sparkles className="size-3.5" /> Build your intelligence
          </div>
          <div className="mt-3 flex gap-1.5" aria-label={`Step ${step + 1} of 4`}>
            {[0, 1, 2, 3].map((item) => <div key={item} className={`h-1 flex-1 rounded-full ${item <= step ? 'bg-brand' : 'bg-border'}`} />)}
          </div>
        </div>

        <div className="px-6 py-7 sm:px-8">
          {step === 0 && (
            <>
              <DialogHeader className="max-w-2xl">
                <DialogTitle className="text-2xl tracking-tight">{profile.prompt}</DialogTitle>
                <DialogDescription className="text-sm leading-relaxed">{profile.description}</DialogDescription>
              </DialogHeader>
              <div className="mt-6 grid gap-3 md:grid-cols-2">
                {profile.outcomes.map((item) => {
                  const selected = item.outcome_id === outcomeId
                  return (
                    <Button key={item.outcome_id} type="button" variant="ghost" onClick={() => setOutcomeId(item.outcome_id)} className={`h-auto w-full justify-start gap-4 whitespace-normal rounded-lg border p-4 text-left ${selected ? 'border-brand/70 bg-brand/7' : 'bg-card hover:border-foreground/25 hover:bg-card'}`}>
                      <div className={`flex size-9 shrink-0 items-center justify-center rounded-md border ${selected ? 'border-brand/40 bg-brand/10 text-brand' : 'bg-muted text-muted-foreground'}`}><OutcomeIcon outcome={item} /></div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 text-sm font-semibold">{item.label}{selected && <Check className="size-3.5 text-brand" />}</div>
                        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{item.description}</p>
                      </div>
                    </Button>
                  )
                })}
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <DialogHeader className="max-w-2xl">
                <DialogTitle className="text-2xl tracking-tight">Tune the picture</DialogTitle>
                <DialogDescription>ACE recommends a complete starting view for <span className="text-foreground">{outcome.label.toLowerCase()}</span>. You can refine it later.</DialogDescription>
              </DialogHeader>
              <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_0.8fr]">
                <Card><CardContent className="p-5"><div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">Recommended coverage</div><div className="mt-4 flex flex-wrap gap-2">{outcome.recommended_topic_labels.length > 0 ? outcome.recommended_topic_labels.map((topic) => <Badge key={topic} variant="secondary" className="rounded-sm py-1 font-normal">{topic}</Badge>) : <span className="text-sm text-muted-foreground">Choose topics after continuing.</span>}</div><div className="mt-6 border-t pt-4"><div className="text-xs font-medium">You can add specific entities, organizations, products, policies, or technologies next.</div><p className="mt-1 text-xs text-muted-foreground">ACE asks only for details it cannot safely infer.</p></div></CardContent></Card>
                <div><div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">How often should ACE orient you?</div><div className="mt-3 space-y-2">{profile.cadences.map((cadence) => { const selected = cadence.cadence_id === cadenceId; return <Button key={cadence.cadence_id} type="button" variant="ghost" onClick={() => setCadenceId(cadence.cadence_id)} className={`h-auto w-full flex-col items-start whitespace-normal rounded-lg border p-4 text-left ${selected ? 'border-brand/70 bg-brand/7' : 'bg-card hover:border-foreground/25 hover:bg-card'}`}><div className="flex items-center gap-2 text-sm font-semibold"><CircleDot className={`size-3.5 ${selected ? 'text-brand' : 'text-muted-foreground'}`} />{cadence.label}</div><p className="mt-1 pl-5 text-xs font-normal text-muted-foreground">{cadence.description}</p></Button>})}</div></div>
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <DialogHeader className="max-w-2xl"><DialogTitle className="text-2xl tracking-tight">Review what ACE will build</DialogTitle><DialogDescription>Public evidence creates the first picture. Private sources remain optional and require explicit permission.</DialogDescription></DialogHeader>
              <div className="mt-6 grid gap-3 sm:grid-cols-2">
                <PlanCard label="Evidence" value="Recommended public mix" detail="Primary records, first-party claims, independent measurement, operational telemetry, and leading indicators." />
                <PlanCard label="Concept map" value="Proposed for review" detail="Entities, aliases, attributes, relationships, claims, events, and outcomes." />
                <PlanCard label="Watches" value={`${outcome.recommended_topic_labels.length || 'Custom'} starting areas`} detail="Material changes, contradictions, catalysts, and weak signals—scoped to your selected job." />
                <PlanCard label="Intelligence" value={`${outcome.recommended_intelligence_labels.length || 'Custom'} starting products`} detail={outcome.recommended_intelligence_labels.length > 0 ? outcome.recommended_intelligence_labels.join(' · ') : 'ACE will propose intelligence products from your custom questions.'} />
              </div>
              <div className="mt-4 flex items-start gap-3 rounded-lg border border-brand/25 bg-brand/5 p-4"><Scale className="mt-0.5 size-4 shrink-0 text-brand" /><p className="text-xs leading-relaxed text-muted-foreground"><span className="font-medium text-foreground">Nothing is connected or activated silently.</span> You will see every requested permission, every proposed source that remains unconnected, and every watch before it receives authority.</p></div>
            </>
          )}

          {step === 3 && (
            <>
              <DialogHeader className="max-w-2xl"><DialogTitle className="text-2xl tracking-tight">Your first picture is assembling</DialogTitle><DialogDescription>ACE's governed agents work as one team. Inspect them when you need to; otherwise, follow the outcomes.</DialogDescription></DialogHeader>
              <div className="mt-7 space-y-2">
                <BuildStep label="Find and validate evidence" result="Recommended source plan ready" />
                <BuildStep label="Map entities and concepts" result="Concept proposal ready for review" />
                <BuildStep label="Build and validate watches" result={`${outcome.recommended_topic_labels.length || 'Custom'} watches proposed`} />
                <BuildStep label="Challenge coverage and contradictions" result="Coverage gaps will remain visible" />
                <BuildStep label="Assemble the first cited Brief" result="Ready to open" featured />
              </div>
              <div className="mt-5 rounded-lg border bg-card p-4 text-xs text-muted-foreground">This preview demonstrates the experience contract. Live activation still follows ACE's governed Connect → Map → Watch → Brief → Activate lifecycle.</div>
            </>
          )}
        </div>

        <div className="flex items-center justify-between border-t px-6 py-4 sm:px-8">
          <Button type="button" variant="ghost" disabled={step === 0} onClick={() => setStep((value) => Math.max(0, value - 1))}><ArrowLeft className="size-4" /> Back</Button>
          {step < 3 ? <Button type="button" onClick={() => setStep((value) => Math.min(3, value + 1))}>{step === 2 ? 'Start watching' : 'Continue'} <ArrowRight className="size-4" /></Button> : <Button type="button" onClick={() => close(false)}>{profile.completion_label} <ArrowRight className="size-4" /></Button>}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function PlanCard({ label, value, detail }: { readonly label: string; readonly value: string | number; readonly detail: string }) {
  return <Card><CardContent className="p-5"><div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">{label}</div><div className="mt-2 text-sm font-semibold">{value}</div><p className="mt-2 text-xs leading-relaxed text-muted-foreground">{detail}</p></CardContent></Card>
}

function BuildStep({ label, result, featured = false }: { readonly label: string; readonly result: string; readonly featured?: boolean }) {
  return <div className={`flex items-center gap-3 rounded-lg border p-4 ${featured ? 'border-brand/40 bg-brand/7' : 'bg-card'}`}><div className="flex size-7 items-center justify-center rounded-full bg-brand/10 text-brand"><Check className="size-3.5" /></div><div className="min-w-0 flex-1"><div className="text-sm font-medium">{label}</div><div className="mt-0.5 text-xs text-muted-foreground">{result}</div></div>{featured && <Badge variant="secondary" className="rounded-sm font-mono text-[9px] text-brand">First value</Badge>}</div>
}
