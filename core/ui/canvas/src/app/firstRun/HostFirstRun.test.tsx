import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import {
  HostFirstRun,
  HostRuntimeReadiness,
  type HostDetectedEnvironment,
  type HostFirstRunProjection,
  type HostRunMode,
  type HostRuntimeReadinessProjection,
} from './HostFirstRun'

const QUESTION = 'How should ACE run on this computer?'

const detected: HostDetectedEnvironment = {
  hardwareSummary: 'AMD Ryzen 9 7940HS · 32 GB usable RAM',
  runtimeSummary: 'Linux · llama.cpp runtime detected',
  modelProfile: 'Qwen3.8 27B GGUF',
  quantization: 'Q4-class recommendation',
  practicalContext: '65,536 configured · active window optimized by ACE memory',
  expectation: 'Observed deployment evidence: about 2.9 tokens/sec; this machine still requires a smoke test.',
}

const unconfigured: HostFirstRunProjection = {
  kind: 'unconfigured',
  detected,
  recommendedMode: 'personal',
}

const neverResolves = () => new Promise<void>(() => {})

function renderFirstRun(overrides: {
  projection?: HostFirstRunProjection
  onSelectMode?: (mode: HostRunMode) => Promise<void>
} = {}) {
  return render(
    <HostFirstRun
      projection={overrides.projection ?? unconfigured}
      onSelectMode={overrides.onSelectMode ?? neverResolves}
    >
      <div>Atrium</div>
    </HostFirstRun>,
  )
}

function modeRadio(label: string): HTMLElement {
  return screen.getByRole('radio', { name: new RegExp(label) })
}

