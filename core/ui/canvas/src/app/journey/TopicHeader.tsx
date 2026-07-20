// app/journey/TopicHeader.tsx
//
// L1 + L2 surface — the question being deliberated. The classification
// metadata (discipline / task type / mode / archetype / complexity /
// depth / orchestra) is no longer dumped as visible chips — it lives
// behind a single "Context" popover so the user sees the topic, not the
// classifier internals.
import {
  Brain,
  CircleNotch,
  Cloud,
  Code,
  Database,
  LinkSimple,
  Toolbox,
} from '@phosphor-icons/react'

import { Aphorism, ScoreHero } from '@/design/components'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/design/shadcn/ui/popover'

import type { JourneyClassification, JourneyStage, JourneyTool } from '../../types/canvas'
import { MetaSkillAvatar } from './MetaSkillAvatar'

const TOOL_CATEGORY_LABEL: Record<JourneyTool['category'], string> = {
  ace: 'ACE substrate',
  code: 'codebase',
  web: 'web',
  data: 'data',
  external: 'external',
}

const TOOL_CATEGORY_ICON: Record<JourneyTool['category'], React.ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>> = {
  ace: Brain as unknown as React.ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
  code: Code as unknown as React.ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
  web: Cloud as unknown as React.ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
  data: Database as unknown as React.ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
  external: LinkSimple as unknown as React.ComponentType<{ size?: number; weight?: 'regular' | 'fill' | 'bold' | 'duotone'; className?: string }>,
}

interface TopicHeaderProps {
  topic: string
  classification: JourneyClassification
  /** Optional per–meta-skill matched signals for the orchestra tooltips. */
  matchedSignalsByMetaSkill?: Record<string, string[]>
  /** Full stage list — drives the page-fact (stage N of M) and italic
   *  clause (current stage subtitle). When omitted, hero collapses to
   *  topic + status row only. */
  stages?: JourneyStage[]
}

const DISCIPLINE_BLURB: Record<string, string> = {
  product_strategy: 'product positioning, market direction, growth strategy',
  ux: 'user experience, design, interaction',
  architecture: 'system structure, boundaries, scale',
  security: 'threats, vulnerabilities, controls',
  testing: 'quality, regression, verification',
}

const TASK_BLURB: Record<string, string> = {
  plan: 'sequencing, dependencies, risk-ordered execution',
  build: 'implementation work — produce a concrete artifact',
  review: 'evaluate against a quality bar',
  debug: 'diagnose and resolve a defect',
  design: 'shape an artifact or interaction',
  research: 'gather, synthesize, form a hypothesis',
  analyze: 'decompose, evaluate evidence, draw conclusions',
}

const MODE_BLURB: Record<string, string> = {
  deliberative: 'reason carefully before committing; consider alternatives',
  reactive: 'pattern-match from established knowledge; respond directly',
  reflective: 'assess output quality; score confidence honestly',
  exploratory: 'generate possibilities before evaluating',
  conversational: 'dialogue; ask when ambiguous',
  procedural: 'follow established procedure step by step',
}

const ARCHETYPE_BLURB: Record<string, string> = {
  advisor: 'present tradeoffs explicitly; own the recommendation',
  analyst: 'work from evidence; hold conclusions proportional',
  creator: 'generate novel solutions; explore the solution space',
  executor: 'execute the defined task precisely',
  researcher: 'map territory; cast wide before narrowing',
  sentinel: 'look for what is wrong; rank findings by impact',
}

const META_SKILL_BLURB: Record<string, string> = {
  strategic_intelligence: 'product-strategy fit, leverage analysis, optionality',
  risk_intelligence: 'FMEA failure modes, reversibility, blast radius',
  planning_intelligence: 'dependency mapping, risk-first ordering, parallelization',
  communication_intelligence: 'audience modeling, framing, granularity',
  domain_specific_intelligence: 'discipline + specialty grounding',
  creative_intelligence: 'aesthetic direction, value prioritization, conjoint validation',
  coding_intelligence: 'constraints, tradeoffs, design pattern selection',
  systems_intelligence: 'scaling architecture, capacity planning, failure cascades',
  data_intelligence: 'anomaly framing, metric design, Bayesian updating',
  research_intelligence: 'hypothesis-driven, evidence hierarchy, source comparison',
  evaluation_intelligence: 'multi-lens framing, criteria prioritization, severity allocation',
  retrieval_intelligence: 'relevance scoping, source ranking, gap detection',
  memory_intelligence: 'capture vs consolidate vs reconstruct, salience detection',
  gap_intelligence: 'coverage mapping, absence ranking, completeness testing',
  verification_intelligence: 'spec compliance, test strategy, regression detection',
}

