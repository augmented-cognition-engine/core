// frontend/src/design/showcase/DesignSystemShowcase.tsx
//
// Visual reference for the ACE design system. Renders every Layer 0–5
// artifact in context: tokens, primitives, behavioral wrappers, and the
// theme override surface.
//
// Routed via `?mode=design-system` from the AppShell.
//
// This page itself MUST eat its own cooking — every component on it
// composes from frontend/src/design/components/, with zero inline
// color / font / spacing / radius / shadow.

import { useState, useEffect } from 'react'
import {
  AcknowledgmentProvider,
  AgentPresenceRow,
  AmbientWorking,
  Aphorism,
  AskInput,
  Avatar,
  Briefing,
  Button,
  Byline,
  Card,
  Checkbox,
  Chip,
  Cluster,
  ContributionLane,
  DecisionCapture,
  Dialog,
  DialogClose,
  Divider,
  EmptyState,
  Eyebrow,
  Frame,
  Glyph,
  Grid,
  HandOff,
  Icon,
  Input,
  LinkButton,
  Menu,
  NorthStarBar,
  Pip,
  Popover,
  ProactiveLine,
  Pushback,
  RosterRow,
  Section,
  Select,
  SeverityFinding,
  Sidebar,
  Sparkline,
  Stack,
  StatusBadge,
  Switch,
  Tabs,
  Textarea,
  Tooltip,
  TooltipProvider,
  VoiceCallout,
  useAcknowledgment,
} from '../components'
import { THEMES, applyTheme } from '../themes'

type CanvasMode = 'dark' | 'light'

export function DesignSystemShowcase() {
  const [mode, setMode] = useState<CanvasMode>('dark')
  const [activeTheme, setActiveTheme] = useState<string>('base')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', mode)
    return () => document.documentElement.removeAttribute('data-theme')
  }, [mode])

  useEffect(() => {
    applyTheme(activeTheme)
  }, [activeTheme])

  return (
    <TooltipProvider>
      <AcknowledgmentProvider>
      <div
        style={{
          minHeight: '100vh',
          background: 'var(--ace-surface-canvas)',
          color: 'var(--ace-ink)',
          fontFamily: 'var(--ace-font-sans)',
          padding: 'var(--ace-space-8)',
          overflowY: 'auto',
        }}
      >
        <div style={{ maxWidth: 1080, margin: '0 auto' }}>
          <Header mode={mode} setMode={setMode} activeTheme={activeTheme} setActiveTheme={setActiveTheme} />

          <FoundationsBlock />
          <ColorBlock />
          <SpacingBlock />
          <TypographyBlock />

          <ShowcaseDivider label="Layer 5 — Presentational primitives" />
          <CardShowcase />
          <ChipShowcase />
          <ButtonShowcase />
          <SmallPrimitivesShowcase />
          <AskInputShowcase />
          <SectionShowcase />

          <ShowcaseDivider label="Layer 5 — Identity primitives" />
          <AvatarShowcase />
          <RosterRowShowcase />
          <NorthStarBarShowcase />
          <SparklineShowcase />
          <StatusBadgeShowcase />

          <ShowcaseDivider label="Layer 4 — Behavioral wrappers (Radix UI)" />
          <TooltipShowcase />
          <PopoverShowcase />
          <DialogShowcase />
          <MenuShowcase />

          <ShowcaseDivider label="Layer 5 — Layout primitives" />
          <StackShowcase />
          <ClusterShowcase />
          <GridShowcase />
          <SidebarShowcase />
          <FrameShowcase />

          <ShowcaseDivider label="Layer 5 — Form primitives" />
          <InputShowcase />
          <TextareaShowcase />
          <SelectShowcase />
          <TabsShowcase />
          <CheckboxShowcase />
          <SwitchShowcase />
          <AcknowledgmentShowcase />

          <ShowcaseDivider label="Layer 5 — Iconography" />
          <IconShowcase />

          <ShowcaseDivider label="Layer 5 — Partnership primitives" />
          <ContributionLaneShowcase />
          <VoiceCalloutShowcase />
          <AgentPresenceRowShowcase />
          <SeverityFindingShowcase />

          <ShowcaseDivider label="Layer 5 — Content-pattern primitives" />
          <PushbackShowcase />
          <ProactiveLineShowcase />
          <EmptyStateShowcase />
          <BriefingShowcase />
          <HandOffShowcase />
          <AmbientWorkingShowcase />
          <DecisionCaptureShowcase />

          <ShowcaseDivider label="Anti-patterns — what NOT to do" />
          <AntiPatternsShowcase />

          <ShowcaseDivider label="Themes" />
          <ThemeRegistryShowcase />

          <div style={{ height: 'var(--ace-space-16)' }} />
        </div>
      </div>
      </AcknowledgmentProvider>
    </TooltipProvider>
  )
}

/* ============================================================================ */
/* Page chrome                                                                  */
/* ============================================================================ */

