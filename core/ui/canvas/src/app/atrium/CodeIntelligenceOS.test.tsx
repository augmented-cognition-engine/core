import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import type { AtriumCodeJourneyResponse } from '@/api/codeIntelligenceApi'
import { TooltipProvider } from '@/design/components'

import { CodeIntelligenceOS } from './CodeIntelligenceOS'

function response(): AtriumCodeJourneyResponse {
  const digest = `sha256:${'a'.repeat(64)}`
  return {
    contract: 'ace.code-intelligence.atrium-journey-response/v1alpha1',
    lens: {
      contract: 'ace.code-intelligence.atrium-code-lens/v1alpha1',
      index: {
        repository: 'ace-core', revision: 'abc123', dirty: true, working_tree_digest: digest,
        analysis_profile: 'python-local-static-v1', topology: 'single-local-git-repository',
        supported_languages: ['python'], observed_languages: ['python', 'typescript'], generated_at: '2026-08-14T12:00:00Z',
      },
      query: 'What breaks?', target_path: 'core/engine/mcp/tools.py',
      nodes: [
        { node_id: 'repository:1', kind: 'repository', label: 'ace-core', path: null, symbol: null, confidence: 'observed', detail: 'revision abc123' },
        { node_id: 'file:1', kind: 'api', label: 'tools.py', path: 'core/engine/mcp/tools.py', symbol: null, confidence: 'observed', detail: null },
        { node_id: 'contributor:1', kind: 'contributor', label: 'Example Author', path: null, symbol: null, confidence: 'supported', detail: 'Historical contributor; not current authority.' },
      ],
      edges: [{ source: 'repository:1', target: 'file:1', relation: 'contains', derivation: 'parser', confidence: 'observed', evidence_refs: [] }],
      impact: {
        target_path: 'core/engine/mcp/tools.py', direct_dependents: ['ace_mcp_server.py'],
        transitive_dependents: ['tests/test_mcp_tools.py'], affected_tests: ['tests/test_mcp_tools.py'],
        known_coverage_gaps: ['Runtime dispatch is not observed.'], confidence: 'supported', basis: 'Static import graph and lexical test links.',
      },
      disconnected_symbols: [{
        symbol_id: 'symbol:maybe', path: 'core/engine/example.py', symbol: 'plugin_entrypoint', line_start: 12,
        reason: 'No static inbound edge; may still be a CLI, plugin, framework, or reflective entrypoint.', confidence: 'inferred', evidence_ref: 'anchor:1',
      }],
      evidence: [{
        path: 'core/engine/mcp/tools.py', line_start: 1, line_end: 80, content_digest: digest,
        derivation: 'parser', confidence: 'observed', explanation: 'Exact target file in the scanned repository revision.',
      }],
      omissions: ['Static reachability does not prove runtime reachability or safe deletion.'], degraded_reasons: [],
      read_only: true, source_authority: false, reasoning_authority: false, delivery_authority: false, effect_authority: false,
    },
    manifest: {
      contract: 'ace.code-intelligence.context-manifest/v1alpha1', index_id: 'code_index:1', lens_id: 'atrium_code_lens:1',
      blocks: [{ block_id: 'block:1', path: 'core/engine/mcp/tools.py', line_start: 1, line_end: 80, body_digest: digest, byte_count: 1200, token_estimate: 300, reason: 'target', evidence_ref: 'anchor:1' }],
      total_bytes: 1200, total_token_estimate: 300, max_files: 8, max_bytes: 24000, omissions: [], degraded_reasons: [], execution_authority: false,
    },
    handoff: {
      receiver_ref: 'coding-agent:provider-neutral', requested_change: 'What breaks?', requested_outputs: ['analysis'],
      index_id: 'code_index:1', lens_id: 'atrium_code_lens:1', manifest_id: 'manifest:1', included_paths: ['core/engine/mcp/tools.py'],
      provider_neutral: true, grants_source_authority: false, grants_reasoning_authority: false,
      grants_delivery_authority: false, grants_effect_authority: false, execution_authority_revalidation_required: true,
    },
    scanner_stats: { files: 2497 }, limitations: ['Python static profile only.'], context_bodies_exposed: false,
    repository_read_only: true, product_history_write: false, local_cache_may_write: true,
    index_snapshot_id: `code_index_snapshot:${'1'.repeat(32)}`,
    index_snapshot_digest: digest,
    index_generation: 2, index_reopened: true, index_store_provider_free: true,
    index_snapshot_is_product_truth: false,
  }
}

