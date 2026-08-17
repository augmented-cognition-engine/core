import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleMinus,
  Download,
  HardDrive,
  Laptop,
  LockKeyhole,
  Server,
  Users,
  WifiOff,
  type LucideIcon,
} from 'lucide-react'

import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import { Card, CardContent } from '@/design/shadcn/ui/card'
import { RadioGroup, RadioGroupItem } from '@/design/shadcn/ui/radio-group'

export type HostRunMode = 'personal' | 'shared_server' | 'dedicated_appliance'

// What the host detected about this computer. Shown as a status summary —
// each value is a recommendation the owner can change later in Settings,
// never a questionnaire step.
export interface HostDetectedEnvironment {
  readonly hardwareSummary: string
  readonly runtimeSummary: string
  readonly modelProfile: string
  readonly quantization: string
  readonly practicalContext: string
  readonly expectation: string
}

// Host-supplied truth. `configured` (a prior owner or environment choice)
// and `admin_fixed` both bypass the first-run prompt entirely.
export type HostFirstRunProjection =
  | { readonly kind: 'configured'; readonly mode: HostRunMode }
  | { readonly kind: 'admin_fixed'; readonly mode: HostRunMode }
  | {
      readonly kind: 'unconfigured'
      readonly detected: HostDetectedEnvironment
      readonly recommendedMode?: 'personal'
    }

export type ModelDownloadState =
  | { readonly status: 'not_started' }
  | {
      readonly status: 'downloading'
      readonly bytesDownloaded?: number
      readonly bytesTotal?: number
      readonly resumable: boolean
    }
  | {
      readonly status: 'interrupted'
      readonly reason: string
      readonly bytesDownloaded?: number
      readonly bytesTotal?: number
      readonly resumable: boolean
    }
  | { readonly status: 'failed'; readonly reason: string; readonly resumable?: boolean }
  | { readonly status: 'complete' }

export type GenerationSmokeTest =
  | { readonly status: 'pending' }
  | { readonly status: 'passed' }
  | { readonly status: 'failed'; readonly reason: string }

export interface HostRuntimeReadinessProjection {
  readonly usableNow: boolean
  readonly download: ModelDownloadState
  readonly modelLoaded: boolean
  readonly smokeTest: GenerationSmokeTest
  readonly offlineReason?: string
  readonly lowDiskReason?: string
}

const QUESTION = 'How should ACE run on this computer?'

const MODE_OPTIONS: readonly {
  readonly mode: HostRunMode
  readonly label: string
  readonly description: string
  readonly icon: LucideIcon
}[] = [
  {
    mode: 'personal',
    label: 'Personal',
    description: 'One person on this computer, local by default.',
    icon: Laptop,
  },
  {
    mode: 'shared_server',
    label: 'Shared server',
    description: 'ACE shares this computer with other workloads. Access stays local until an operator enables it.',
    icon: Users,
  },
  {
    mode: 'dedicated_appliance',
    label: 'Dedicated appliance',
    description: 'This computer is exclusively ACE. Boot, recovery, and remote access are reviewed separately.',
    icon: Server,
  },
]