function Header({
  mode,
  setMode,
  activeTheme,
  setActiveTheme,
}: {
  mode: CanvasMode
  setMode: (m: CanvasMode) => void
  activeTheme: string
  setActiveTheme: (t: string) => void
}) {
  return (
    <header style={{ marginBottom: 'var(--ace-space-10)' }}>
      <Eyebrow>ACE · design system</Eyebrow>
      <h1
        style={{
          margin: 'var(--ace-space-2) 0 var(--ace-space-3)',
          fontFamily: 'var(--ace-font-serif)',
          fontSize: 'var(--ace-text-4xl)',
          fontWeight: 'var(--ace-weight-medium)' as unknown as number,
          letterSpacing: 'var(--ace-track-tight)',
          color: 'var(--ace-ink)',
        }}
      >
        Showcase
      </h1>
      <p
        style={{
          margin: 0,
          maxWidth: 600,
          color: 'var(--ace-ink-soft)',
          fontSize: 'var(--ace-text-lg)',
          lineHeight: 'var(--ace-leading-relaxed)',
        }}
      >
        Every primitive rendered against live tokens. Toggle theme + canvas
        mode to see component tokens propagate. If a component on any other
        surface looks different than what's here, that surface is wrong.
      </p>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--ace-space-4)',
          marginTop: 'var(--ace-space-5)',
          flexWrap: 'wrap',
        }}
      >
        <Eyebrow>Canvas mode</Eyebrow>
        <Chip
          variant={mode === 'dark' ? 'strong' : 'subtle'}
          onClick={() => setMode('dark')}
        >
          Dark
        </Chip>
        <Chip
          variant={mode === 'light' ? 'strong' : 'subtle'}
          onClick={() => setMode('light')}
        >
          Light
        </Chip>
        <span style={{ marginLeft: 'var(--ace-space-4)' }}>
          <Eyebrow>Theme</Eyebrow>
        </span>
        {Object.values(THEMES).map((t) => (
          <Chip
            key={t.id}
            variant={activeTheme === t.id ? 'strong' : 'subtle'}
            onClick={() => setActiveTheme(t.id)}
          >
            {t.label}
          </Chip>
        ))}
      </div>
    </header>
  )
}

function ShowcaseDivider({ label }: { label: string }) {
  return (
    <div style={{ margin: 'var(--ace-space-10) 0 var(--ace-space-6)' }}>
      <Eyebrow>{label}</Eyebrow>
      <Divider />
    </div>
  )
}

function SubsectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3
      style={{
        margin: '0 0 var(--ace-space-3)',
        fontFamily: 'var(--ace-font-serif)',
        fontSize: 'var(--ace-text-xl)',
        fontWeight: 'var(--ace-weight-medium)' as unknown as number,
        letterSpacing: 'var(--ace-track-tight)',
        color: 'var(--ace-ink)',
      }}
    >
      {children}
    </h3>
  )
}

function ShowcaseRow({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--ace-space-4)',
        flexWrap: 'wrap',
        marginBottom: 'var(--ace-space-4)',
      }}
    >
      {children}
    </div>
  )
}

/* ============================================================================ */
/* Tokens                                                                       */
/* ============================================================================ */

function Swatch({ token, label }: { token: string; label?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--ace-space-1)' }}>
      <div
        style={{
          width: 56,
          height: 56,
          background: `var(${token})`,
          border: '1px solid var(--ace-line-soft)',
          borderRadius: 'var(--ace-radius-base)',
        }}
      />
      <div style={{ fontSize: 'var(--ace-text-sm)', color: 'var(--ace-ink-muted)', fontFamily: 'var(--ace-font-mono)' }}>
        {label ?? token.replace('--ace-', '')}
      </div>
    </div>
  )
}

function FoundationsBlock() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-8)' }}>
      <SubsectionTitle>Foundations</SubsectionTitle>
      <Card>
        <div style={{ display: 'grid', gap: 'var(--ace-space-3)', gridTemplateColumns: '160px 1fr' }}>
          <Eyebrow>font-sans</Eyebrow>
          <div style={{ fontFamily: 'var(--ace-font-sans)', fontSize: 'var(--ace-text-lg)' }}>
            The quick brown fox — body text, UI labels, microcopy.
          </div>
          <Eyebrow>font-serif</Eyebrow>
          <div style={{ fontFamily: 'var(--ace-font-serif)', fontSize: 'var(--ace-text-xl)' }}>
            Character bylines and aphorisms — editorial voice.
          </div>
          <Eyebrow>font-mono</Eyebrow>
          <div style={{ fontFamily: 'var(--ace-font-mono)', fontSize: 'var(--ace-text-base)' }}>
            0.82 · 3 lenses · 28d · $0.024
          </div>
          <Eyebrow>base-unit</Eyebrow>
          <div style={{ fontFamily: 'var(--ace-font-mono)' }}>4px — every spacing token is a multiple</div>
          <Eyebrow>radii</Eyebrow>
          <div style={{ display: 'flex', gap: 'var(--ace-space-3)' }}>
            {(['sm', 'base', 'lg', 'pill'] as const).map((r) => (
              <div key={r} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--ace-space-1)' }}>
                <div
                  style={{
                    width: 48,
                    height: 48,
                    background: 'var(--ace-surface-card)',
                    border: '1px solid var(--ace-line)',
                    borderRadius: `var(--ace-radius-${r})`,
                  }}
                />
                <span style={{ fontSize: 'var(--ace-text-sm)', color: 'var(--ace-ink-muted)' }}>{r}</span>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </section>
  )
}

function ColorBlock() {
  const warm = [50, 100, 150, 200, 300, 400, 500, 600, 700, 800, 850, 900, 950]
  const cool = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900]
  return (
    <section style={{ marginBottom: 'var(--ace-space-8)' }}>
      <SubsectionTitle>Color scales (Layer 1)</SubsectionTitle>
      <Card>
        <Eyebrow>warm — default surface family</Eyebrow>
        <div style={{ display: 'flex', gap: 'var(--ace-space-2)', flexWrap: 'wrap', marginTop: 'var(--ace-space-3)' }}>
          {warm.map((n) => (
            <Swatch key={n} token={`--ace-warm-${n}`} label={`warm-${n}`} />
          ))}
        </div>
        <div style={{ height: 'var(--ace-space-4)' }} />
        <Eyebrow>cool — used sparingly for inks</Eyebrow>
        <div style={{ display: 'flex', gap: 'var(--ace-space-2)', flexWrap: 'wrap', marginTop: 'var(--ace-space-3)' }}>
          {cool.map((n) => (
            <Swatch key={n} token={`--ace-cool-${n}`} label={`cool-${n}`} />
          ))}
        </div>
        <div style={{ height: 'var(--ace-space-4)' }} />
        <Eyebrow>semantic — strict-use only</Eyebrow>
        <div style={{ display: 'flex', gap: 'var(--ace-space-2)', marginTop: 'var(--ace-space-3)' }}>
          <Swatch token="--ace-success" />
          <Swatch token="--ace-warning" />
        </div>
      </Card>

      <div style={{ height: 'var(--ace-space-4)' }} />
      <SubsectionTitle>Role tokens (Layer 2)</SubsectionTitle>
      <Card>
        <div style={{ display: 'flex', gap: 'var(--ace-space-2)', flexWrap: 'wrap' }}>
          <Swatch token="--ace-surface-canvas" />
          <Swatch token="--ace-surface-card" />
          <Swatch token="--ace-surface-card-strong" />
          <Swatch token="--ace-surface-card-dim" />
          <Swatch token="--ace-surface-elevated" />
          <Swatch token="--ace-line" />
          <Swatch token="--ace-line-soft" />
          <Swatch token="--ace-line-strong" />
        </div>
      </Card>
    </section>
  )
}

