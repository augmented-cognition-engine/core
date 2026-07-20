// core/ui/canvas/src/app/showcase/V14Showcase.tsx
//
// Calibration surface for the b39gyV5NI preset. Mirrors canvas-preset/
// src/App.tsx in intent — but tuned to prove the preset can carry every
// product-chrome move using ONLY shadcn primitives + design tokens:
//
//   Verdict gets primary-surface chrome (the single most important node
//   on the page). Audit dial (Ready) gets a chart-3 watch rail. Committee
//   seats carry severity rails per status (destructive = veto, chart-3 =
//   dissent, chart-1 = serves, muted = observes). Sentinel findings use
//   the same severity rail vocabulary. Closing aside ties the chrome
//   inventory back to the JTBD: prove the preset cohere as a workspace.
//
// Components: ONLY @/design/shadcn/ui/*. Icons: lucide-react + ico glyph
// (data `mark`) in AvatarFallback for committee seats. No custom CSS.
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Compass,
  Eye,
  FileEdit,
  Flame,
  Hexagon,
  Info,
  Library,
  MoreHorizontal,
  PenLine,
  ScrollText,
  Settings,
  ShieldCheck,
  Sparkles,
  Users,
} from 'lucide-react'

import { cn } from '@/lib/utils'

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from '@/design/shadcn/ui/alert'
import { Avatar, AvatarFallback } from '@/design/shadcn/ui/avatar'
import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/design/shadcn/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/design/shadcn/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/design/shadcn/ui/dropdown-menu'
import { Input } from '@/design/shadcn/ui/input'
import { Label } from '@/design/shadcn/ui/label'
import { ScrollArea } from '@/design/shadcn/ui/scroll-area'
import { Separator } from '@/design/shadcn/ui/separator'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/design/shadcn/ui/sheet'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
} from '@/design/shadcn/ui/sidebar'
import { Skeleton } from '@/design/shadcn/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/design/shadcn/ui/tabs'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/design/shadcn/ui/tooltip'

const eyebrow =
  'text-[10px] uppercase tracking-widest font-semibold text-muted-foreground'
const eyebrowAccent =
  'text-[10px] uppercase tracking-widest font-semibold text-primary'
const stepOverline =
  'font-mono text-[10px] tabular-nums tracking-widest text-muted-foreground/80'

// Committee seat status → severity rail. Veto = destructive, dissent =
// chart-3 watch, serves = chart-1 success, observes = muted. Matches the
// drift/coverage rail vocabulary used in Message Architecture so the
// preset reads as one system, not three.
type SeatStatus = 'veto' | 'dissent' | 'serves' | 'observes'
const SEAT_STYLE: Record<
  SeatStatus,
  {
    rail: string
    badge: { variant: 'destructive' | 'outline' | 'secondary'; className?: string }
  }
> = {
  veto: {
    rail: 'border-l-destructive/70',
    badge: { variant: 'destructive' },
  },
  dissent: {
    rail: 'border-l-[var(--chart-3)]',
    badge: {
      variant: 'outline',
      className:
        'border-[var(--chart-3)]/50 text-[var(--chart-3)] bg-[var(--chart-3)]/10',
    },
  },
  serves: {
    rail: 'border-l-[var(--chart-1)]',
    badge: {
      variant: 'outline',
      className:
        'border-[var(--chart-1)]/50 text-[var(--chart-1)] bg-[var(--chart-1)]/10',
    },
  },
  observes: {
    rail: 'border-l-muted-foreground/40',
    badge: { variant: 'secondary' },
  },
}

// Finding severity — same vocabulary. Gated = destructive (blocks ship),
// rewrite = chart-3 watch, ready = chart-1 success.
type FindingSeverity = 'gated' | 'rewrite' | 'ready'
const FINDING_STYLE: Record<
  FindingSeverity,
  {
    rail: string
    icon: typeof AlertTriangle
    iconClass: string
    badge: { variant: 'destructive' | 'outline'; className?: string }
  }