export function HostFirstRun({
  projection,
  onSelectMode,
  children,
}: {
  readonly projection: HostFirstRunProjection
  readonly onSelectMode: (mode: HostRunMode) => Promise<void>
  readonly children?: ReactNode
}) {
  const unconfigured = projection.kind === 'unconfigured'
  const [selected, setSelected] = useState<HostRunMode | null>(
    unconfigured ? (projection.recommendedMode ?? null) : null,
  )
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    if (unconfigured) headingRef.current?.focus()
  }, [unconfigured])

  if (projection.kind !== 'unconfigured') return <>{children}</>

  const submit = async () => {
    if (!selected || pending) return
    setPending(true)
    setFailure(null)
    try {
      await onSelectMode(selected)
      // Resolution proves nothing about persistence. Stay in the applying
      // state until the host re-renders with a configured projection.
    } catch (error) {
      setFailure(error instanceof Error ? error.message : 'Mode selection did not complete.')
      setPending(false)
    }
  }

  return (
    <section aria-labelledby="ace-host-mode-question" className="mx-auto max-w-xl space-y-4">
      <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
        First run · one decision
      </div>
      <div>
        <h1
          ref={headingRef}
          id="ace-host-mode-question"
          tabIndex={-1}
          className="text-lg font-medium text-foreground outline-none"
        >
          {QUESTION}
        </h1>
        <RadioGroup
          aria-labelledby="ace-host-mode-question"
          className="mt-4"
          value={selected ?? undefined}
          disabled={pending}
          onValueChange={(value) => setSelected(value as HostRunMode)}
        >
          {MODE_OPTIONS.map(({ mode, label, description, icon: Icon }) => (
            <RadioGroupItem
              key={mode}
              value={mode}
              aria-label={`${label}: ${description}`}
              className="flex w-full cursor-pointer items-start gap-3 rounded-md border border-border p-3 data-[state=checked]:border-foreground/40 data-[state=checked]:bg-muted"
            >
              <Icon className="mt-0.5 size-4 text-muted-foreground" aria-hidden="true" />
              <span className="min-w-0">
                <span className="flex items-center gap-2 text-sm font-medium text-foreground">
                  {label}
                  {mode === 'personal' && projection.recommendedMode === 'personal' && (
                    <Badge variant="secondary">Recommended</Badge>
                  )}
                </span>
                <span className="mt-0.5 block text-xs text-muted-foreground">{description}</span>
              </span>
            </RadioGroupItem>
          ))}
        </RadioGroup>
      </div>

      {failure && (
        <p role="alert" className="flex items-center gap-2 text-sm text-destructive">
          <CircleAlert className="size-4" aria-hidden="true" />
          {failure}
        </p>
      )}

      <Button onClick={submit} disabled={!selected || pending}>
        {pending ? 'Saving mode…' : 'Continue to Atrium'}
      </Button>

      <Card>
        <CardContent className="space-y-3 pt-4">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Detected on this computer
          </div>
          <dl className="space-y-2">
            {(
              [
                ['Hardware', projection.detected.hardwareSummary],
                ['Runtime', projection.detected.runtimeSummary],
                ['Model profile', projection.detected.modelProfile],
                ['Quantization', projection.detected.quantization],
                ['Context', projection.detected.practicalContext],
                ['What to expect', projection.detected.expectation],
              ] as const
            ).map(([term, value]) => (
              <div key={term} className="flex items-baseline justify-between gap-4">
                <dt className="text-xs text-muted-foreground">{term}</dt>
                <dd className="text-right text-xs text-foreground">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="text-xs text-muted-foreground">
            This recommendation is detected, not another setup question. You can adjust the model plan and change a user-selected mode later in Settings.
          </p>
          <p className="flex items-center gap-2 border-t border-border pt-3 text-xs text-foreground">
            <LockKeyhole className="size-3.5 text-muted-foreground" aria-hidden="true" />
            Local only by default. Remote serving is enabled only by a separate operator action.
          </p>
        </CardContent>
      </Card>
    </section>
  )
}

function formatBytes(value: number): string {
  return value.toLocaleString('en-US')
}

function downloadLabel(download: ModelDownloadState): string {
  switch (download.status) {
    case 'not_started':
      return 'Not started'
    case 'downloading': {
      const progress =
        download.bytesDownloaded != null && download.bytesTotal != null
          ? ` — ${formatBytes(download.bytesDownloaded)} of ${formatBytes(download.bytesTotal)} bytes`
          : ''
      return `Downloading${progress}${download.resumable ? ' (resumable)' : ''}`
    }
    case 'interrupted': {
      const at =
        download.bytesDownloaded != null && download.bytesTotal != null
          ? ` at ${formatBytes(download.bytesDownloaded)} of ${formatBytes(download.bytesTotal)} bytes`
          : ''
      const resume = download.resumable
        ? ' — can resume where it left off'
        : ' — cannot be resumed'
      return `Interrupted${at}: ${download.reason}${resume}`
    }
    case 'failed':
      return `Failed: ${download.reason}`
    case 'complete':
      return 'Complete'
  }
}

function downloadIcon(download: ModelDownloadState): LucideIcon {
  switch (download.status) {
    case 'downloading':
      return Download
    case 'complete':
      return CircleCheck
    case 'failed':
    case 'interrupted':
      return CircleAlert
    case 'not_started':
      return CircleMinus
  }
}

// Four literal truths from the host, rendered without inference: a running
// or even loaded model never reads as generation success — only the
// supplied smoke-test result does.
export function HostRuntimeReadiness({
  projection,
}: {
  readonly projection: HostRuntimeReadinessProjection
}) {
  const { usableNow, download, modelLoaded, smokeTest, offlineReason, lowDiskReason } = projection
  const exactProgress = download.status === 'downloading'
    && download.bytesDownloaded != null
    && download.bytesTotal != null
    && download.bytesTotal > 0

  const rows: readonly {
    readonly term: string
    readonly value: string
    readonly icon: LucideIcon
  }[] = [
    {
      term: 'ACE usable now',
      value: usableNow ? 'Yes — ready to use' : 'Not yet usable',
      icon: usableNow ? CircleCheck : CircleMinus,
    },
    {
      term: 'Model download',
      value: downloadLabel(download),
      icon: downloadIcon(download),
    },
    {
      term: 'Model loaded',
      value: modelLoaded ? 'Loaded' : 'Not loaded',
      icon: modelLoaded ? CircleCheck : CircleMinus,
    },
    {
      term: 'Generation check',
      value:
        smokeTest.status === 'passed'
          ? 'Passed — a real generation completed'
          : smokeTest.status === 'failed'
            ? `Failed: ${smokeTest.reason}`
            : 'Not verified yet — no generation has completed',
      icon:
        smokeTest.status === 'passed'
          ? CircleCheck
          : smokeTest.status === 'failed'
            ? CircleAlert
            : CircleDashed,
    },
  ]

  return (
    <section aria-label="Local model readiness" aria-live="polite" className="space-y-2">
      <dl className="space-y-2">
        {rows.map(({ term, value, icon: Icon }) => (
          <div key={term} className="flex items-start gap-2">
            <Icon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <dt className="text-xs text-muted-foreground">{term}</dt>
              <dd className="text-xs text-foreground">{value}</dd>
            </div>
          </div>
        ))}
      </dl>
      {exactProgress && (
        <progress
          aria-label="Local model download"
          className="h-1.5 w-full accent-foreground"
          value={download.bytesDownloaded}
          max={download.bytesTotal}
        />
      )}
      {offlineReason && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <WifiOff className="size-3.5 shrink-0" aria-hidden="true" />
          Offline: {offlineReason}
        </p>
      )}
      {lowDiskReason && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <HardDrive className="size-3.5 shrink-0" aria-hidden="true" />
          Low disk: {lowDiskReason}
        </p>
      )}
      {download.status === 'failed' && download.resumable && (
        <Badge variant="outline">Download can resume</Badge>
      )}
    </section>
  )
}
