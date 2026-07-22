import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, test, vi } from 'vitest'

import { landscapeApi, type LivingProductSnapshot } from '@/api/landscapeApi'
import { TooltipProvider } from '@/design/components'

import { ProductMap } from './ProductMap'
import { projectProductMap } from './productMapProjection'

function snapshot(overrides: Partial<LivingProductSnapshot> = {}): LivingProductSnapshot {
  return {
    schema_version: 'ace.living-product-snapshot.v1',
    projection_version: 'ace.living-product-projection.g1.v1',
    snapshot_id: 'product_snapshot:0123456789abcdef0123456789abcdef',
    authority: {
      mode: 'read_only',
      writes_permitted: false,
      autonomous_dispatch: false,
      operational_truth: 'relationships.operational',
      assertions_are_operational_only_when: 'accepted_and_projection_eligible',
      model_proposals_define_truth: false,
    },
    projection_state: {
      status: 'complete',
      assertion_states: { accepted: 1, contested: 1, rejected: 1 },
      issue_count: 0,
    },
    product: { id: 'product:ace', name: 'ACE' },
    intent: {
      directions: [{ id: 'product_direction:north', title: 'Make reasoning inspectable' }],
      visions: [],
    },
    projects: [{ id: 'project:canvas', name: 'Canvas' }],
    capabilities: {
      items: [
        { id: 'capability:graph', name: 'Living Product Graph' },
        { id: 'capability:atrium', name: 'Atrium' },
      ],
      quality: [],
    },
    relationships: {
      operational: [
        {
          id: 'operational_relationship:accepted',
          subject: 'capability:atrium',
          predicate: 'depends_on',
          object: 'capability:graph',
        },
      ],
      assertions: [
        {
          id: 'assertion:accepted',
          subject: 'capability:atrium',
          predicate: 'depends_on',
          object: 'capability:graph',
          status: 'accepted',
          proposal_confidence: 0.94,
          evidence_refs: ['observation:evidence'],
          projection_eligible: true,
        },
        {
          id: 'assertion:contested',
          subject: 'capability:graph',
          predicate: 'replaces',
          object: 'capability:atrium',
          status: 'contested',
          proposal_confidence: 0.42,
          evidence_refs: [],
          contradicting_assertions: ['assertion:accepted'],
          projection_eligible: false,
        },
        {
          id: 'assertion:rejected',
          subject: 'capability:graph',
          predicate: 'blocks',
          object: 'capability:atrium',
          status: 'rejected',
          evidence_refs: [],
          projection_eligible: false,
        },
      ],
      structural: [],
    },
    history: {
      assertion_events: [{ id: 'assertion_event:1', event_type: 'accepted', title: 'Relationship accepted' }],
    },
    decisions: [{ id: 'decision:1', title: 'Keep inspection read-only', rationale: 'Bound authority' }],
    foresight: {
      predictions: [{ id: 'prediction:1', title: 'Operators find product state faster' }],
      prediction_outcomes: [{ id: 'prediction_outcome:1', title: 'Operator located the decision' }],
      outcome_observations: [],
      action_outcomes: [],
    },
    intelligence: {
      observations: [
        { id: 'observation:evidence', title: 'Operator interview', observation_type: 'evidence' },
        { id: 'observation:correction', title: 'Correction: outcome was delayed', observation_type: 'correction' },
      ],
      insights: [],
    },
    work: {
      authority: 'runtime_records_only_not_living_roadmap',
      tasks: [],
      initiatives: [],
      milestones: [],
      work_items: [],
      agent_specs: [],
      roadmap_phases: [],
    },
    source_states: [
      { source: 'product', status: 'available', record_count: 1, required: true, limit: null },
      { source: 'capabilities', status: 'available', record_count: 2, required: true, limit: null },
    ],
    issues: [],
    ...overrides,
  }
}

describe('projectProductMap', () => {
  test('keeps operational truth, uncertainty, corrections, and outcomes distinct', () => {
    const projected = projectProductMap(snapshot())
    expect(projected.counts.relationships).toBe(1)
    expect(projected.assertions.accepted.map((row) => row.id)).toEqual(['assertion:accepted'])
    expect(projected.assertions.contested.map((row) => row.id)).toEqual(['assertion:contested'])
    expect(projected.assertions.rejected.map((row) => row.id)).toEqual(['assertion:rejected'])
    expect(projected.corrections.map((row) => row.id)).toEqual(['observation:correction'])
    expect(projected.outcomes.map((row) => row.id)).toEqual(['prediction_outcome:1'])
  })

  test('counts degraded sources and contested assertions as attention, not product truth', () => {
    const value = snapshot({
      projection_state: { status: 'degraded', assertion_states: { contested: 1 }, issue_count: 1 },
      source_states: [
        { source: 'product', status: 'available', record_count: 1, required: true, limit: 256 },
        { source: 'decisions', status: 'unavailable', record_count: 0, reason: 'timeout', required: true, limit: 256 },
      ],
      issues: [{ id: 'projection_issue:1', code: 'source_unavailable', recovery: 'Retry the read.' }],
    })
    const projected = projectProductMap(value)
    expect(projected.status).toBe('degraded')
    expect(projected.counts.attention).toBe(3)
    expect(projected.counts.relationships).toBe(1)
  })
})