describe('Atrium Code lens', () => {
  it('renders impact, provenance, uncertainty, and a body-free authority boundary', async () => {
    const runJourney = vi.fn().mockResolvedValue(response())
    render(
      <MemoryRouter initialEntries={['/atrium/code']}>
        <TooltipProvider><CodeIntelligenceOS runJourney={runJourney} /></TooltipProvider>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Inspect' }))
    await waitFor(() => expect(runJourney).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('Change impact')).toBeTruthy()
    expect(screen.getAllByText('tests/test_mcp_tools.py').length).toBeGreaterThan(0)
    expect(screen.getByText('Evidence and provenance')).toBeTruthy()
    expect(screen.getByText('plugin_entrypoint')).toBeTruthy()
    expect(screen.getByText('Historical contributor; not current authority.')).toBeTruthy()
    expect(screen.getByText('Bounded coding-agent handoff')).toBeTruthy()
    expect(screen.getAllByText('Not granted')).toHaveLength(5)
    expect(screen.getByText('Atrium exposes manifest receipts, not source bodies.', { exact: false })).toBeTruthy()
  })

  it('clears a prior result before a failed reinspection, so no stale result survives', async () => {
    const runJourney = vi.fn().mockResolvedValueOnce(response()).mockRejectedValueOnce(new Error('journey unavailable'))
    render(
      <MemoryRouter initialEntries={['/atrium/code']}>
        <TooltipProvider><CodeIntelligenceOS runJourney={runJourney} /></TooltipProvider>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Inspect' }))
    expect(await screen.findByText('Change impact')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Inspect' }))
    await waitFor(() => expect(runJourney).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('journey unavailable')).toBeTruthy()
    expect(screen.queryByText('Change impact')).toBeNull()
    expect(screen.queryByText('tests/test_mcp_tools.py')).toBeNull()
  })

  it('bounds the target path and query inputs to the backend max of 500 characters', async () => {
    const runJourney = vi.fn().mockResolvedValue(response())
    render(
      <MemoryRouter initialEntries={['/atrium/code']}>
        <TooltipProvider><CodeIntelligenceOS runJourney={runJourney} /></TooltipProvider>
      </MemoryRouter>,
    )

    const overlong = 'x'.repeat(600)
    const targetInput = screen.getByLabelText('Target path') as HTMLInputElement
    fireEvent.change(targetInput, { target: { value: overlong } })
    expect(targetInput.value.length).toBe(500)

    const queryInput = screen.getByLabelText('Change question') as HTMLInputElement
    fireEvent.change(queryInput, { target: { value: overlong } })
    expect(queryInput.value.length).toBe(500)

    fireEvent.click(screen.getByRole('button', { name: 'Inspect' }))
    await waitFor(() => expect(runJourney).toHaveBeenCalledTimes(1))
    const sent = runJourney.mock.calls[0][0]
    expect(sent.target_path.length).toBe(500)
    expect(sent.query.length).toBe(500)
  })

  it('locks the target/query inputs during an in-flight inspection and keeps the result bound to what was actually submitted', async () => {
    let resolveJourney: (value: AtriumCodeJourneyResponse) => void = () => {}
    const pending = new Promise<AtriumCodeJourneyResponse>((resolve) => {
      resolveJourney = resolve
    })
    const runJourney = vi.fn().mockReturnValue(pending)
    render(
      <MemoryRouter initialEntries={['/atrium/code']}>
        <TooltipProvider><CodeIntelligenceOS runJourney={runJourney} /></TooltipProvider>
      </MemoryRouter>,
    )

    const targetInput = screen.getByLabelText('Target path') as HTMLInputElement
    const queryInput = screen.getByLabelText('Change question') as HTMLInputElement
    const submittedTarget = targetInput.value
    const submittedQuery = queryInput.value

    fireEvent.click(screen.getByRole('button', { name: 'Inspect' }))
    await waitFor(() => expect(runJourney).toHaveBeenCalledTimes(1))

    expect(targetInput.disabled).toBe(true)
    expect(queryInput.disabled).toBe(true)

    // Editing while the request is in flight must not change what was submitted.
    fireEvent.change(targetInput, { target: { value: 'core/engine/some_other_module.py' } })
    fireEvent.change(queryInput, { target: { value: 'A completely unrelated question?' } })
    expect(targetInput.value).toBe(submittedTarget)
    expect(queryInput.value).toBe(submittedQuery)

    resolveJourney(response())
    expect(await screen.findByText('Change impact')).toBeTruthy()

    // The result heading is bound to the immutable submitted values, not live input state.
    const heading = screen.getByTestId('journey-heading')
    expect(heading.textContent).toContain(submittedTarget)
    expect(heading.textContent).toContain(submittedQuery)
    expect(heading.textContent).not.toContain('core/engine/some_other_module.py')

    // Inputs are editable again post-completion, but that must not retroactively
    // relabel the result already on screen — a second submission never happened.
    fireEvent.change(targetInput, { target: { value: 'core/engine/some_other_module.py' } })
    expect(screen.getByTestId('journey-heading').textContent).toContain(submittedTarget)
    expect(runJourney).toHaveBeenCalledTimes(1)
  })

  it('clamps a long, control-character-laden error to a short fixed maximum', async () => {
    const hostile = String.fromCharCode(1) + String.fromCharCode(7) + 'x'.repeat(1000)
    const runJourney = vi.fn().mockRejectedValue(new Error(hostile))
    render(
      <MemoryRouter initialEntries={['/atrium/code']}>
        <TooltipProvider><CodeIntelligenceOS runJourney={runJourney} /></TooltipProvider>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Inspect' }))
    await waitFor(() => expect(runJourney).toHaveBeenCalledTimes(1))

    await screen.findByText('Journey unavailable')
    const description = document.querySelector('[data-slot="alert-description"]')
    expect(description).toBeTruthy()
    const shown = description!.textContent ?? ''
    expect(shown.length).toBeLessThan(220)
    expect(shown).not.toContain(hostile)
    expect(shown).not.toContain(String.fromCharCode(1))
    expect(shown).not.toContain(String.fromCharCode(7))
  })
})