const eyebrow = 'text-[10px] uppercase tracking-widest font-semibold text-muted-foreground'

export function TopicHeader({
  topic,
  classification,
  matchedSignalsByMetaSkill,
  stages,
}: TopicHeaderProps) {
  const {
    discipline,
    taskType,
    mode,
    archetype,
    complexity,
    confidence,
    depth,
    fusionMode,
    metaSkills,
  } = classification

  const confPct = confidence !== undefined ? Math.round(confidence * 100) : null
  const depthMode = fusionMode ? `depth ${depth} · fused` : `depth ${depth} · multiphase`
  const classificationCount = 6 + (confPct !== null ? 1 : 0) // discipline/task/mode/archetype/complexity/depth (+conf)

  // Page-fact derivation: stage N of M + the current stage's subtitle as
  // the italic clause. Grounds the hero in *what's happening now* rather
  // than restating the topic.
  const currentIndex = stages?.findIndex((s) => s.status === 'current') ?? -1
  const currentStage = currentIndex >= 0 ? stages?.[currentIndex] : undefined
  const stageProgress =
    stages !== undefined && currentIndex >= 0
      ? { now: currentIndex + 1, total: stages.length }
      : null
  const heroClause =
    currentStage?.subtitle ?? currentStage?.title ?? undefined

  return (
    <header className="flex flex-col gap-4 px-8 pt-6 pb-4 bg-background border-b border-border">
      {/* Hero row: topic on the left, stage page-fact on the right. The
          topic sits at a calm section-headline scale (text-lg/xl) — it
          leads the room without dominating the work below. The italic
          clause under it anchors the reader in what's happening now
          without restating the topic. */}
      <div className="flex items-start justify-between gap-8">
        <div className="flex flex-col gap-1.5 min-w-0 flex-1">
          <h1 className="font-heading text-lg md:text-xl leading-snug tracking-tight font-semibold text-foreground">
            {topic}
          </h1>
          {heroClause !== undefined && (
            <Aphorism size="md">
              <span className="text-muted-foreground">{heroClause}</span>
            </Aphorism>
          )}
        </div>
        {stageProgress !== null && currentStage !== undefined && (
          <div className="shrink-0 pt-1">
            <ScoreHero
              value={
                <span>
                  <span className="text-foreground">{stageProgress.now}</span>
                  <span className="text-muted-foreground/50"> / {stageProgress.total}</span>
                </span>
              }
              caption={`stage · ${currentStage.phase}`}
              size="md"
            />
          </div>
        )}
      </div>

      {/* Single quiet status row — partner pulse + two independent popovers:
          Classification (L2) and Orchestra (L3). Splitting these makes each
          surface its own clean explanation without scroll inside one popover. */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5 text-chart-1">
          <CircleNotch
            size={12}
            weight="bold"
            className="animate-spin [animation-duration:6s]"
          />
          Partner · warm
        </span>
        <span aria-hidden className="text-muted-foreground/40">·</span>

        {/* L2 Classification */}
        <Popover>
          <PopoverTrigger
            className="inline-flex items-center h-6 px-2 -ml-1 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            Classification · {classificationCount}
          </PopoverTrigger>
          <PopoverContent align="start" className="w-96 max-h-[60vh] overflow-y-auto">
            <div className="space-y-2">
              <div className={eyebrow}>Classification · L2</div>
              <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-2 text-sm">
                <ContextRow term="discipline" value={discipline} hint={DISCIPLINE_BLURB[discipline]} />
                <ContextRow term="task type" value={taskType} hint={TASK_BLURB[taskType]} />
                <ContextRow term="cognitive mode" value={mode} hint={MODE_BLURB[mode]} />
                <ContextRow term="archetype" value={archetype} hint={ARCHETYPE_BLURB[archetype]} />
                <ContextRow term="complexity" value={complexity} hint="drives reasoning depth and the number of phases that activate" />
                <ContextRow
                  term="depth"
                  value={depthMode}
                  hint={fusionMode ? 'fusion mode — all active phases collapse into one LLM call' : 'multiphase — phases execute as sequential LLM calls'}
                />
                {confPct !== null && (
                  <ContextRow term="confidence" value={`${confPct}%`} hint="L2 classifier certainty in this classification" />
                )}
              </dl>
            </div>
          </PopoverContent>
        </Popover>

        {metaSkills.length > 0 && (
          <>
            <span aria-hidden className="text-muted-foreground/40">·</span>
            {/* L3 Orchestra */}
            <Popover>
              <PopoverTrigger
                className="inline-flex items-center h-6 px-2 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
              >
                <span className="flex items-center -space-x-1.5 mr-1.5">
                  {metaSkills.slice(0, 5).map((slug) => (
                    <MetaSkillAvatar key={slug} slug={slug} size="sm" />
                  ))}
                </span>
                Orchestra · {metaSkills.length}
              </PopoverTrigger>
              <PopoverContent align="start" className="w-96 max-h-[60vh] overflow-y-auto">
                <div className="space-y-2">
                  <div className={eyebrow}>Orchestra · L3 · {metaSkills.length}</div>
                  <ul className="space-y-2">
                    {metaSkills.map((slug) => (
                      <li key={slug} className="flex items-start gap-2.5">
                        <MetaSkillAvatar
                          slug={slug}
                          size="sm"
                          fullName={slug.replace(/_/g, ' ')}
                          description={META_SKILL_BLURB[slug]}
                          matchedSignals={matchedSignalsByMetaSkill?.[slug]}
                        />
                        <div className="min-w-0 space-y-0.5">
                          <div className="text-sm font-medium">
                            {slug.replace(/_/g, ' ')}
                          </div>
                          {META_SKILL_BLURB[slug] !== undefined && (
                            <p className="text-xs text-muted-foreground leading-snug">
                              {META_SKILL_BLURB[slug]}
                            </p>
                          )}
                          {matchedSignalsByMetaSkill?.[slug] !== undefined &&
                            matchedSignalsByMetaSkill[slug].length > 0 && (
                              <p className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground pt-0.5">
                                matched: {matchedSignalsByMetaSkill[slug].slice(0, 5).join(' · ')}
                                {matchedSignalsByMetaSkill[slug].length > 5 &&
                                  ` · +${matchedSignalsByMetaSkill[slug].length - 5}`}
                              </p>
                            )}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              </PopoverContent>
            </Popover>
          </>
        )}

        {classification.tools !== undefined && classification.tools.length > 0 && (
          <>
            <span aria-hidden className="text-muted-foreground/40">·</span>
            <ToolsPopover tools={classification.tools} />
          </>
        )}
      </div>
    </header>
  )
}

// ---------------------------------------------------------------------------
// Tools popover — third pillar (alongside Classification + Orchestra)
//
// Surfaces the tools available to the partner this turn, grouped by
// category, with active tools called out. ACE isn't just a reasoning
// substrate — it's a reasoning substrate WITH tools it can invoke. This
// makes that pluggable surface visible.
// ---------------------------------------------------------------------------

function ToolsPopover({ tools }: { tools: JourneyTool[] }) {
  const activeCount = tools.filter((t) => t.active === true).length
  const grouped: Record<JourneyTool['category'], JourneyTool[]> = {
    ace: [],
    code: [],
    web: [],
    data: [],
    external: [],
  }
  tools.forEach((t) => grouped[t.category].push(t))

  return (
    <Popover>
      <PopoverTrigger className="inline-flex items-center h-6 px-2 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 gap-1.5">
        <Toolbox size={12} weight="duotone" />
        Tools · {tools.length}
        {activeCount > 0 && (
          <span className="inline-flex items-center gap-1 font-mono text-[10px] text-live">
            <span className="h-1 w-1 rounded-full bg-live animate-pulse" />
            {activeCount} active
          </span>
        )}
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[28rem] max-h-[60vh] overflow-y-auto">
        <div className="space-y-3">
          <div className={eyebrow}>Tools · the partner has access to {tools.length}</div>
          {(Object.keys(grouped) as JourneyTool['category'][]).map((cat) => {
            const list = grouped[cat]
            if (list.length === 0) return null
            const Icon = TOOL_CATEGORY_ICON[cat]
            return (
              <div key={cat} className="space-y-1.5">
                <div className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                  <Icon size={12} weight="duotone" />
                  {TOOL_CATEGORY_LABEL[cat]}
                </div>
                <ul className="space-y-1">
                  {list.map((t) => (
                    <li
                      key={t.slug}
                      className="grid grid-cols-[140px_1fr] gap-x-3 items-baseline"
                    >
                      <span
                        className={
                          'font-mono text-xs ' +
                          (t.active === true ? 'text-live font-semibold' : 'text-foreground')
                        }
                      >
                        {t.label}
                        {t.active === true && (
                          <span className="ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-live animate-pulse align-middle" />
                        )}
                      </span>
                      <p className="text-xs text-muted-foreground leading-snug">
                        {t.description}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      </PopoverContent>
    </Popover>
  )
}

function ContextRow({ term, value, hint }: { term: string; value: string; hint?: string }) {
  return (
    <>
      <dt className={eyebrow}>{term}</dt>
      <dd className="space-y-0.5">
        <div className="font-medium font-mono text-xs">{value}</div>
        {hint !== undefined && <p className="text-xs text-muted-foreground leading-snug">{hint}</p>}
      </dd>
    </>
  )
}