describe('ProductMap', () => {
  test('the production loader settles after one landscape read', async () => {
    const read = vi.spyOn(landscapeApi, 'get').mockResolvedValue(snapshot())
    render(
      <MemoryRouter initialEntries={['/landscape']}>
        <TooltipProvider><ProductMap /></TooltipProvider>
      </MemoryRouter>,
    )
    await screen.findByRole('heading', { name: 'Product map' })
    expect(read).toHaveBeenCalledTimes(1)
    read.mockRestore()
  })

  test('renders the operator question hierarchy and stable receipts from one read', async () => {
    const loadSnapshot = vi.fn().mockResolvedValue(snapshot())
    render(
      <MemoryRouter initialEntries={['/landscape']}>
        <TooltipProvider><ProductMap loadSnapshot={loadSnapshot} /></TooltipProvider>
      </MemoryRouter>,
    )

    expect(screen.getByText('Reading the product map…')).toBeTruthy()
    await screen.findByRole('heading', { name: 'Product map' })
    expect(loadSnapshot).toHaveBeenCalledTimes(1)
    for (const heading of [
      'What exists',
      'How it connects',
      'Why we believe it',
      'What changed',
      'What happened next',
      'What needs attention',
    ]) {
      expect(screen.getByRole('heading', { name: heading })).toBeTruthy()
    }
    expect(screen.getAllByText('Living Product Graph').length).toBeGreaterThan(0)
    expect(screen.getByText('Keep inspection read-only')).toBeTruthy()
    expect(screen.getByText('Correction: outcome was delayed')).toBeTruthy()
    expect(screen.getByText('Operator located the decision')).toBeTruthy()
    expect(screen.getByTitle('product_snapshot:0123456789abcdef0123456789abcdef')).toBeTruthy()
  })

  test('shows contested and rejected assertions without promoting either into current links', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/landscape']}>
        <TooltipProvider><ProductMap loadSnapshot={() => Promise.resolve(snapshot())} /></TooltipProvider>
      </MemoryRouter>,
    )
    await screen.findByRole('heading', { name: 'Product map' })
    expect(container.querySelectorAll('[data-test="assertion-contested"]')).toHaveLength(1)
    expect(container.querySelectorAll('[data-test="assertion-rejected"]')).toHaveLength(1)
    const current = screen.getByRole('list', { name: 'Operational relationships' })
    expect(current.textContent).toContain('Atrium')
    expect(current.textContent).not.toContain('Replaces')
    expect(current.textContent).not.toContain('Blocks')
  })

  test('labels degraded data and preserves source failure context', async () => {
    const degraded = snapshot({
      projection_state: { status: 'degraded', assertion_states: {}, issue_count: 1 },
      source_states: [
        { source: 'decisions', status: 'unavailable', record_count: 0, reason: 'read timed out', required: true, limit: 256 },
      ],
      issues: [{ id: 'projection_issue:1', code: 'source_unavailable', detail: 'decisions', recovery: 'Retry the read.' }],
    })
    render(
      <MemoryRouter initialEntries={['/landscape']}>
        <TooltipProvider><ProductMap loadSnapshot={() => Promise.resolve(degraded)} /></TooltipProvider>
      </MemoryRouter>,
    )
    await screen.findByText('Snapshot is degraded.')
    expect(screen.getByText('read timed out')).toBeTruthy()
    expect(screen.getByText('Recovery: Retry the read.')).toBeTruthy()
  })

  test('failure is explicit and retry performs another read only', async () => {
    const loadSnapshot = vi
      .fn<[], Promise<LivingProductSnapshot>>()
      .mockRejectedValueOnce(new Error('GET /product/landscape → 503'))
      .mockResolvedValueOnce(snapshot())
    render(
      <MemoryRouter initialEntries={['/landscape']}>
        <TooltipProvider><ProductMap loadSnapshot={loadSnapshot} /></TooltipProvider>
      </MemoryRouter>,
    )
    await screen.findByRole('heading', { name: 'Product map unavailable' })
    expect(screen.getByText('No state was changed.', { exact: false })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Retry read' }))
    await waitFor(() => expect(loadSnapshot).toHaveBeenCalledTimes(2))
    await screen.findByRole('heading', { name: 'Product map' })
  })
})
