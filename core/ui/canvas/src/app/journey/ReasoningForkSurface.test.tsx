// core/ui/canvas/src/app/journey/ReasoningForkSurface.test.tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import type { JourneyForkTrace } from '../../types/canvas'

import { ReasoningForkSurface } from './ReasoningForkSurface'

const trace: JourneyForkTrace = {
  runId: 'reasoning_run:abc',
  checkpointSeq: 2,
  recommendation: 'fork',
  original: { label: 'original', lens: 'conclude', score: 0.25, conclusion: 'Ship the curated marketplace.' },
  best: { label: 'systems', lens: 'systems', score: 0.66, conclusion: 'Systems view: stage the rollout.' },
  forks: [
    { label: 'systems', lens: 'systems', score: 0.66, conclusion: 'Systems view: stage the rollout.' },
    { label: 'adversarial', lens: 'adversarial', score: 0.41, conclusion: 'Adversarial: gate-first, invite-only.' },
  ],
}

describe('ReasoningForkSurface', () => {
  test('shows the proactive line, collapsed by default', () => {
    const { container } = render(<ReasoningForkSurface trace={trace} />)
    expect(screen.getByText('paths not taken')).toBeTruthy()
    expect(screen.getByText(/explored 2 alternative paths/)).toBeTruthy()
    expect(screen.getByText(/one scores higher/)).toBeTruthy() // recommendation = fork
    // the comparison is hidden until the user expands it
    expect(container.querySelector('[data-test="fork-comparison"]')).toBeNull()
  })

  test('expands the branch comparison on click, marking the best as recommended', () => {
    const { container } = render(<ReasoningForkSurface trace={trace} />)
    fireEvent.click(screen.getByText('compare →'))
    expect(container.querySelector('[data-test="fork-comparison"]')).toBeTruthy()
    // original baseline + both forks each render
    expect(container.querySelector('[data-test="fork-branch-original"]')).toBeTruthy()
    expect(container.querySelector('[data-test="fork-branch-systems"]')).toBeTruthy()
    expect(container.querySelector('[data-test="fork-branch-adversarial"]')).toBeTruthy()
    // the best branch (systems) carries the recommended marker
    expect(screen.getByText('recommended')).toBeTruthy()
    // scores render as percentages
    expect(screen.getByText('66 / 100')).toBeTruthy()
    expect(screen.getByText('25 / 100')).toBeTruthy()
  })

  test('a keep_original recommendation reads differently', () => {
    render(
      <ReasoningForkSurface trace={{ ...trace, recommendation: 'keep_original', best: trace.original }} />,
    )
    expect(screen.getByText(/path I took still ranks best/)).toBeTruthy()
  })

  test('renders the optional capability lens score when present', () => {
    const withCap: JourneyForkTrace = {
      ...trace,
      forks: [{ ...trace.forks[0], capabilityDeltaScore: 0.72 }, trace.forks[1]],
    }
    render(<ReasoningForkSurface trace={withCap} />)
    fireEvent.click(screen.getByText('compare →'))
    expect(screen.getByText(/capability 72/)).toBeTruthy()
  })

  test('live mode: computes the fork on first expand (not before), then renders it', async () => {
    const fetchTrace = vi.fn().mockResolvedValue(trace)
    const { container } = render(<ReasoningForkSurface fetchTrace={fetchTrace} />)
    // collapsed: only an invitation — the expensive fork has NOT run
    expect(screen.getByText(/could re-reason this/)).toBeTruthy()
    expect(fetchTrace).not.toHaveBeenCalled()
    // expand → computes once, shows loading, then the comparison
    fireEvent.click(screen.getByText('compare →'))
    expect(fetchTrace).toHaveBeenCalledTimes(1)
    expect(container.querySelector('[data-test="fork-loading"]')).toBeTruthy()
    await waitFor(() => expect(container.querySelector('[data-test="fork-comparison"]')).toBeTruthy())
    expect(screen.getByText('recommended')).toBeTruthy()
  })

  test('live mode: shows an empty state when the run is not forkable (fetch → null)', async () => {
    const fetchTrace = vi.fn().mockResolvedValue(null)
    const { container } = render(<ReasoningForkSurface fetchTrace={fetchTrace} />)
    fireEvent.click(screen.getByText('compare →'))
    await waitFor(() => expect(container.querySelector('[data-test="fork-empty"]')).toBeTruthy())
  })
})