> = {
  gated: {
    rail: 'border-l-destructive/70',
    icon: AlertTriangle,
    iconClass: 'text-destructive',
    badge: { variant: 'destructive' },
  },
  rewrite: {
    rail: 'border-l-[var(--chart-3)]',
    icon: AlertTriangle,
    iconClass: 'text-[var(--chart-3)]',
    badge: {
      variant: 'outline',
      className:
        'border-[var(--chart-3)]/50 text-[var(--chart-3)] bg-[var(--chart-3)]/10',
    },
  },
  ready: {
    rail: 'border-l-[var(--chart-1)]',
    icon: CheckCircle2,
    iconClass: 'text-[var(--chart-1)]',
    badge: {
      variant: 'outline',
      className:
        'border-[var(--chart-1)]/50 text-[var(--chart-1)] bg-[var(--chart-1)]/10',
    },
  },
}

export function V14Showcase() {
  return (
    <TooltipProvider delayDuration={200}>
      <SidebarProvider>
        <Sidebar collapsible="icon">
          <SidebarHeader>
            <div className="flex items-center gap-2 px-1 py-1.5">
              <Avatar className="size-7 rounded-md">
                <AvatarFallback className="rounded-md bg-primary text-primary-foreground text-xs font-bold">A</AvatarFallback>
              </Avatar>
              <span className="text-base font-semibold tracking-tight group-data-[collapsible=icon]:hidden">
                ACE
              </span>
            </div>
          </SidebarHeader>

          <SidebarContent>
            <SidebarGroup>
              <SidebarGroupLabel>Workspace</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  <SidebarMenuItem>
                    <SidebarMenuButton tooltip="Vision">
                      <Compass />
                      <span>Vision</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                  <SidebarMenuItem>
                    <SidebarMenuButton isActive tooltip="Brief Composer">
                      <PenLine />
                      <span>Brief Composer</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                  <SidebarMenuItem>
                    <SidebarMenuButton tooltip="Atrium">
                      <Users />
                      <span>Atrium</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                  <SidebarMenuItem>
                    <SidebarMenuButton tooltip="Sentinel">
                      <Eye />
                      <span>Sentinel</span>
                    </SidebarMenuButton>
                    <SidebarMenuBadge>14</SidebarMenuBadge>
                  </SidebarMenuItem>
                  <SidebarMenuItem>
                    <SidebarMenuButton tooltip="Foresight">
                      <Flame />
                      <span>Foresight</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>

            <SidebarGroup>
              <SidebarGroupLabel>Library</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  <SidebarMenuItem>
                    <SidebarMenuButton tooltip="Personas">
                      <Users />
                      <span>Personas</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                  <SidebarMenuItem>
                    <SidebarMenuButton tooltip="Frameworks">
                      <Library />
                      <span>Frameworks</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                  <SidebarMenuItem>
                    <SidebarMenuButton tooltip="Decisions">
                      <Hexagon />
                      <span>Decisions</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                  <SidebarMenuItem>
                    <SidebarMenuButton tooltip="Memory">
                      <ScrollText />
                      <span>Memory</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          </SidebarContent>

          <SidebarFooter>
            <div className="flex items-center gap-2 px-2 py-1.5 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
              <span className="size-1.5 rounded-full bg-primary" />
              <span>Live · internal</span>
            </div>
          </SidebarFooter>
        </Sidebar>

        <SidebarInset>
          <header className="flex items-center gap-3 h-14 px-6 border-b sticky top-0 z-10 bg-background">
            <div className="flex flex-col gap-0.5">
              <div className={eyebrow}>Workspace · Brief Composer</div>
              <div className="text-sm font-semibold tracking-tight">
                page audit · brief · working draft · receipts
              </div>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <Badge variant="outline" className="gap-1.5 font-mono text-[10px] uppercase tracking-widest">
                <span className="size-1.5 rounded-full bg-[var(--chart-1)]" />
                Live
              </Badge>

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon">
                    <Settings />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Workspace settings</TooltipContent>
              </Tooltip>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon">
                    <MoreHorizontal />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuLabel>Brief actions</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem>Duplicate</DropdownMenuItem>
                  <DropdownMenuItem>Share</DropdownMenuItem>
                  <DropdownMenuItem>Export as DOCX</DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive">Delete</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>

              <Sheet>
                <SheetTrigger asChild>
                  <Button variant="outline" size="sm">Run deliberation</Button>
                </SheetTrigger>
                <SheetContent>
                  <SheetHeader>
                    <SheetTitle>Run a full deliberation</SheetTitle>
                    <SheetDescription>
                      Compose the buying committee, walk the Double Diamond, and surface every objection traced to the seat that raised it.
                    </SheetDescription>
                  </SheetHeader>
                  <div className="p-4 space-y-3">
                    <div className="space-y-1.5">
                      <Label htmlFor="src">Source URL</Label>
                      <Input id="src" placeholder="https://www.example.com/products/cloud.html" />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="anchor">Anchor workload</Label>
                      <Input id="anchor" placeholder="e.g. ML training cluster" />
                    </div>
                  </div>
                  <SheetFooter>
                    <Button>Run deliberation</Button>
                  </SheetFooter>
                </SheetContent>
              </Sheet>

              <Dialog>
                <DialogTrigger asChild>
                  <Button size="sm">Open the brief</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Open Brief Composer</DialogTitle>
                    <DialogDescription>
                      The full brief is ready. Confirm to load.
                    </DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <Button variant="outline">Cancel</Button>
                    <Button>Open brief</Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </div>
          </header>

          <ScrollArea className="flex-1">
            <div className="p-6 max-w-5xl mx-auto space-y-6">

              {/* Section eyebrow — sets the JTBD up front: this is the
                  calibration page proving the preset cohere. */}
              <div className="space-y-1">
                <div className={eyebrowAccent}>Preset calibration · b39gyV5NI</div>
                <h2 className="text-xl font-bold tracking-tight">
                  Product chrome, expressed in shadcn primitives
                </h2>
                <p className="text-sm text-muted-foreground leading-snug max-w-2xl">
                  Every move below — verdict-grade chrome, severity rails, mono
                  step overlines, dashed sub-cards — is the same primitive
                  vocabulary the live product pages use. If the preset bends here,
                  it bends everywhere.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <Input
                  placeholder="https://www.example.com/products/cloud.html"
                  className="flex-1"
                />
                <Button>Run B2B audit</Button>
                <Button variant="outline">Run deliberation</Button>
              </div>

              <Alert>
                <Sparkles />
                <AlertTitle>Read as the buying committee</AlertTitle>
                <AlertDescription>
                  12 archetypes anchor the composition. Click any seat to see the
                  lens it reads through.
                </AlertDescription>
              </Alert>

              <Tabs defaultValue="audit">
                <TabsList>
                  <TabsTrigger value="audit">Audit</TabsTrigger>
                  <TabsTrigger value="design">Design</TabsTrigger>
                  <TabsTrigger value="sentinel">Sentinel</TabsTrigger>
                </TabsList>

                <TabsContent value="audit" className="space-y-4">
                  {/* Verdict — primary-surface chrome. This is the single most
                      important node on the page; nothing else competes. Ready
                      sits beside it as a secondary dial with a chart-3 watch
                      rail (18/33 is mid). */}
                  <div className="grid grid-cols-1 md:grid-cols-[1.4fr_1fr] gap-4">
                    <Card className="bg-primary text-primary-foreground ring-primary/30 shadow-md">
                      <CardContent className="space-y-4 py-6 px-6">
                        <div className="flex items-center justify-between gap-3">
                          <span className={cn(stepOverline, 'text-primary-foreground/75')}>
                            00 · Verdict
                          </span>
                          <span className="inline-flex items-center gap-1.5 font-mono text-[9px] tracking-[0.18em] uppercase text-primary-foreground/80">
                            <ShieldCheck aria-hidden className="size-3" />
                            Canonical
                          </span>
                        </div>
                        <div className="space-y-1.5">
                          <div className="font-mono text-3xl font-bold tabular-nums leading-none">
                            54
                            <span className="text-lg text-primary-foreground/70 font-medium">
                              {' '}/ 60
                            </span>
                          </div>
                          <div className="text-[11px] text-primary-foreground/80 leading-snug">
                            Example Cloud — Consumption Cloud · cloud · cross · consideration
                          </div>
                        </div>
                      </CardContent>
                    </Card>

                    <Card size="sm" className="border-l-2 border-l-[var(--chart-3)]">
                      <CardContent className="space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className={stepOverline}>01 · Ready</span>
                          <Badge
                            variant="outline"
                            className="border-[var(--chart-3)]/50 text-[var(--chart-3)] bg-[var(--chart-3)]/10"
                          >
                            watch
                          </Badge>
                        </div>
                        <div className="font-mono text-3xl font-bold tabular-nums leading-none">
                          18
                          <span className="text-lg text-muted-foreground font-medium">
                            {' '}/ 33
                          </span>
                        </div>
                        <div className="text-[11px] text-muted-foreground leading-snug">
                          15 demo patterns blocked behind the accessibility floor.
                        </div>
                      </CardContent>
                    </Card>
                  </div>

                  {/* Buying committee — rail-coded cards instead of a flat
                      table. The seat's status drives the rail color and badge
                      tone so the page reads at a glance. */}
                  <div className="space-y-2">
                    <div className={eyebrow}>Buying committee · five seats anchored</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {AUDIENCE_ROWS.map((row) => (
                        <SeatCard key={row.id} row={row} />
                      ))}
                    </div>
                  </div>
                </TabsContent>

                <TabsContent value="design">
                  <Card>
                    <CardContent className="p-4 space-y-2">
                      <Skeleton className="h-4 w-1/3" />
                      <Skeleton className="h-3 w-1/2" />
                      <div className="flex gap-2 pt-2">
                        <Skeleton className="h-8 w-24 rounded-md" />
                        <Skeleton className="h-8 w-24 rounded-md" />
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="sentinel" className="space-y-3">
                  <div className="space-y-1">
                    <div className={eyebrow}>Latest sweep · three findings</div>
                  </div>
                  {FINDINGS.map((f) => (
                    <FindingCard key={f.id} finding={f} />
                  ))}
                </TabsContent>
              </Tabs>

              {/* Primitive reference — dashed sub-card chrome to read as a
                  derived/inventory leaf node, not authoritative content. */}
              <Card
                size="sm"
                className="border border-dashed border-border bg-muted/20 shadow-none"
              >
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <CardTitle className="text-sm font-semibold flex items-center gap-2">
                      <FileEdit aria-hidden className="size-3.5 text-muted-foreground" />
                      Primitive reference
                    </CardTitle>
                    <span className="font-mono text-[10px] tracking-widest uppercase text-muted-foreground">
                      Every variant
                    </span>
                  </div>
                  <CardDescription className="text-[12px]">
                    The raw primitives this page composes from. No custom-custom.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label className={eyebrow}>Buttons</Label>
                    <div className="flex flex-wrap gap-2">
                      <Button>Primary</Button>
                      <Button variant="outline">Outline</Button>
                      <Button variant="secondary">Secondary</Button>
                      <Button variant="ghost">Ghost</Button>
                      <Button variant="destructive">Destructive</Button>
                      <Button variant="link">Link</Button>
                      <Button size="icon" variant="outline"><Info /></Button>
                      <Button disabled>Disabled</Button>
                    </div>
                  </div>

                  <Separator />

                  <div className="space-y-2">
                    <Label className={eyebrow}>Badges</Label>
                    <div className="flex flex-wrap gap-2">
                      <Badge>Default</Badge>
                      <Badge variant="secondary">Secondary</Badge>
                      <Badge variant="outline">Outline</Badge>
                      <Badge variant="destructive">Destructive</Badge>
                      <Badge
                        variant="outline"
                        className="border-[var(--chart-1)]/50 text-[var(--chart-1)] bg-[var(--chart-1)]/10"
                      >
                        chart-1 · success
                      </Badge>
                      <Badge
                        variant="outline"
                        className="border-[var(--chart-3)]/50 text-[var(--chart-3)] bg-[var(--chart-3)]/10"
                      >
                        chart-3 · watch
                      </Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Closing aside — ties the chrome inventory back to the JTBD. */}
              <aside className="rounded-lg bg-muted/40 border-l-2 border-l-primary/40 px-4 py-3 text-sm text-muted-foreground leading-snug">
                <b className="text-foreground">Verdict</b> takes the primary surface.{' '}
                <b className="text-foreground">Severity</b> drives the rails — destructive,
                chart-3 watch, chart-1 success, muted observe.{' '}
                <b className="text-foreground">Mono step overlines</b> mark ordinals.{' '}
                <b className="text-foreground">Dashed sub-cards</b> read as derived.
                Same vocabulary, every page. The preset bends.
              </aside>

            </div>
          </ScrollArea>
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  )
}

