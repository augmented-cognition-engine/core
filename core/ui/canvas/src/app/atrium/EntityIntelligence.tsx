import { useEffect, useMemo, useState } from 'react'
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  CircleAlert,
  Clock3,
  Equal,
  Link2,
} from 'lucide-react'

import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'
import { Badge } from '@/design/shadcn/ui/badge'

import { AskAce } from './AskAce'
import {
  type EntityChangeProjection,
  type EntityIntelligenceProjection,
  projectEntityIntelligence,
} from './entityIntelligenceModel'
import { kindLabel } from './intelligenceModel'

function dateLabel(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.valueOf())) return 'Time unavailable'
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(parsed)
}

function Confidence({ value }: { readonly value: number | null }) {
  return (
    <div className="text-right">
      <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
        Snapshot confidence
      </div>
      <div className="mt-1 text-sm font-medium">
        {value === null ? 'Not scored' : `${Math.round(value * 100)}%`}
      </div>
      <div className="mt-1 max-w-44 text-[9px] leading-4 text-muted-foreground">
        {value === null
          ? 'No supported 0–1 value is projected.'
          : 'Reported by this immutable entity snapshot.'}
      </div>
    </div>
  )
}

function DirectionIcon({ direction }: { readonly direction: EntityChangeProjection['direction'] }) {
  if (direction === 'increased') return <ArrowUp className="size-3" aria-label="Increased" />
  if (direction === 'decreased') return <ArrowDown className="size-3" aria-label="Decreased" />
  if (direction === 'changed') return <Equal className="size-3" aria-label="Changed" />
  return <ArrowRight className="size-3" aria-label="Reported shift" />
}