function SpacingBlock() {
  const sizes = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16]
  return (
    <section style={{ marginBottom: 'var(--ace-space-8)' }}>
      <SubsectionTitle>Spacing scale</SubsectionTitle>
      <Card>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--ace-space-2)' }}>
          {sizes.map((n) => (
            <div key={n} style={{ display: 'flex', alignItems: 'center', gap: 'var(--ace-space-3)' }}>
              <span
                style={{
                  fontFamily: 'var(--ace-font-mono)',
                  fontSize: 'var(--ace-text-sm)',
                  color: 'var(--ace-ink-muted)',
                  minWidth: 90,
                }}
              >
                space-{n}
              </span>
              <div
                style={{
                  height: 12,
                  width: `var(--ace-space-${n})`,
                  background: 'var(--ace-ink-soft)',
                  borderRadius: 'var(--ace-radius-sm)',
                }}
              />
            </div>
          ))}
        </div>
      </Card>
    </section>
  )
}

function TypographyBlock() {
  const sizes = ['xs', 'sm', 'base', 'md', 'lg', 'xl', '2xl', '3xl', '4xl'] as const
  return (
    <section style={{ marginBottom: 'var(--ace-space-8)' }}>
      <SubsectionTitle>Typography</SubsectionTitle>
      <Card>
        {sizes.map((s) => (
          <div
            key={s}
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 'var(--ace-space-3)',
              padding: 'var(--ace-space-2) 0',
              borderBottom: '1px solid var(--ace-line-soft)',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--ace-font-mono)',
                fontSize: 'var(--ace-text-sm)',
                color: 'var(--ace-ink-muted)',
                minWidth: 60,
              }}
            >
              text-{s}
            </span>
            <span style={{ fontSize: `var(--ace-text-${s})`, color: 'var(--ace-ink)' }}>
              Intelligence that compounds.
            </span>
          </div>
        ))}
      </Card>
    </section>
  )
}

/* ============================================================================ */
/* Presentational primitives                                                    */
/* ============================================================================ */

function CardShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Card</SubsectionTitle>
      <div style={{ display: 'grid', gap: 'var(--ace-space-3)', gridTemplateColumns: 'repeat(2, 1fr)' }}>
        <Card variant="default">
          <Eyebrow>variant: default</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>The canonical paper card.</div>
        </Card>
        <Card variant="strong" elevated>
          <Eyebrow>variant: strong · elevated</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>The convergence-beat synthesis card.</div>
        </Card>
        <Card variant="dim">
          <Eyebrow>variant: dim</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>Aged paper — the partner moved on.</div>
        </Card>
        <Card variant="subtle" accent="#C26648">
          <Eyebrow>variant: subtle · accent</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>Left-tab accent for discipline identity.</div>
        </Card>
      </div>
    </section>
  )
}

function ChipShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Chip</SubsectionTitle>
      <ShowcaseRow>
        <Chip>subtle (default)</Chip>
        <Chip variant="strong">strong</Chip>
        <Chip variant="ghost">ghost</Chip>
        <Chip tone="#5B7A99">tone: slate-blue</Chip>
        <Chip variant="strong" tone="#8C3A3A">strong · oxblood</Chip>
        <Chip onClick={() => {}}>clickable</Chip>
      </ShowcaseRow>
    </section>
  )
}

function ButtonShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Button</SubsectionTitle>
      <ShowcaseRow>
        <Button variant="primary">Accept</Button>
        <Button variant="secondary">Rerun</Button>
        <Button variant="ghost">Comment</Button>
        <Button variant="secondary" size="sm">Add perspective</Button>
        <Button variant="primary" disabled>Disabled</Button>
        <LinkButton href="#" external={false}>Link button</LinkButton>
      </ShowcaseRow>
    </section>
  )
}

function SmallPrimitivesShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Small primitives</SubsectionTitle>
      <ShowcaseRow>
        <span>
          <Eyebrow>eyebrow</Eyebrow> tiny uppercase label
        </span>
        <Pip tone="#5F7A4F" />
        <Pip tone="#C26648" size="md" />
        <Glyph lens="ux" />
        <Glyph lens="architecture" size="lg" />
      </ShowcaseRow>
      <Byline>The editorial conscience — italic serif role line.</Byline>
      <div style={{ height: 'var(--ace-space-3)' }} />
      <Aphorism>
        AI shouldn't be operated — it should be partnered with.
      </Aphorism>
    </section>
  )
}

function AskInputShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>AskInput</SubsectionTitle>
      <AskInput label="Ask the team" placeholder="What should we look at?" onSubmit={() => {}} />
    </section>
  )
}

function SectionShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Section</SubsectionTitle>
      <Section
        title="UX"
        byline="The editorial conscience"
        lens="ux"
        statusLabel="FRAME · 0.82"
        status="active"
      >
        Section body — a lens's contribution sits inside this container.
        Header carries the discipline byline, status badge sits flush right,
        body is editorial-density text.
      </Section>
    </section>
  )
}

/* ============================================================================ */
/* Identity primitives                                                          */
/* ============================================================================ */

function AvatarShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Avatar</SubsectionTitle>
      <ShowcaseRow>
        <Avatar lens="ux" size="sm" />
        <Avatar lens="ux" />
        <Avatar lens="ux" size="lg" />
        <Avatar lens="security" />
        <Avatar lens="data" />
        <Avatar lens="product_strategy" />
      </ShowcaseRow>
    </section>
  )
}

function RosterRowShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>RosterRow</SubsectionTitle>
      <RosterRow lenses={['ux', 'security', 'data', 'architecture', 'product_strategy']} />
    </section>
  )
}

function NorthStarBarShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>NorthStarBar</SubsectionTitle>
      <div style={{ marginLeft: 'calc(-1 * var(--ace-space-8))', marginRight: 'calc(-1 * var(--ace-space-8))' }}>
        <NorthStarBar
          goal="Make ACE the obvious choice for partnership-shaped AI"
          okr="OKR · 3 design partners by EOQ"
        />
      </div>
    </section>
  )
}

function SparklineShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Sparkline</SubsectionTitle>
      <ShowcaseRow>
        <Sparkline values={[0.62, 0.68, 0.71, 0.74, 0.78, 0.81, 0.83]} />
        <Sparkline values={[0.4, 0.5, 0.3, 0.6, 0.4, 0.55, 0.5]} />
        <Sparkline values={[0.2, 0.4, 0.6, 0.8, 1.0]} />
      </ShowcaseRow>
    </section>
  )
}

function StatusBadgeShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>StatusBadge</SubsectionTitle>
      <ShowcaseRow>
        <StatusBadge label="FRAME · 0.82" />
        <StatusBadge label="preparing…" dim />
        <StatusBadge label="RECOMMEND" tone="var(--ace-success)" />
        <StatusBadge label="REWORK" tone="var(--ace-warning)" />
        <StatusBadge label="ARCH" tone="#5B7A99" />
      </ShowcaseRow>
    </section>
  )
}

/* ============================================================================ */
/* Behavioral wrappers (Radix)                                                  */
/* ============================================================================ */

function TooltipShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Tooltip (Radix)</SubsectionTitle>
      <ShowcaseRow>
        <Tooltip content="UX — Editorial Conscience">
          <Avatar lens="ux" />
        </Tooltip>
        <Tooltip content="Security — System Reliability">
          <Avatar lens="security" />
        </Tooltip>
        <Tooltip content="Hover or focus me" side="right">
          <Button variant="secondary">Hover me</Button>
        </Tooltip>
      </ShowcaseRow>
    </section>
  )
}

function PopoverShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Popover (Radix)</SubsectionTitle>
      <ShowcaseRow>
        <Popover
          content={
            <div>
              <AskInput
                label="comment"
                placeholder="Tell the partner what's missing..."
                onSubmit={() => {}}
              />
            </div>
          }
        >
          <Button variant="ghost">Comment</Button>
        </Popover>
        <Popover
          content={
            <div>
              <Aphorism>The arrow that sketches in only when the synthesis lands.</Aphorism>
              <Byline>The editorial conscience</Byline>
            </div>
          }
          side="right"
        >
          <Button variant="secondary">Show quote</Button>
        </Popover>
      </ShowcaseRow>
    </section>
  )
}

function DialogShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Dialog (Radix)</SubsectionTitle>
      <ShowcaseRow>
        <Dialog
          trigger={<Button variant="secondary">Preview memory</Button>}
          title="Memory captured"
          description="L7 noticed a recurring pattern in this deliberation that's worth keeping."
        >
          <Card variant="strong">
            <Eyebrow>pattern</Eyebrow>
            <div style={{ marginTop: 'var(--ace-space-2)' }}>
              "Every time we rerun UX after Security weighs in, the synthesis converges faster."
            </div>
          </Card>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--ace-space-2)', marginTop: 'var(--ace-space-4)' }}>
            <DialogClose>
              <Button variant="ghost">Not now</Button>
            </DialogClose>
            <DialogClose>
              <Button variant="primary">Keep it</Button>
            </DialogClose>
          </div>
        </Dialog>
      </ShowcaseRow>
    </section>
  )
}

function MenuShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Menu (Radix)</SubsectionTitle>
      <ShowcaseRow>
        <Menu
          trigger={<Button variant="secondary">More</Button>}
          items={[
            { type: 'label', label: 'Continue the conversation' },
            { id: 'comment', label: 'Comment', onSelect: () => {}, hint: 'C' },
            { id: 'rerun', label: 'Rerun this lens', onSelect: () => {}, hint: 'R' },
            { id: 'add', label: 'Add perspective', onSelect: () => {} },
            { type: 'separator' },
            { id: 'branch', label: 'Branch from here', onSelect: () => {} },
            { id: 'archive', label: 'Archive', onSelect: () => {}, disabled: true },
          ]}
        />
      </ShowcaseRow>
    </section>
  )
}

/* ============================================================================ */
/* Theme registry                                                               */
/* ============================================================================ */

function ThemeRegistryShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Theme registry</SubsectionTitle>
      <p style={{ color: 'var(--ace-ink-soft)', maxWidth: 600, lineHeight: 'var(--ace-leading-relaxed)', margin: 0 }}>
        Themes override Layer 2 / 3 tokens at `:root`. Toggle one from the
        header to retune every component on the page without touching its code.
      </p>
      <div style={{ height: 'var(--ace-space-4)' }} />
      <div style={{ display: 'grid', gap: 'var(--ace-space-3)', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
        {Object.values(THEMES).map((t) => (
          <Card key={t.id}>
            <Eyebrow>{t.id}</Eyebrow>
            <div style={{ marginTop: 'var(--ace-space-2)', fontSize: 'var(--ace-text-lg)' }}>{t.label}</div>
            <div style={{ marginTop: 'var(--ace-space-1)', color: 'var(--ace-ink-soft)', fontSize: 'var(--ace-text-sm)' }}>
              {t.tokens === undefined || Object.keys(t.tokens).length === 0
                ? 'No overrides — pure base.'
                : `${Object.keys(t.tokens).length} token override${Object.keys(t.tokens).length === 1 ? '' : 's'}.`}
            </div>
          </Card>
        ))}
      </div>
    </section>
  )
}