type AudienceRow = {
  id: string
  mark: string
  label: string
  role: string
  status: SeatStatus
  statusLabel: string
  detail: string
}

const AUDIENCE_ROWS: readonly AudienceRow[] = [
  { id: 'cfo', mark: 'C', label: 'CFO Mode', role: 'economic_buyer', status: 'veto', statusLabel: 'Veto', detail: 'Practitioner-curious; needs ROI tied to specific workload.' },
  { id: 'pmm', mark: 'P', label: 'PMM Lead', role: 'champion', status: 'serves', statusLabel: 'Serves', detail: 'Multi-cloud aware; reads consumption-cloud framing as defensive.' },
  { id: 'brand', mark: 'B', label: 'Brand Voice', role: 'user', status: 'dissent', statusLabel: 'Dissents', detail: 'CFO-skeptical of "AI-powered" without specific outcome.' },
  { id: 'risk', mark: 'R', label: 'Risk Officer', role: 'security', status: 'veto', statusLabel: 'Veto', detail: 'Privacy posture stable; auditability gaps remain.' },
  { id: 'sentinel', mark: 'S', label: 'Sentinel', role: 'cross_domain', status: 'observes', statusLabel: 'Observes', detail: 'No findings this sweep.' },
]

type Finding = {
  id: string
  severity: FindingSeverity
  tone: string
  title: string
  detail: string
}

