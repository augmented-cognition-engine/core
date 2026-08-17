import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, Check, CircleAlert, CircleMinus, FileText, History, KeyRound, PackageCheck } from 'lucide-react'

import {
  IntelligenceCatalogApiError,
  queryDomainPackActivationHistory,
  type DomainPackActivationHistory,
  type DomainPackActivationRevision,
  type DomainPackLifecycleAvailability,
  type DomainPackLifecycleCapability,
  type InstalledDomainPackPreview,
  type IntelligenceConsumerAvailability,
  type IntelligenceConsumerCatalog,
  type IntelligenceConsumerInterface,
} from '@/api/intelligenceCatalogApi'
import { Alert, AlertDescription, AlertTitle } from '@/design/shadcn/ui/alert'
import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import { Input } from '@/design/shadcn/ui/input'
import { Label } from '@/design/shadcn/ui/label'

function exactDigest(value: string): string {
  return `${value.slice(0, 15)}…${value.slice(-8)}`
}

function Availability({ value }: { readonly value: IntelligenceConsumerAvailability | DomainPackLifecycleAvailability }) {
  if (value === 'available') {
    return <span className="inline-flex items-center gap-1.5 text-success"><Check className="size-3" aria-hidden="true" />Available</span>
  }
  if (value === 'navigation_only') {
    return <span className="inline-flex items-center gap-1.5 text-foreground/75"><ArrowUpRight className="size-3" aria-hidden="true" />In-product route</span>
  }
  if (value === 'contract_only') {
    return <span className="inline-flex items-center gap-1.5 text-foreground/70"><FileText className="size-3" aria-hidden="true" />Defined</span>
  }
  return <span className="inline-flex items-center gap-1.5 text-muted-foreground"><CircleMinus className="size-3" aria-hidden="true" />Not exposed</span>
}

/**
 * Groups Domain Pack lifecycle capabilities by availability so installed/readable
 * capabilities lead, contract-only capabilities are subordinate, and unexposed
 * capabilities are separated out entirely. Every input capability appears in
 * exactly one output group, in its original catalog order.
 */
export function groupLifecycleCapabilities(
  capabilities: readonly DomainPackLifecycleCapability[],
): {
  readonly usable: readonly DomainPackLifecycleCapability[]
  readonly defined: readonly DomainPackLifecycleCapability[]
  readonly notExposed: readonly DomainPackLifecycleCapability[]
} {
  const usable: DomainPackLifecycleCapability[] = []
  const defined: DomainPackLifecycleCapability[] = []
  const notExposed: DomainPackLifecycleCapability[] = []
  for (const capability of capabilities) {
    if (capability.availability === 'available') usable.push(capability)
    else if (capability.availability === 'contract_only') defined.push(capability)
    else notExposed.push(capability)
  }
  return { usable, defined, notExposed }
}

/**
 * Groups consumer interfaces by availability so interfaces usable now lead,
 * bounded in-product routes and defined-but-undelivered contracts are
 * subordinate, and unexposed interfaces are separated out entirely. Every
 * input interface appears in exactly one output group, in its original
 * catalog order.
 */
export function groupConsumerInterfaces(
  interfaces: readonly IntelligenceConsumerInterface[],
): {
  readonly usable: readonly IntelligenceConsumerInterface[]
  readonly navigationOnly: readonly IntelligenceConsumerInterface[]
  readonly defined: readonly IntelligenceConsumerInterface[]
  readonly notExposed: readonly IntelligenceConsumerInterface[]
} {
  const usable: IntelligenceConsumerInterface[] = []
  const navigationOnly: IntelligenceConsumerInterface[] = []
  const defined: IntelligenceConsumerInterface[] = []
  const notExposed: IntelligenceConsumerInterface[] = []
  for (const item of interfaces) {
    if (item.availability === 'available') usable.push(item)
    else if (item.availability === 'navigation_only') navigationOnly.push(item)
    else if (item.availability === 'contract_only') defined.push(item)
    else notExposed.push(item)
  }
  return { usable, navigationOnly, defined, notExposed }
}