/* ============================================================================ */
/* Layer 5 — Layout primitives                                                  */
/* ============================================================================ */

function StackShowcase() {
  const placeholder = (label: string) => (
    <div
      style={{
        padding: 'var(--ace-space-3) var(--ace-space-4)',
        background: 'var(--ace-surface-recessed)',
        borderRadius: 'var(--ace-radius-base)',
        fontFamily: 'var(--ace-font-mono)',
        fontSize: 'var(--ace-text-sm)',
        color: 'var(--ace-ink-soft)',
      }}
    >
      {label}
    </div>
  )
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Stack — vertical / horizontal flex</SubsectionTitle>
      <ShowcaseRow>
        <Card padding="md">
          <Eyebrow>vertical, gap 3</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', width: 200 }}>
            <Stack direction="vertical" gap={3}>
              {placeholder('one')}
              {placeholder('two')}
              {placeholder('three')}
            </Stack>
          </div>
        </Card>
        <Card padding="md">
          <Eyebrow>horizontal, gap 2, between</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', width: 300 }}>
            <Stack direction="horizontal" gap={2} justify="between">
              {placeholder('left')}
              {placeholder('right')}
            </Stack>
          </div>
        </Card>
      </ShowcaseRow>
    </section>
  )
}

function ClusterShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Cluster — horizontal flex with wrap</SubsectionTitle>
      <ShowcaseRow>
        <Card padding="md">
          <Eyebrow>chips that wrap</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', width: 300 }}>
            <Cluster gap={2}>
              <Chip>architecture</Chip>
              <Chip>security</Chip>
              <Chip>data</Chip>
              <Chip>ux</Chip>
              <Chip>performance</Chip>
              <Chip>compliance</Chip>
            </Cluster>
          </div>
        </Card>
      </ShowcaseRow>
    </section>
  )
}

function GridShowcase() {
  const tile = (n: number) => (
    <div
      style={{
        padding: 'var(--ace-space-4)',
        background: 'var(--ace-surface-recessed)',
        borderRadius: 'var(--ace-radius-base)',
        textAlign: 'center',
        fontFamily: 'var(--ace-font-mono)',
        color: 'var(--ace-ink-soft)',
      }}
    >
      {n}
    </div>
  )
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Grid — equal cols + auto-fit responsive</SubsectionTitle>
      <ShowcaseRow>
        <Card padding="md">
          <Eyebrow>columns=3, gap 3</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', width: 320 }}>
            <Grid columns={3} gap={3}>
              {tile(1)}
              {tile(2)}
              {tile(3)}
            </Grid>
          </div>
        </Card>
        <Card padding="md">
          <Eyebrow>minColumnWidth=120, auto-fit</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', width: 400 }}>
            <Grid minColumnWidth={120} gap={3}>
              {tile(1)}
              {tile(2)}
              {tile(3)}
              {tile(4)}
            </Grid>
          </div>
        </Card>
      </ShowcaseRow>
    </section>
  )
}

function SidebarShowcase() {
  const block = (label: string, bg: string) => (
    <div
      style={{
        padding: 'var(--ace-space-3)',
        background: bg,
        borderRadius: 'var(--ace-radius-base)',
        fontFamily: 'var(--ace-font-mono)',
        fontSize: 'var(--ace-text-sm)',
        color: 'var(--ace-ink-soft)',
        textAlign: 'center',
      }}
    >
      {label}
    </div>
  )
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Sidebar — fixed-width rail + flexible main</SubsectionTitle>
      <ShowcaseRow>
        <Card padding="md">
          <Eyebrow>side=left, width 120</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', width: 420 }}>
            <Sidebar
              side="left"
              width={120}
              sidebar={block('sidebar', 'var(--ace-surface-tint)')}
              main={block('main content', 'var(--ace-surface-recessed)')}
            />
          </div>
        </Card>
      </ShowcaseRow>
    </section>
  )
}

function FrameShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Frame — constrained container with surface tone</SubsectionTitle>
      <ShowcaseRow>
        <Frame maxWidth={400} padding={4} surface="raised">
          <div style={{ fontFamily: 'var(--ace-font-serif)', color: 'var(--ace-ink-soft)' }}>
            maxWidth=400, padding=4, surface=raised. Frame is the outermost
            container of a reading column or section — caps width, applies
            padding, optionally renders a surface tone.
          </div>
        </Frame>
      </ShowcaseRow>
    </section>
  )
}

/* ============================================================================ */
/* Layer 5 — Form primitives                                                    */
/* ============================================================================ */

function InputShowcase() {
  const [a, setA] = useState('')
  const [b, setB] = useState('search query')
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Input — controlled text, variants × sizes</SubsectionTitle>
      <ShowcaseRow>
        <Card padding="md">
          <Eyebrow>default · md</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', width: 280 }}>
            <Input value={a} onChange={setA} placeholder="type here…" ariaLabel="demo" />
          </div>
        </Card>
        <Card padding="md">
          <Eyebrow>quiet · sm</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', width: 220 }}>
            <Input value={b} onChange={setB} variant="quiet" size="sm" placeholder="search" ariaLabel="demo" />
          </div>
        </Card>
        <Card padding="md">
          <Eyebrow>inline · md</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', width: 220 }}>
            <Input value="" onChange={() => {}} variant="inline" placeholder="editable inline…" ariaLabel="demo" />
          </div>
        </Card>
      </ShowcaseRow>
    </section>
  )
}