describe('HostFirstRun', () => {
  it('bypasses first run for an existing configured installation', () => {
    renderFirstRun({ projection: { kind: 'configured', mode: 'personal' } })
    expect(screen.getByText('Atrium')).toBeTruthy()
    expect(screen.queryByRole('heading', { name: QUESTION })).toBeNull()
  })

  it('bypasses the prompt for administrator-fixed Shared and Appliance modes', () => {
    for (const mode of ['shared_server', 'dedicated_appliance'] as const) {
      const view = renderFirstRun({ projection: { kind: 'admin_fixed', mode } })
      expect(screen.getByText('Atrium')).toBeTruthy()
      expect(screen.queryByRole('heading', { name: QUESTION })).toBeNull()
      view.unmount()
    }
  })

  it('asks exactly one grouped question and moves focus to its heading', () => {
    renderFirstRun()
    const heading = screen.getByRole('heading', { name: QUESTION })
    expect(document.activeElement).toBe(heading)
    expect(screen.getByRole('radiogroup', { name: QUESTION })).toBeTruthy()
    expect(screen.getAllByRole('radio')).toHaveLength(3)
    expect(screen.queryByText('Atrium')).toBeNull()
  })

  it('preselects Personal only when the host recommends it', () => {
    const recommended = renderFirstRun()
    expect(modeRadio('Personal').getAttribute('aria-checked')).toBe('true')
    expect(screen.getByText('Recommended')).toBeTruthy()
    recommended.unmount()

    renderFirstRun({ projection: { kind: 'unconfigured', detected } })
    expect(screen.queryByText('Recommended')).toBeNull()
    expect(screen.getAllByRole('radio').every((radio) => radio.getAttribute('aria-checked') === 'false')).toBe(true)
    expect((screen.getByRole('button', { name: 'Continue to Atrium' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('submits the exact selected mode and no appliance-side options', async () => {
    const onSelectMode = vi.fn().mockImplementation(neverResolves)
    renderFirstRun({ onSelectMode })
    fireEvent.click(modeRadio('Shared server'))
    fireEvent.click(screen.getByRole('button', { name: 'Continue to Atrium' }))
    await waitFor(() => expect(onSelectMode).toHaveBeenCalledWith('shared_server'))
    expect(onSelectMode).toHaveBeenCalledTimes(1)
    expect(screen.queryByText(/auto-login|hostname|Tailscale|cleanup|boot target/i)).toBeNull()
  })

  it('keeps a truthful pending state until the host returns a configured projection', async () => {
    let resolveSelection!: () => void
    const onSelectMode = vi.fn().mockImplementation(
      () => new Promise<void>((resolve) => { resolveSelection = resolve }),
    )
    renderFirstRun({ onSelectMode })
    fireEvent.click(screen.getByRole('button', { name: 'Continue to Atrium' }))
    expect((screen.getByRole('button', { name: 'Saving mode…' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByRole('radiogroup', { name: QUESTION }).getAttribute('data-disabled')).not.toBeNull()
    resolveSelection()
    await waitFor(() => expect(onSelectMode).toHaveBeenCalledTimes(1))
    expect(screen.getByRole('button', { name: 'Saving mode…' })).toBeTruthy()
    expect(screen.queryByText('Atrium')).toBeNull()
  })

  it('surfaces persistence failure and re-enables the choice', async () => {
    const onSelectMode = vi.fn().mockRejectedValue(new Error('Mode could not be persisted.'))
    renderFirstRun({ onSelectMode })
    fireEvent.click(screen.getByRole('button', { name: 'Continue to Atrium' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Mode could not be persisted.')
    expect((screen.getByRole('button', { name: 'Continue to Atrium' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('presents detection and recommendation as status with a local-only boundary', () => {
    renderFirstRun()
    for (const value of Object.values(detected)) expect(screen.getByText(value)).toBeTruthy()
    expect(screen.getByText(/detected, not another setup question/i)).toBeTruthy()
    expect(screen.getByText(/change a user-selected mode later in Settings/i)).toBeTruthy()
    expect(screen.getByText(/Local only by default/i)).toBeTruthy()
  })
})

describe('HostRuntimeReadiness', () => {
  const baseline: HostRuntimeReadinessProjection = {
    usableNow: false,
    download: { status: 'not_started' },
    modelLoaded: false,
    smokeTest: { status: 'pending' },
  }

  it('keeps usable, downloaded, loaded, and real-generation truth independent', () => {
    render(
      <HostRuntimeReadiness projection={{
        ...baseline,
        usableNow: true,
        download: { status: 'complete' },
        modelLoaded: true,
      }} />,
    )
    expect(screen.getByText('Yes — ready to use')).toBeTruthy()
    expect(screen.getByText('Complete')).toBeTruthy()
    expect(screen.getByText('Loaded')).toBeTruthy()
    expect(screen.getByText('Not verified yet — no generation has completed')).toBeTruthy()
    expect(screen.queryByText(/real generation completed/)).toBeNull()
  })

  it('exposes exact resumable download progress to assistive technology', () => {
    render(
      <HostRuntimeReadiness projection={{
        ...baseline,
        download: {
          status: 'downloading',
          bytesDownloaded: 3_221_225_472,
          bytesTotal: 4_294_967_296,
          resumable: true,
        },
      }} />,
    )
    expect(screen.getByText(/3,221,225,472 of 4,294,967,296 bytes/)).toBeTruthy()
    const progress = screen.getByRole('progressbar', { name: 'Local model download' })
    expect(progress.getAttribute('value')).toBe('3221225472')
    expect(progress.getAttribute('max')).toBe('4294967296')
  })

  it('renders interrupted, offline, low-disk, and resumable failure truth', () => {
    const interrupted = render(
      <HostRuntimeReadiness projection={{
        ...baseline,
        download: {
          status: 'interrupted',
          reason: 'connection lost',
          bytesDownloaded: 100,
          bytesTotal: 200,
          resumable: true,
        },
        offlineReason: 'No network route is available.',
        lowDiskReason: '12 GB more space is required.',
      }} />,
    )
    expect(screen.getByText(/Interrupted at 100 of 200 bytes/)).toBeTruthy()
    expect(screen.getByText(/Offline: No network route is available/)).toBeTruthy()
    expect(screen.getByText(/Low disk: 12 GB more space is required/)).toBeTruthy()
    interrupted.unmount()

    render(
      <HostRuntimeReadiness projection={{
        ...baseline,
        download: { status: 'failed', reason: 'checksum mismatch', resumable: true },
        smokeTest: { status: 'failed', reason: 'generation timed out' },
      }} />,
    )
    expect(screen.getByText('Failed: checksum mismatch')).toBeTruthy()
    expect(screen.getByText('Download can resume')).toBeTruthy()
    expect(screen.getByText('Failed: generation timed out')).toBeTruthy()
  })

  it('reports generation success only from a supplied passed smoke test', () => {
    render(
      <HostRuntimeReadiness projection={{
        usableNow: true,
        download: { status: 'complete' },
        modelLoaded: true,
        smokeTest: { status: 'passed' },
      }} />,
    )
    expect(screen.getByText('Passed — a real generation completed')).toBeTruthy()
  })
})