function CurrentState({ entity }: { readonly entity: EntityIntelligenceProjection }) {
  return (
    <section aria-labelledby="entity-current-state">
      <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">
        Current state
      </div>
      <h3 id="entity-current-state" className="mt-1 text-lg font-normal tracking-tight">
        What is admitted now
      </h3>
      {entity.attributes.length === 0 ? (
        <p className="mt-4 border-y border-border py-4 text-xs leading-5 text-muted-foreground">
          This entity snapshot does not project displayable scalar attributes. ACE is preserving the entity identity without inventing a state summary.
        </p>
      ) : (
        <dl className="mt-4 divide-y divide-border border-y border-border">
          {entity.attributes.slice(0, 10).map((attribute) => (
            <div key={attribute.key} className="grid grid-cols-[minmax(0,1fr)_minmax(7rem,auto)] gap-4 py-3">
              <dt className="text-[11px] text-muted-foreground">{attribute.label}</dt>
              <dd className="text-right text-[11px] font-medium text-foreground">{attribute.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}

function DirectionalChange({ entity }: { readonly entity: EntityIntelligenceProjection }) {
  return (
    <section aria-labelledby="entity-directional-change" className="border-t border-border pt-6 lg:border-l lg:border-t-0 lg:pl-7 lg:pt-0">
      <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">
        Directional change
      </div>
      <h3 id="entity-directional-change" className="mt-1 text-lg font-normal tracking-tight">
        What moved
      </h3>
      {entity.changes.length === 0 ? (
        <div className="mt-4 border border-warning/35 bg-warning/[0.04] p-4">
          <div className="flex items-center gap-2 text-[10px] font-medium text-warning">
            <CircleAlert className="size-3.5" aria-hidden="true" /> Direction unavailable
          </div>
          <p className="mt-2 text-[10px] leading-5 text-muted-foreground">
            No comparable prior snapshot or subject-scoped Shift is admitted. A single current snapshot cannot establish direction.
          </p>
        </div>
      ) : (
        <ol className="mt-4 divide-y divide-border border-y border-border">
          {entity.changes.slice(0, 6).map((change) => (
            <li key={change.key} className="py-3">
              <div className="flex items-center gap-2 text-[11px] font-medium">
                <span className="text-muted-foreground"><DirectionIcon direction={change.direction} /></span>
                {change.label}
              </div>
              <p className="mt-1.5 text-[10px] leading-5 text-muted-foreground">{change.detail}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function AnswerFirstTimeline({ entity }: { readonly entity: EntityIntelligenceProjection }) {
  return (
    <section aria-labelledby="entity-timeline" className="border-t border-border pt-7">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">
            Answer-first timeline
          </div>
          <h3 id="entity-timeline" className="mt-1 text-xl font-normal tracking-tight">
            Recent admitted developments
          </h3>
        </div>
        <Badge variant="outline" className="rounded-sm font-mono text-[8px]">
          {entity.timeline.length} records
        </Badge>
      </div>
      <p className="mt-2 max-w-3xl text-[10px] leading-5 text-muted-foreground">
        The entity answer remains primary. This sequence uses explicit effective, publication, observation, or as-of time from subject-scoped records; ACE does not infer missing event time.
      </p>
      {entity.timeline.length === 0 ? (
        <p className="mt-5 border-y border-border py-5 text-xs text-muted-foreground">
          No subject-scoped Observation, Signal, or Shift is projected for this entity.
        </p>
      ) : (
        <ol className="mt-5 divide-y divide-border border-y border-border">
          {entity.timeline.slice(0, 12).map((item) => (
            <li
              key={`${item.record.reference.resource_id}:${item.record.reference.revision}`}
              className="grid gap-2 py-4 sm:grid-cols-[8rem_minmax(0,1fr)] sm:gap-5"
            >
              <div className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground">
                <div className="flex items-center gap-1.5"><Clock3 className="size-3" aria-hidden="true" /> {dateLabel(item.occurredAt)}</div>
                <div className="mt-1">{item.timeBasis}</div>
              </div>
              <div>
                <div className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground">
                  {item.kindLabel}
                </div>
                <h4 className="mt-1.5 text-sm font-medium leading-snug">{item.record.title}</h4>
                <p className="mt-1 text-[10px] leading-5 text-muted-foreground">
                  {item.record.summary ?? 'No display summary is projected for this record.'}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
      <p className="mt-3 text-[9px] leading-4 text-muted-foreground">
        First-class event resources are not part of the current public resource-plane contract; the timeline does not relabel other records as events.
      </p>
    </section>
  )
}

function FocusedRelationships({ entity }: { readonly entity: EntityIntelligenceProjection }) {
  const [depth, setDepth] = useState<0 | 1>(0)
  return (
    <section aria-labelledby="entity-relationships" className="border-t border-border pt-7">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">
            Focused relationships
          </div>
          <h3 id="entity-relationships" className="mt-1 text-xl font-normal tracking-tight">
            Deliberate expansion
          </h3>
        </div>
        <div role="group" aria-label="Relationship depth" className="flex border border-border p-0.5">
          {[0, 1].map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={depth === option}
              className={depth === option
                ? 'bg-accent px-3 py-1.5 font-mono text-[8px] uppercase tracking-[0.12em] text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
                : 'px-3 py-1.5 font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'}
              onClick={() => setDepth(option as 0 | 1)}
            >
              Depth {option}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-2 max-w-3xl text-[10px] leading-5 text-muted-foreground">
        Depth 1 reveals only exact public-resource provenance around this snapshot. Semantic entity-to-entity relationships are not projected, so ACE does not invent partner, competitor, ownership, or influence edges.
      </p>

      <div className="mt-5 border border-border p-4">
        <div className="mx-auto max-w-xl border border-brand/60 bg-brand/[0.06] px-4 py-3 text-center">
          <div className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground">Selected entity snapshot</div>
          <div className="mt-1 text-sm font-medium">{entity.name}</div>
        </div>
        {depth === 0 ? (
          <p className="mt-4 text-center text-[9px] text-muted-foreground">
            Entity only. Choose Depth 1 to inspect its exact evidence closure.
          </p>
        ) : entity.relationships.length === 0 ? (
          <p className="mt-4 border-t border-border pt-4 text-center text-[10px] leading-5 text-muted-foreground">
            No exact upstream or downstream resource link is available for this snapshot.
          </p>
        ) : (
          <ul className="mt-4 grid gap-2 border-t border-border pt-4 sm:grid-cols-2" aria-label="Depth 1 resource relationships">
            {entity.relationships.map((relationship) => (
              <li
                key={`${relationship.direction}:${relationship.record.reference.resource_id}:${relationship.record.reference.revision}`}
                className="min-w-0 border border-border bg-card/35 p-3"
              >
                <div className="flex items-center gap-1.5 font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground">
                  <Link2 className="size-3" /> {relationship.label}
                </div>
                <div className="mt-2 text-[11px] font-medium leading-snug">{relationship.record.title}</div>
                <div className="mt-1 font-mono text-[8px] text-muted-foreground">
                  {kindLabel(relationship.record.reference.resource_kind)} · depth 1
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

function EvidenceAndLimits({ entity }: { readonly entity: EntityIntelligenceProjection }) {
  return (
    <div className="grid gap-7 border-t border-border pt-7 lg:grid-cols-2">
      <section aria-labelledby="entity-evidence">
        <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">Admitted evidence</div>
        <h3 id="entity-evidence" className="mt-1 text-lg font-normal tracking-tight">Exact upstream basis</h3>
        {entity.evidence.length === 0 ? (
          <p className="mt-4 border-y border-border py-4 text-[10px] leading-5 text-muted-foreground">
            No upstream record in this page matches the snapshot’s exact provenance references. ACE preserves the gap rather than substituting subject similarity.
          </p>
        ) : (
          <ol className="mt-4 divide-y divide-border border-y border-border">
            {entity.evidence.map((record, index) => (
              <li key={`${record.reference.resource_id}:${record.reference.revision}`} className="flex gap-3 py-3">
                <span className="font-mono text-[9px] text-muted-foreground">[{index + 1}]</span>
                <div className="min-w-0">
                  <div className="text-[11px] font-medium leading-snug">{record.title}</div>
                  <div className="mt-1 font-mono text-[8px] text-muted-foreground">
                    {kindLabel(record.reference.resource_kind)} · admitted
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-labelledby="entity-limits" className="lg:border-l lg:border-border lg:pl-7">
        <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">Conflicts and unknowns</div>
        <h3 id="entity-limits" className="mt-1 text-lg font-normal tracking-tight">What ACE cannot close</h3>
        {entity.conflicts.length === 0 && entity.unknowns.length === 0 ? (
          <div className="mt-4 border border-warning/35 bg-warning/[0.04] p-4">
            <div className="flex items-center gap-2 text-[10px] font-medium text-warning">
              <CircleAlert className="size-3.5" aria-hidden="true" /> Not projected
            </div>
            <p className="mt-2 text-[10px] leading-5 text-muted-foreground">
              No subject-scoped conflict or uncertainty record is admitted. This does not claim the entity is conflict-free or fully known.
            </p>
          </div>
        ) : (
          <ul className="mt-4 divide-y divide-border border-y border-border">
            {[...entity.conflicts, ...entity.unknowns].map((record) => (
              <li key={`${record.reference.resource_id}:${record.reference.revision}`} className="py-3">
                <div className="font-mono text-[8px] uppercase tracking-[0.12em] text-warning">
                  {kindLabel(record.reference.resource_kind)} · admitted
                </div>
                <div className="mt-1 text-[11px] font-medium">{record.title}</div>
                <p className="mt-1 text-[10px] leading-5 text-muted-foreground">
                  {record.summary ?? 'No display summary is projected for this limit.'}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function EntityDetail({ entity }: { readonly entity: EntityIntelligenceProjection }) {
  return (
    <article aria-labelledby="entity-intelligence-title" className="min-w-0">
      <header className="flex flex-wrap items-start justify-between gap-5 border-b border-border pb-7">
        <div className="min-w-0">
          <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">
            Entity intelligence · current snapshot
          </div>
          <h2 id="entity-intelligence-title" className="mt-2 text-4xl font-normal leading-none tracking-[-0.04em]">
            {entity.name}
          </h2>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground">
            <span>{entity.typeRef === null ? 'Type not projected' : entity.typeRef}</span>
            <span>As of {dateLabel(entity.current.reference.as_of)}</span>
          </div>
        </div>
        <Confidence value={entity.confidence} />
      </header>

      <div className="grid gap-7 py-7 lg:grid-cols-2">
        <CurrentState entity={entity} />
        <DirectionalChange entity={entity} />
      </div>
      <AnswerFirstTimeline entity={entity} />
      <FocusedRelationships entity={entity} />
      <EvidenceAndLimits entity={entity} />
    </article>
  )
}

export function EntityIntelligenceExplore({
  items,
  embedded = false,
}: {
  readonly items: readonly IntelligenceResourceRecord[]
  readonly embedded?: boolean
}) {
  const entities = useMemo(() => projectEntityIntelligence(items), [items])
  const [selectedRef, setSelectedRef] = useState<string | null>(entities[0]?.entityRef ?? null)
  const selected = entities.find((entity) => entity.entityRef === selectedRef) ?? entities[0]

  useEffect(() => {
    if (selected === undefined) setSelectedRef(null)
    else if (selected.entityRef !== selectedRef) setSelectedRef(selected.entityRef)
  }, [selected, selectedRef])

  return (
    <div className="space-y-7">
      {!embedded && (
        <>
          <section aria-labelledby="explore-answer-first">
            <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">Explore the world</div>
            <h2 id="explore-answer-first" className="mt-2 text-3xl font-normal tracking-[-0.035em]">
              Ask first. Then inspect the entity.
            </h2>
            <p className="mt-2 max-w-3xl text-xs leading-5 text-muted-foreground">
              Existing Ask ACE search and RAG semantics remain unchanged. Entity intelligence below projects only the current public resource page: state, supported movement, time, exact evidence, limits, and depth-one lineage.
            </p>
          </section>

          <AskAce items={items} />
        </>
      )}

      {entities.length === 0 ? (
        <section role="status" aria-label="Entity intelligence unavailable" className="border-y border-border py-10">
          <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-warning">Contract dependency</div>
          <h2 className="mt-2 text-xl font-normal tracking-tight">No entity snapshot is projected</h2>
          <p className="mt-3 max-w-3xl text-xs leading-6 text-muted-foreground">
            The current page can still answer from its admitted Briefs, Shifts, and Signals, but an entity intelligence object requires a public entity snapshot. ACE will not synthesize one from titles, keywords, or search results.
          </p>
        </section>
      ) : (
        <section className="grid min-w-0 overflow-hidden border border-border xl:grid-cols-[12rem_minmax(0,1fr)]">
          <nav aria-label="Entities" className="border-b border-border p-3 xl:border-b-0 xl:border-r">
            <div className="px-2 pb-3 font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
              Entities · {entities.length}
            </div>
            <ul className="grid gap-1 sm:grid-cols-2 xl:grid-cols-1">
              {entities.map((entity) => (
                <li key={entity.entityRef}>
                  <button
                    type="button"
                    aria-pressed={selected?.entityRef === entity.entityRef}
                    className={selected?.entityRef === entity.entityRef
                      ? 'w-full bg-accent px-2.5 py-2 text-left text-[10px] text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
                      : 'w-full px-2.5 py-2 text-left text-[10px] text-muted-foreground hover:bg-accent/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'}
                    onClick={() => setSelectedRef(entity.entityRef)}
                  >
                    <span className="block truncate font-medium">{entity.name}</span>
                    <span className="mt-1 block truncate font-mono text-[7px] uppercase tracking-[0.1em]">
                      {entity.typeRef ?? 'type unavailable'}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </nav>
          <div className="min-w-0 p-5 md:p-7">
            {selected !== undefined && <EntityDetail key={selected.entityRef} entity={selected} />}
          </div>
        </section>
      )}

      <section aria-label="Explore contract boundary" className="border border-border bg-card/25 p-4">
        <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">Contract boundary</div>
        <p className="mt-2 text-[10px] leading-5 text-muted-foreground">
          Still required from architecture: typed semantic relationships, first-class event projections, and authoritative conflict/uncertainty coverage. Until those contracts exist, Explore shows exact resource lineage and explicit gaps—never a fabricated knowledge graph.
        </p>
      </section>
    </div>
  )
}