function TextareaShowcase() {
  const [t, setT] = useState('Multiline composer. Cmd/Ctrl+Enter to submit, plain Enter inserts a newline. AutoGrow expands height to fit.')
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Textarea — multiline, autoGrow</SubsectionTitle>
      <ShowcaseRow>
        <Card padding="md">
          <Eyebrow>default · autoGrow</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', width: 360 }}>
            <Textarea value={t} onChange={setT} autoGrow maxRows={6} ariaLabel="demo" />
          </div>
        </Card>
      </ShowcaseRow>
    </section>
  )
}

/* ============================================================================ */
/* Layer 5 — Partnership primitives                                             */
/* ============================================================================ */

function ContributionLaneShowcase() {
  const VOICE = { speaker: 'architecture', accent: '#5B7A99' }
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>ContributionLane — voice-in-rail, state variants</SubsectionTitle>
      <ShowcaseRow>
        <div style={{ width: 320 }}>
          <Eyebrow>state=active</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <ContributionLane voice={VOICE} state="active" landedAt="just now">
              The cleanest path is to lock the contract first — every layer downstream depends on it.
            </ContributionLane>
          </div>
        </div>
        <div style={{ width: 320 }}>
          <Eyebrow>state=in-flight</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <ContributionLane voice={VOICE} state="in-flight" thinkingAbout="boundary cases">
              I'm reading the spec right now…
            </ContributionLane>
          </div>
        </div>
        <div style={{ width: 320 }}>
          <Eyebrow>state=placeholder</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <ContributionLane voice={VOICE} state="placeholder">
              <span style={{ fontStyle: 'italic', color: 'var(--ace-ink-muted)' }}>not yet</span>
            </ContributionLane>
          </div>
        </div>
      </ShowcaseRow>
    </section>
  )
}

function VoiceCalloutShowcase() {
  const FROM = { speaker: 'security', accent: '#8C3A3A', initial: 'S' }
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>VoiceCallout — voice-addressing-you</SubsectionTitle>
      <ShowcaseRow>
        <div style={{ width: 520 }}>
          <Eyebrow>tone=question</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <VoiceCallout
              from={FROM}
              tone="question"
              askedAt="just now"
              triggeredBy="JWT rotation policy mentioned"
              question={<>We didn't talk about token rotation — is 30 days the right cadence here, or should we tighten?</>}
            />
          </div>
        </div>
      </ShowcaseRow>
    </section>
  )
}

function AgentPresenceRowShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>AgentPresenceRow — voice-in-motion</SubsectionTitle>
      <ShowcaseRow>
        <div style={{ width: 320 }}>
          <Eyebrow>tone=active</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <AgentPresenceRow
              lens="architecture"
              accent="#5B7A99"
              activity="reading the boundary spec"
              avatar={<Avatar lens="architecture" size="sm" />}
            />
          </div>
        </div>
        <div style={{ width: 320 }}>
          <Eyebrow>tone=dim</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <AgentPresenceRow
              lens="security"
              accent="#8C3A3A"
              activity="quiet — waiting on the next pass"
              tone="dim"
              avatar={<Avatar lens="security" size="sm" />}
            />
          </div>
        </div>
      </ShowcaseRow>
    </section>
  )
}

function SeverityFindingShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>SeverityFinding — severity rank</SubsectionTitle>
      <ShowcaseRow>
        <div style={{ width: 360 }}>
          <Eyebrow>severity=high</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <SeverityFinding
              severity="high"
              headline="Auth middleware writes session tokens to disk"
              detail="Compliance flagged this in the Tuesday review."
              meta="OKR · compliance"
            />
          </div>
        </div>
        <div style={{ width: 360 }}>
          <Eyebrow>severity=medium</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <SeverityFinding
              severity="medium"
              headline="Cache hit rate dipped below baseline"
              detail="Sustained 71% for the last 4 hours."
              meta="OKR · performance"
            />
          </div>
        </div>
        <div style={{ width: 360 }}>
          <Eyebrow>severity=low</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <SeverityFinding severity="low" headline="All boundary tests pass on this commit." />
          </div>
        </div>
      </ShowcaseRow>
    </section>
  )
}

/* ============================================================================ */
/* Layer 5 — Content-pattern primitives                                         */
/* ============================================================================ */

function PushbackShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Pushback — voice disagreeing</SubsectionTitle>
      <ShowcaseRow>
        <div style={{ width: 520 }}>
          <Pushback
            from={{ speaker: 'architecture', accent: '#5B7A99', initial: 'A' }}
            disagreement="I'd push back here"
            reference="we agreed boundary tests stay green before merge"
            question="Want me to add the missing test before we land this?"
            askedAt="just now"
          />
        </div>
      </ShowcaseRow>
    </section>
  )
}

function ProactiveLineShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>ProactiveLine — observation + optional offer</SubsectionTitle>
      <ShowcaseRow>
        <div style={{ width: 520 }}>
          <Eyebrow>tone=observation</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <ProactiveLine observation="We've made 4 architecture decisions this week — 2 reversible, 2 not." />
          </div>
        </div>
        <div style={{ width: 520, marginTop: 'var(--ace-space-3)' }}>
          <Eyebrow>tone=offer</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <ProactiveLine
              tone="offer"
              observation="The boundary test is missing for the new auth path."
              offer="Want me to draft it?"
            />
          </div>
        </div>
      </ShowcaseRow>
    </section>
  )
}

function EmptyStateShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>EmptyState — partnership-voice empty</SubsectionTitle>
      <ShowcaseRow>
        <Card padding="none">
          <div style={{ width: 480 }}>
            <EmptyState />
          </div>
        </Card>
      </ShowcaseRow>
    </section>
  )
}

function BriefingShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Briefing — long-form partner-voice artifact</SubsectionTitle>
      <ShowcaseRow>
        <Card padding="none" variant="default">
          <Briefing period="Since you stepped away" title="Two threads worth your attention">
            <p style={{ margin: 0 }}>
              We had a productive run on the auth boundary — the architecture
              lens locked the new contract, security signed off, and the
              boundary tests are passing.
            </p>
            <p style={{ margin: 0 }}>
              One open thread: the JWT rotation cadence. We didn't decide.
              I'd suggest 14 days; want to talk it through?
            </p>
          </Briefing>
        </Card>
      </ShowcaseRow>
    </section>
  )
}

function HandOffShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>HandOff — dispatch phases (announce / running / summary)</SubsectionTitle>
      <ShowcaseRow>
        <div style={{ width: 520 }}>
          <Stack gap={3}>
            <HandOff
              phase="announce"
              to="claude-code"
              message="…to draft the boundary test and run it against the new contract."
            />
            <HandOff
              phase="running"
              to="claude-code"
              message="Reading the spec → drafting the test → running."
            />
            <HandOff
              phase="summary"
              to="claude-code"
              message="Test drafted and passing. Want me to open the PR?"
            >
              <Button variant="primary" size="sm">Open the PR</Button>
              <Button variant="secondary" size="sm">Show me the diff</Button>
            </HandOff>
          </Stack>
        </div>
      </ShowcaseRow>
    </section>
  )
}

function AmbientWorkingShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>AmbientWorking — presence, not summoning</SubsectionTitle>
      <ShowcaseRow>
        <Card padding="md">
          <Eyebrow>silent (dot only)</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <AmbientWorking />
          </div>
        </Card>
        <Card padding="md">
          <Eyebrow>with activity</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <AmbientWorking activity="reading the spec" />
          </div>
        </Card>
        <Card padding="md">
          <Eyebrow>discipline accent</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <AmbientWorking accent="#5B7A99" activity="architecture is thinking it through" size="prominent" />
          </div>
        </Card>
      </ShowcaseRow>
    </section>
  )
}

function DecisionCaptureShowcase() {
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>DecisionCapture — recognized inline</SubsectionTitle>
      <ShowcaseRow>
        <div style={{ width: 480 }}>
          <Eyebrow>source=recognized</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <DecisionCapture
              source="recognized"
              decision="JWT tokens rotate every 14 days; refresh tokens last 30."
              provenance="from the auth boundary conversation, 11 min ago"
            >
              <Button variant="secondary" size="sm">amend</Button>
              <Button variant="ghost" size="sm">challenge</Button>
            </DecisionCapture>
          </div>
        </div>
      </ShowcaseRow>
    </section>
  )
}

/* ============================================================================ */
/* Anti-patterns — what NOT to do                                               */
/* ============================================================================ */

function AntiPatternsShowcase() {
  const item = (wrong: string, right: string) => (
    <Card padding="md">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--ace-space-2)' }}>
        <div style={{ fontFamily: 'var(--ace-font-mono)', fontSize: 'var(--ace-text-sm)', color: 'var(--ace-warning)' }}>
          ✗ {wrong}
        </div>
        <div style={{ fontFamily: 'var(--ace-font-mono)', fontSize: 'var(--ace-text-sm)', color: 'var(--ace-success)' }}>
          ✓ {right}
        </div>
      </div>
    </Card>
  )
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <Stack gap={3}>
        {item(
          "style={{ borderLeft: `2px solid ${accent}` }}",
          'Use ContributionLane / VoiceCallout / AgentPresenceRow / SeverityFinding',
        )}
        {item('<input type="text" />', '<Input value={x} onChange={setX} />')}
        {item('<button onClick={...}>Send</button>', '<Button variant="primary" onClick={...}>Send</Button>')}
        {item("style={{ color: '#0070F3' }}", "style={{ color: 'var(--ace-accent)' }}")}
        {item('"Loading..."', '<AmbientWorking activity="reading the spec" />')}
        {item('"Welcome! Get started"', '<EmptyState />  /* prompts "Tell me what we\'re building together" */')}
        {item('toast.error("Operation failed")', '<Pushback from={...} disagreement="I\'d push back" reference="..." />')}
        {item('✨ AI-powered analysis', 'No emoji. No "AI-powered" framing. Partner voice in serif prose.')}
      </Stack>
    </section>
  )
}

/* ============================================================================ */
/* Form primitives — Radix-wrapped                                              */
/* ============================================================================ */

function SelectShowcase() {
  const [v, setV] = useState<string | undefined>('committee')
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Select (Radix)</SubsectionTitle>
      <ShowcaseRow>
        <Card padding="md">
          <Eyebrow>Recipe</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', width: 240 }}>
            <Select
              value={v}
              onChange={setV}
              ariaLabel="Recipe"
              options={[
                { value: 'committee', label: 'Deep committee', hint: 'Opus' },
                { value: 'fast', label: 'Fast review', hint: 'Sonnet' },
                { value: 'solo', label: 'Solo lens', hint: 'Haiku' },
              ]}
            />
          </div>
        </Card>
      </ShowcaseRow>
    </section>
  )
}

function TabsShowcase() {
  const [tab, setTab] = useState('overview')
  const [pillTab, setPillTab] = useState('a')
  const [underTab, setUnderTab] = useState('one')
  const panel = (label: string) => (
    <div style={{ fontFamily: 'var(--ace-font-serif)', color: 'var(--ace-ink-soft)' }}>
      {label} panel content. Renders only when this tab is active.
    </div>
  )
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Tabs (Radix) — variants</SubsectionTitle>
      <ShowcaseRow>
        <div style={{ width: 360 }}>
          <Eyebrow>default</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <Tabs
              activeTab={tab}
              onTabChange={setTab}
              tabs={[
                { id: 'overview', label: 'Overview', content: panel('Overview') },
                { id: 'details', label: 'Details', hint: '⌘D', content: panel('Details') },
                { id: 'history', label: 'History', content: panel('History') },
              ]}
            />
          </div>
        </div>
        <div style={{ width: 360 }}>
          <Eyebrow>pill</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <Tabs
              variant="pill"
              activeTab={pillTab}
              onTabChange={setPillTab}
              tabs={[
                { id: 'a', label: 'Recipes', content: panel('Recipes') },
                { id: 'b', label: 'Extensions', content: panel('Extensions') },
              ]}
            />
          </div>
        </div>
        <div style={{ width: 360 }}>
          <Eyebrow>underline</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)' }}>
            <Tabs
              variant="underline"
              activeTab={underTab}
              onTabChange={setUnderTab}
              tabs={[
                { id: 'one', label: 'First', content: panel('First') },
                { id: 'two', label: 'Second', content: panel('Second') },
                { id: 'three', label: 'Third', content: panel('Third') },
              ]}
            />
          </div>
        </div>
      </ShowcaseRow>
    </section>
  )
}