const FINDINGS: readonly Finding[] = [
  { id: '1', severity: 'gated', tone: 'Gated', title: 'Accessibility floor is 0.30 — 0.30 below 0.60 target.', detail: '55 active gaps in error handling, semantic markup, focus management. Blocks 15 demo patterns.' },
  { id: '2', severity: 'rewrite', tone: 'Rewrite', title: 'Observability avg 0.28 with 248 gaps.', detail: 'No structured logging on 18 of 35 critical paths. Telemetry declining (-0.07 this week).' },
  { id: '3', severity: 'ready', tone: 'Ready', title: 'Privacy posture stable — no findings this sweep.', detail: 'Last drift 14 days ago. Cohort encryption + token rotation still passing.' },
]

function SeatCard({ row }: { row: AudienceRow }) {
  const style = SEAT_STYLE[row.status]
  return (
    <Card
      size="sm"
      className={cn('border-l-2 transition-all hover:ring-foreground/15', style.rail)}
    >
      <CardContent className="flex items-start gap-3">
        <Avatar className="size-9 shrink-0 bg-muted">
          <AvatarFallback className="bg-muted text-foreground/70 text-base font-mono">
            {row.mark}
          </AvatarFallback>
        </Avatar>
        <div className="flex flex-col gap-1 min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="text-sm font-semibold leading-tight">{row.label}</div>
            <Badge variant={style.badge.variant} className={style.badge.className}>
              {row.statusLabel}
            </Badge>
          </div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            {row.role}
          </div>
          <p className="text-[12px] text-muted-foreground leading-snug">
            {row.detail}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}

function FindingCard({ finding }: { finding: Finding }) {
  const style = FINDING_STYLE[finding.severity]
  const SeverityIcon = style.icon
  return (
    <Card
      size="sm"
      className={cn('border-l-2 transition-all hover:ring-foreground/15', style.rail)}
    >
      <CardContent className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3 items-start">
        <div className="space-y-2 min-w-0">
          <div className="flex items-center gap-1.5">
            <SeverityIcon aria-hidden className={cn('size-3.5 shrink-0', style.iconClass)} />
            <Badge variant={style.badge.variant} className={style.badge.className}>
              {finding.tone}
            </Badge>
          </div>
          <div className="text-sm font-medium leading-snug">{finding.title}</div>
          <p className="text-[12px] text-muted-foreground leading-snug font-mono tabular-nums">
            {finding.detail}
          </p>
        </div>
        <div className="flex md:flex-col items-end gap-1.5">
          <Button variant="ghost" size="sm" className="gap-1">
            Open
            <ChevronRight aria-hidden className="size-3.5" />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