function LifecycleCapabilityRow({ capability }: { readonly capability: DomainPackLifecycleCapability }) {
  return (
    <li className="grid gap-2 border-t border-border py-3 first:border-t-0 lg:grid-cols-[9rem_8rem_minmax(0,1fr)]">
      <span className="text-[9px] font-medium text-foreground/85">{capability.label}</span>
      <span className="font-mono text-[8px] uppercase tracking-[0.08em]"><Availability value={capability.availability} /></span>
      <div className="text-[9px] leading-4 text-muted-foreground">
        <p>{capability.boundary}</p>
        {capability.endpoint !== null && <p className="mt-1 break-all font-mono text-[7px] text-foreground/70">{capability.endpoint}</p>}
        {capability.contract_refs.length > 0 && (
          <p className="mt-1 break-words font-mono text-[7px]">{capability.contract_refs.join(' · ')}</p>
        )}
      </div>
    </li>
  )
}

function ReleasePosture() {
  const experiences = [
    { label: 'World Intelligence', state: 'Release-ready', ready: true, boundary: 'May proceed through reviewed activation.' },
    { label: 'Market Intelligence', state: 'Release-ready', ready: true, boundary: 'May proceed through reviewed activation.' },
    { label: 'Custom Intelligence', state: 'Preview', ready: false, boundary: 'Proposal and review only in v1; activation remains unavailable.' },
  ] as const

  return (
    <section aria-labelledby="release-posture-heading" className="mt-6">
      <div id="release-posture-heading" className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground">
        v1 experience posture
      </div>
      <ol className="mt-2 border-y border-border" aria-label="Domain experience release posture">
        {experiences.map((experience) => (
          <li key={experience.label} className="grid gap-2 border-t border-border py-3 first:border-t-0 sm:grid-cols-[11rem_7rem_minmax(0,1fr)] sm:items-baseline">
            <span className="text-[10px] font-medium text-foreground/90">{experience.label}</span>
            <span className={experience.ready ? 'inline-flex items-center gap-1.5 text-[9px] text-success' : 'text-[9px] text-foreground/70'}>
              {experience.ready && <Check className="size-3" aria-hidden="true" />}
              {experience.state}
            </span>
            <span className="text-[9px] leading-4 text-muted-foreground">{experience.boundary}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

export function DomainPackLedger({
  packs,
  onReviewBuild,
}: {
  readonly packs: readonly InstalledDomainPackPreview[]
  readonly onReviewBuild: () => void
}) {
  return (
    <section aria-labelledby="domain-pack-heading">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
            Domain Pack · installed truth
          </div>
          <h3 id="domain-pack-heading" className="mt-2 text-lg font-medium tracking-tight">
            Preview the installed operating model.
          </h3>
          <p className="mt-2 max-w-3xl text-[10px] leading-5 text-muted-foreground">
            Installation means validated declarative material is present on this host. It does not activate a Pack,
            connect a source, grant authority, or apply a local override.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={onReviewBuild}>
          Review build boundaries
        </Button>
      </div>

      <ReleasePosture />

      {packs.length === 0 ? (
        <div className="mt-6 border-y border-border px-4 py-8 text-sm text-muted-foreground">
          No installed Domain Pack manifest is exposed by the current host. Release posture does not imply local installation.
        </div>
      ) : (
        <ol className="mt-6 border-y border-border" aria-label="Installed Domain Packs">
          {packs.map((item) => {
            const manifest = item.manifest
            const slots = manifest.overlay_slots ?? []
            const capabilities = manifest.capability_requirements ?? []
            const authorities = manifest.authority_requests ?? []
            return (
              <li
                key={`${manifest.metadata.pack_id}:${item.manifest_digest}`}
                className="grid gap-4 border-t border-border py-5 first:border-t-0 xl:grid-cols-[minmax(0,1fr)_13rem_13rem]"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <PackageCheck className="size-4 text-success" aria-hidden="true" />
                    <h4 className="text-sm font-medium">{manifest.metadata.display_name}</h4>
                    <Badge variant="outline" className="rounded-sm font-mono text-[8px]">
                      Pack {manifest.metadata.version}
                    </Badge>
                  </div>
                  <p className="mt-2 text-[10px] leading-5 text-muted-foreground">
                    {manifest.metadata.description ?? 'No Pack description is declared.'}
                  </p>
                  <details className="mt-3 text-[9px] leading-4 text-muted-foreground">
                    <summary className="cursor-pointer text-foreground/80">Exact manifest and contracts</summary>
                    <dl className="mt-3 grid gap-2 border-l border-border pl-3 font-mono text-[8px]">
                      <div><dt className="inline text-muted-foreground">Pack ID </dt><dd className="inline text-foreground/75">{manifest.metadata.pack_id}</dd></div>
                      <div><dt className="inline text-muted-foreground">Installed by </dt><dd className="inline text-foreground/75">{item.distribution} {item.distribution_version}</dd></div>
                      <div><dt className="inline text-muted-foreground">Manifest </dt><dd className="inline text-foreground/75" title={item.manifest_digest}>{exactDigest(item.manifest_digest)}</dd></div>
                      <div><dt className="inline text-muted-foreground">Module contracts </dt><dd className="inline text-foreground/75">{manifest.modules.map((module) => module.contract).join(', ')}</dd></div>
                    </dl>
                  </details>
                </div>
                <div className="border-t border-border pt-4 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0">
                  <div className="font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground">Pack defaults</div>
                  <p className="mt-2 text-[10px] leading-5 text-foreground/80">
                    {manifest.modules.length} modules · {manifest.resources.length} resources
                  </p>
                  <p className="mt-1 text-[9px] leading-4 text-muted-foreground">
                    {capabilities.length} capability requirements · {authorities.length} authority requests
                  </p>
                </div>
                <div className="border-t border-border pt-4 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0">
                  <div className="font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground">Local boundary</div>
                  <p className="mt-2 text-[10px] leading-5 text-foreground/80">
                    {slots.length === 0 ? 'No overlay slots declared' : `${slots.length} declared overlay slot${slots.length === 1 ? '' : 's'}`}
                  </p>
                  <p className="mt-1 text-[9px] leading-4 text-muted-foreground">
                    Active values are not inferred from declared slots.
                  </p>
                </div>
                <details className="border-t border-border pt-4 xl:col-span-3">
                  <summary className="cursor-pointer font-mono text-[8px] uppercase tracking-[0.1em] text-foreground/75">
                    Install, customize, upgrade, history, and rollback
                  </summary>
                  {(() => {
                    const grouped = groupLifecycleCapabilities(item.lifecycle)
                    const lifecycleLabel = `${manifest.metadata.display_name} lifecycle`
                    return (
                      <div className="mt-3">
                        {grouped.usable.length > 0 && (
                          <section>
                            <h5 className="font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground">Usable now</h5>
                            <ol className="mt-2 border-y border-border" aria-label={`${lifecycleLabel} · usable now`}>
                              {grouped.usable.map((capability) => (
                                <LifecycleCapabilityRow key={capability.capability_id} capability={capability} />
                              ))}
                            </ol>
                          </section>
                        )}
                        {grouped.defined.length > 0 && (
                          <section className="mt-4">
                            <h5 className="font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground">Defined, not active</h5>
                            <ol className="mt-2 border-y border-border" aria-label={`${lifecycleLabel} · defined`}>
                              {grouped.defined.map((capability) => (
                                <LifecycleCapabilityRow key={capability.capability_id} capability={capability} />
                              ))}
                            </ol>
                          </section>
                        )}
                        {grouped.notExposed.length > 0 && (
                          <details className="mt-3 border-t border-border pt-2">
                            <summary className="cursor-pointer font-mono text-[8px] uppercase tracking-[0.1em] text-foreground/70">
                              Not exposed ({grouped.notExposed.length})
                            </summary>
                            <ol className="mt-2 border-y border-border" aria-label={`${lifecycleLabel} · not exposed`}>
                              {grouped.notExposed.map((capability) => (
                                <LifecycleCapabilityRow key={capability.capability_id} capability={capability} />
                              ))}
                            </ol>
                          </details>
                        )}
                      </div>
                    )
                  })()}
                </details>
              </li>
            )
          })}
        </ol>
      )}

      <details className="mt-6 border-t border-border pt-4 text-[9px] leading-4 text-muted-foreground">
        <summary className="cursor-pointer font-mono text-[8px] uppercase tracking-[0.12em] text-foreground/75">
          Advanced Build and operator detail
        </summary>
        <dl className="mt-4 grid gap-4 md:grid-cols-3">
          <div><dt className="text-foreground/85">Agent topology</dt><dd className="mt-1">P2 operator detail. ACE does not project an editable agent canvas or infer active handoffs from Pack declarations.</dd></div>
          <div><dt className="text-foreground/85">Source pipeline</dt><dd className="mt-1">Exact source roles and readiness belong to the reviewed build. v1 does not promise a universal connector catalog.</dd></div>
          <div><dt className="text-foreground/85">Rules and escalation</dt><dd className="mt-1">Pack contracts may declare capabilities and authority requests; accepted values and runtime grants require their own current projections.</dd></div>
        </dl>
      </details>
    </section>
  )
}

interface ActivationHistoryErrorState {
  readonly status: number
  readonly title: string
  readonly detail: string
}

function activationHistoryErrorState(reason: unknown): ActivationHistoryErrorState {
  const status = reason instanceof IntelligenceCatalogApiError ? reason.status : 0
  const detail = reason instanceof Error ? reason.message : 'ACE could not read this exact Pack activation.'
  if (status === 401) {
    return {
      status,
      title: 'ACE retried authentication and still could not read this activation.',
      detail: `${detail} Nothing was activated, customized, upgraded, or rolled back.`,
    }
  }
  if (status === 403) {
    return {
      status,
      title: 'Current permission does not authorize this read.',
      detail: `${detail} Reading requires the existing administer_lifecycle authority.`,
    }
  }
  if (status === 404) {
    return {
      status,
      title: 'No activation exists for this exact activation key.',
      detail: `${detail} ACE never infers an activation key from an installed Pack ID.`,
    }
  }
  if (status === 503) {
    return {
      status,
      title: 'Exact Pack activation history is unavailable right now.',
      detail: `${detail} Nothing was activated, customized, upgraded, or rolled back.`,
    }
  }
  return {
    status,
    title: 'ACE stopped before reading this activation.',
    detail: `${detail} Nothing was activated, customized, upgraded, or rolled back.`,
  }
}

function exactTimestamp(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toISOString()
}

function ActivationRevisionDetail({
  revision,
  heading,
}: {
  readonly revision: DomainPackActivationRevision
  readonly heading: string
}) {
  return (
    <div className="border-t border-border py-4 first:border-t-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground">{heading}</span>
        <Badge variant="outline" className="rounded-sm font-mono text-[8px]">r{revision.revision}</Badge>
        <Badge variant="outline" className="rounded-sm font-mono text-[8px] uppercase tracking-[0.06em]">{revision.action}</Badge>
        <Badge variant="outline" className="rounded-sm font-mono text-[8px] uppercase tracking-[0.06em]">{revision.state}</Badge>
      </div>
      <dl className="mt-3 grid gap-x-6 gap-y-2 font-mono text-[8px] leading-4 text-muted-foreground sm:grid-cols-2">
        <div><dt className="inline text-muted-foreground">Pack </dt><dd className="inline text-foreground/80">{revision.pack.pack_id} {revision.pack.pack_version} · {exactDigest(revision.pack.pack_digest)}</dd></div>
        <div><dt className="inline text-muted-foreground">Compiled pack </dt><dd className="inline text-foreground/80">{revision.pack.compiled_pack_id}</dd></div>
        <div><dt className="inline text-muted-foreground">Plan </dt><dd className="inline text-foreground/80">{revision.plan_id} · {exactDigest(revision.plan_digest)}</dd></div>
        <div><dt className="inline text-muted-foreground">Approval receipt </dt><dd className="inline text-foreground/80">{revision.approval_receipt_ref} · {exactDigest(revision.approval_receipt_digest)}</dd></div>
        <div><dt className="inline text-muted-foreground">Commit receipt </dt><dd className="inline text-foreground/80">{revision.commit_receipt_id} · {exactDigest(revision.commit_receipt_digest)}</dd></div>
        <div><dt className="inline text-muted-foreground">Actor </dt><dd className="inline text-foreground/80">{revision.actor_ref}</dd></div>
        <div><dt className="inline text-muted-foreground">Occurred </dt><dd className="inline text-foreground/80">{exactTimestamp(revision.occurred_at)}</dd></div>
        <div><dt className="inline text-muted-foreground">Committed </dt><dd className="inline text-foreground/80">{exactTimestamp(revision.committed_at)}</dd></div>
      </dl>
      <div className="mt-3">
        <div className="font-mono text-[7px] uppercase tracking-[0.1em] text-muted-foreground">
          Compiled overlay values ({revision.overlay.values.length})
        </div>
        {revision.overlay.values.length === 0 ? (
          <p className="mt-1 text-[9px] leading-4 text-muted-foreground">No overlay slot carries an active value in this revision.</p>
        ) : (
          <dl className="mt-1 grid gap-1 font-mono text-[8px] leading-4">
            {revision.overlay.values.map((value) => (
              <div key={value.slot_id}><dt className="inline text-muted-foreground">{value.slot_id} </dt><dd className="inline text-foreground/80">{value.value_json}</dd></div>
            ))}
          </dl>
        )}
      </div>
    </div>
  )
}

function ActivationHistoryResult({ history }: { readonly history: DomainPackActivationHistory }) {
  return (
    <div className="mt-5">
      <div className="flex flex-wrap items-center gap-2 border-y border-border py-2 font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground">
        <span>Product {history.product_id}</span>
        <span>·</span>
        <span>Activation {history.activation_id}</span>
        <span>·</span>
        <span className="inline-flex items-center gap-1 text-warning">
          <CircleAlert className="size-3" aria-hidden="true" /> live_authority: false
        </span>
      </div>
      <p className="mt-2 text-[9px] leading-4 text-muted-foreground">
        {history.authority_stage === 'historical_reference' ? 'Historical reference only.' : history.authority_stage}{' '}
        This read does not authorize customization, upgrade, rollback, or activation.
      </p>
      <ActivationRevisionDetail revision={history.current} heading="Current governed revision" />
      <div className="mt-4">
        <div className="flex items-center gap-1.5 font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground">
          <History className="size-3" aria-hidden="true" /> Append-only history · newest first ·{' '}
          {history.history.length} revision{history.history.length === 1 ? '' : 's'}
        </div>
        <div className="mt-1 border-t border-border">
          {history.history.map((revision) => (
            <ActivationRevisionDetail key={revision.revision_id} revision={revision} heading={`Revision r${revision.revision}`} />
          ))}
        </div>
      </div>
    </div>
  )
}

export function PackActivationReader() {
  const [activationKey, setActivationKey] = useState('')
  const [submittedKey, setSubmittedKey] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<ActivationHistoryErrorState | null>(null)
  const [history, setHistory] = useState<DomainPackActivationHistory | null>(null)

  async function readActivation(key: string) {
    const normalized = key.trim()
    if (normalized.length === 0) return
    setPending(true)
    setError(null)
    setHistory(null)
    setSubmittedKey(normalized)
    try {
      const result = await queryDomainPackActivationHistory(normalized)
      setHistory(result)
    } catch (reason: unknown) {
      setError(activationHistoryErrorState(reason))
    } finally {
      setPending(false)
    }
  }

  return (
    <section aria-labelledby="pack-activation-heading" className="mt-10 border-t border-border pt-8">
      <div>
        <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
          Pack activation · read only
        </div>
        <h3 id="pack-activation-heading" className="mt-2 text-lg font-medium tracking-tight">
          Read one exact governed Pack by activation key.
        </h3>
        <p className="mt-2 max-w-3xl text-[10px] leading-5 text-muted-foreground">
          ACE never infers an activation key from an installed Pack ID. Supply the exact activation key to read its
          current governed Pack reference, compiled overlay values, and immutable append-only revision history. This
          read does not authorize customization, upgrade, rollback, or activation.
        </p>
      </div>

      <form
        className="mt-4 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault()
          void readActivation(activationKey)
        }}
      >
        <div className="min-w-0 flex-1 sm:max-w-xs">
          <Label htmlFor="pack-activation-key" className="font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground">
            <KeyRound className="size-3" aria-hidden="true" /> Activation key
          </Label>
          <Input
            id="pack-activation-key"
            value={activationKey}
            onChange={(event) => setActivationKey(event.target.value)}
            placeholder="Exact activation key, not a Pack ID"
            aria-describedby="pack-activation-key-hint"
            className="mt-1.5"
          />
        </div>
        <Button type="submit" variant="outline" size="sm" disabled={activationKey.trim().length === 0 || pending}>
          {pending ? 'Reading…' : 'Read activation'}
        </Button>
      </form>
      <p id="pack-activation-key-hint" className="mt-2 text-[9px] leading-4 text-muted-foreground">
        Not inferred from an installed Pack ID. You must supply the exact activation key.
      </p>

      {submittedKey === null ? (
        <div className="mt-5 border-y border-border px-4 py-8 text-sm text-muted-foreground">
          No activation key has been read yet.
        </div>
      ) : pending ? (
        <div
          role="status"
          aria-live="polite"
          className="mt-5 border-y border-border px-4 py-8 text-sm text-muted-foreground"
        >
          Reading activation…
        </div>
      ) : error !== null ? (
        <Alert variant="destructive" className="mt-5">
          <CircleAlert />
          <AlertTitle>{error.title}</AlertTitle>
          <AlertDescription>
            <p>{error.detail}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => void readActivation(submittedKey)}
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : history !== null ? (
        <ActivationHistoryResult history={history} />
      ) : null}
    </section>
  )
}

function ConsumerInterfaceRow({ item }: { readonly item: IntelligenceConsumerInterface }) {
  return (
    <li className="grid gap-4 border-t border-border py-5 first:border-t-0 lg:grid-cols-[10rem_minmax(0,1fr)_minmax(0,1fr)]">
      <div>
        <Badge variant="outline" className="rounded-sm font-mono text-[8px] uppercase tracking-[0.08em]">
          {item.kind}
        </Badge>
        <h5 className="mt-2 text-xs font-medium leading-5">{item.label}</h5>
        <div className="mt-2 font-mono text-[8px] uppercase tracking-[0.08em]">
          <Availability value={item.availability} />
        </div>
        {item.endpoint !== null && <div className="mt-2 break-all font-mono text-[8px] text-muted-foreground">{item.endpoint}</div>}
        {item.interface_id === 'investigation_board' && (
          <Button asChild variant="outline" size="sm" className="mt-3">
            <Link to="/board">Open Investigation Board</Link>
          </Button>
        )}
      </div>
      <div className="border-t border-border pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
        <div className="font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground">Exact contract and provenance</div>
        <p className="mt-2 text-[9px] leading-4 text-foreground/80">{item.provenance_boundary}</p>
        <p className="mt-2 break-words font-mono text-[8px] leading-4 text-muted-foreground">
          {item.contract_refs.length === 0 ? 'No downstream contract reference exposed' : item.contract_refs.join(' · ')}
        </p>
      </div>
      <div className="border-t border-border pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
        <div className="font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground">Permission and delivery</div>
        <p className="mt-2 text-[9px] leading-4 text-foreground/80">{item.permission_boundary}</p>
        <p className="mt-2 text-[9px] leading-4 text-muted-foreground">{item.delivery_boundary}</p>
      </div>
    </li>
  )
}

export function ConsumerContractLedger({ catalog }: { readonly catalog: IntelligenceConsumerCatalog | null }) {
  if (catalog === null) {
    return (
      <section aria-labelledby="consumer-contract-heading">
        <h3 id="consumer-contract-heading" className="text-lg font-medium tracking-tight">Consumer contracts</h3>
        <div className="mt-4 border-y border-border px-4 py-8 text-sm text-muted-foreground">
          The consumer contract catalog is unavailable. ACE is not substituting inferred interfaces.
        </div>
      </section>
    )
  }

  const grouped = groupConsumerInterfaces(catalog.interfaces)

  return (
    <section aria-labelledby="consumer-contract-heading">
      <div>
        <div className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
          Contracts · permissions · delivery
        </div>
        <h3 id="consumer-contract-heading" className="mt-2 text-lg font-medium tracking-tight">
          Use only the interfaces ACE can defend.
        </h3>
      </div>

      <div className="mt-5">
        <h4 id="consumer-usable-heading" className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
          Usable now
        </h4>
        {grouped.usable.length === 0 ? (
          <p className="mt-2 text-[10px] leading-5 text-muted-foreground">No consumer interface is usable from this host right now.</p>
        ) : (
          <ol className="mt-2 border-y border-border" aria-labelledby="consumer-usable-heading">
            {grouped.usable.map((item) => <ConsumerInterfaceRow key={item.interface_id} item={item} />)}
          </ol>
        )}
        <p className="mt-3 text-[9px] leading-4 text-muted-foreground">
          A ChatGPT, Claude, or other consumer subscription is not an API credential. Any provider integration must
          name and validate the actual provider/API credential and permission boundary.
        </p>
      </div>

      {grouped.navigationOnly.length > 0 && (
        <div className="mt-6">
          <h4 id="consumer-navigation-heading" className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
            In-product route
          </h4>
          <p className="mt-1 text-[9px] leading-4 text-muted-foreground">Bounded in-product navigation, not payload delivery.</p>
          <ol className="mt-2 border-y border-border" aria-labelledby="consumer-navigation-heading">
            {grouped.navigationOnly.map((item) => <ConsumerInterfaceRow key={item.interface_id} item={item} />)}
          </ol>
        </div>
      )}

      {grouped.defined.length > 0 && (
        <div className="mt-6">
          <h4 id="consumer-defined-heading" className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted-foreground">
            Defined
          </h4>
          <p className="mt-1 text-[9px] leading-4 text-muted-foreground">A contract exists. Nothing is delivered through it yet.</p>
          <ol className="mt-2 border-y border-border" aria-labelledby="consumer-defined-heading">
            {grouped.defined.map((item) => <ConsumerInterfaceRow key={item.interface_id} item={item} />)}
          </ol>
        </div>
      )}

      {grouped.notExposed.length > 0 && (
        <details className="mt-6 border-t border-border pt-3">
          <summary className="cursor-pointer font-mono text-[8px] uppercase tracking-[0.12em] text-foreground/75">
            Not exposed ({grouped.notExposed.length})
          </summary>
          <ol className="mt-3 border-y border-border" aria-label="Not exposed consumer interfaces">
            {grouped.notExposed.map((item) => <ConsumerInterfaceRow key={item.interface_id} item={item} />)}
          </ol>
        </details>
      )}

      {catalog.unresolved_dependencies.length > 0 && (
        <aside className="mt-6 border-l border-border pl-4">
          <div className="font-mono text-[8px] uppercase tracking-[0.12em] text-muted-foreground">Unresolved dependencies</div>
          <ul className="mt-3 space-y-2 text-[9px] leading-4 text-muted-foreground">
            {catalog.unresolved_dependencies.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </aside>
      )}
    </section>
  )
}