function CheckboxShowcase() {
  const [a, setA] = useState(true)
  const [b, setB] = useState(false)
  const [card, setCard] = useState(false)
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Checkbox (Radix) — variants</SubsectionTitle>
      <ShowcaseRow>
        <Card padding="md">
          <Eyebrow>default with description</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', display: 'flex', flexDirection: 'column', gap: 'var(--ace-space-3)' }}>
            <Checkbox
              checked={a}
              onChange={setA}
              label="Surface proactive line"
              description="ACE will volunteer observations when something looks worth your attention."
            />
            <Checkbox
              checked={b}
              onChange={setB}
              label="Show calibration sparkline"
              description="Renders a small chart of prediction accuracy over the last 30 sessions."
            />
          </div>
        </Card>
        <Card padding="md">
          <Eyebrow>card variant</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', width: 280 }}>
            <Checkbox
              variant="card"
              checked={card}
              onChange={setCard}
              label="Deep committee"
              description="Five lenses deliberate; takes ~90s. Opus model."
            />
          </div>
        </Card>
      </ShowcaseRow>
    </section>
  )
}

function SwitchShowcase() {
  const [a, setA] = useState(true)
  const [b, setB] = useState(false)
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Switch (Radix)</SubsectionTitle>
      <ShowcaseRow>
        <Card padding="md">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--ace-space-3)' }}>
            <Switch
              checked={a}
              onChange={setA}
              label="Ambient mode"
              description="Lets ACE keep watching while you're away. Turn off if you want strictly synchronous work."
            />
            <Switch
              checked={b}
              onChange={setB}
              label="Dispatch confirmations"
              description="Ask before sending work to claude-code, codex, cursor."
            />
          </div>
        </Card>
      </ShowcaseRow>
    </section>
  )
}

/* ============================================================================ */
/* Acknowledgment — programmatic record primitive                               */
/* ============================================================================ */

function AcknowledgmentShowcase() {
  const acknowledge = useAcknowledgment()
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Acknowledgment — programmatic record</SubsectionTitle>
      <ShowcaseRow>
        <Card padding="md">
          <Eyebrow>fire one</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', display: 'flex', gap: 'var(--ace-space-2)', flexWrap: 'wrap' }}>
            <Button
              variant="secondary"
              size="md"
              onClick={() =>
                acknowledge({
                  title: 'Decision spotted',
                  description: 'JWT rotation set to 14 days.',
                })
              }
            >
              record a decision
            </Button>
            <Button
              variant="secondary"
              size="md"
              onClick={() =>
                acknowledge({
                  title: 'Spec drafted',
                  description: 'Auth boundary spec written; tests pending.',
                  tone: 'positive',
                })
              }
            >
              record a milestone
            </Button>
          </div>
        </Card>
      </ShowcaseRow>
    </section>
  )
}

/* ============================================================================ */
/* Iconography — curated Phosphor set                                           */
/* ============================================================================ */

function IconShowcase() {
  const names = [
    'arrow-left',
    'arrow-right',
    'caret-down',
    'caret-up',
    'chat',
    'check',
    'close',
    'eye',
    'gear',
    'info',
    'menu-dots',
    'minus',
    'plus',
    'question',
    'search',
    'warning-circle',
  ] as const
  return (
    <section style={{ marginBottom: 'var(--ace-space-6)' }}>
      <SubsectionTitle>Icon — curated set, ACE size + tone</SubsectionTitle>
      <ShowcaseRow>
        <Card padding="md">
          <Eyebrow>sizes</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', display: 'flex', gap: 'var(--ace-space-3)', alignItems: 'center' }}>
            <Icon name="check" size="sm" />
            <Icon name="check" size="md" />
            <Icon name="check" size="lg" />
          </div>
        </Card>
        <Card padding="md">
          <Eyebrow>tones</Eyebrow>
          <div style={{ marginTop: 'var(--ace-space-2)', display: 'flex', gap: 'var(--ace-space-3)', alignItems: 'center' }}>
            <Icon name="info" tone="default" />
            <Icon name="info" tone="soft" />
            <Icon name="info" tone="muted" />
            <Icon name="info" tone="accent" />
            <Icon name="warning-circle" tone="warning" />
            <Icon name="warning-circle" tone="danger" />
            <Icon name="check" tone="success" />
          </div>
        </Card>
      </ShowcaseRow>
      <ShowcaseRow>
        <Card padding="md">
          <Eyebrow>full curated set</Eyebrow>
          <div
            style={{
              marginTop: 'var(--ace-space-2)',
              display: 'grid',
              gridTemplateColumns: 'repeat(8, 1fr)',
              gap: 'var(--ace-space-3)',
              maxWidth: 560,
            }}
          >
            {names.map((n) => (
              <div
                key={n}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 4,
                  padding: 'var(--ace-space-2)',
                  background: 'var(--ace-surface-recessed)',
                  borderRadius: 'var(--ace-radius-sm)',
                }}
              >
                <Icon name={n} size="md" tone="soft" />
                <span
                  style={{
                    fontFamily: 'var(--ace-font-mono)',
                    fontSize: 9,
                    color: 'var(--ace-ink-muted)',
                  }}
                >
                  {n}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </ShowcaseRow>
    </section>
  )
}
