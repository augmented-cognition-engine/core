import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  IntelligenceCatalogApiError,
  queryDomainPackActivationHistory,
  type DomainPackActivationHistory,
  type DomainPackLifecycleCapability,
  type InstalledDomainPackPreview,
  type IntelligenceConsumerCatalog,
  type IntelligenceConsumerInterface,
} from '@/api/intelligenceCatalogApi'

import {
  ConsumerContractLedger,
  DomainPackLedger,
  groupConsumerInterfaces,
  groupLifecycleCapabilities,
  PackActivationReader,
} from './DomainPackConsumers'

vi.mock('@/api/intelligenceCatalogApi', async () => {
  const actual = await vi.importActual<typeof import('@/api/intelligenceCatalogApi')>(
    '@/api/intelligenceCatalogApi',
  )
  return { ...actual, queryDomainPackActivationHistory: vi.fn() }
})

const activationHistory: DomainPackActivationHistory = {
  contract: 'ace.http.domain-pack-activation-history/v1alpha1',
  authority_stage: 'historical_reference',
  live_authority: false,
  product_id: 'product:acme',
  activation_key: 'world-ai',
  activation_id: 'activation:acme-world',
  current: {
    revision: 2,
    revision_id: 'revision:2',
    revision_digest: 'sha256:aaaa',
    action: 'upgrade',
    state: 'active',
    pack: { pack_id: 'world', pack_version: '1.1.0', compiled_pack_id: 'pack_ir:aaaa', pack_digest: 'sha256:aaaa' },
    overlay: {
      contract: 'ace.intelligence.compiled-overlay/v1alpha1',
      overlay_id: 'overlay:world',
      version: '1',
      pack_id: 'world',
      pack_version: '1.1.0',
      pack_digest: 'sha256:aaaa',
      values: [{ slot_id: 'tone', value_json: '"formal"' }],
      compiled_overlay_id: 'overlay_ir:aaaa',
      overlay_digest: 'sha256:aaaa',
    },
    plan_id: 'plan:2',
    plan_digest: 'sha256:plan2',
    approval_receipt_ref: 'receipt:approval2',
    approval_receipt_digest: 'sha256:approval2',
    actor_ref: 'actor:owner',
    occurred_at: '2026-08-01T00:00:00Z',
    commit_receipt_id: 'receipt:commit2',
    commit_receipt_digest: 'sha256:commit2',
    committed_at: '2026-08-01T00:00:01Z',
  },
  history: [
    {
      revision: 1,
      revision_id: 'revision:1',
      revision_digest: 'sha256:bbbb',
      action: 'initial_activation',
      state: 'active',
      pack: { pack_id: 'world', pack_version: '1.0.0', compiled_pack_id: 'pack_ir:bbbb', pack_digest: 'sha256:bbbb' },
      overlay: {
        contract: 'ace.intelligence.compiled-overlay/v1alpha1',
        overlay_id: 'overlay:world',
        version: '1',
        pack_id: 'world',
        pack_version: '1.0.0',
        pack_digest: 'sha256:bbbb',
        values: [],
        compiled_overlay_id: 'overlay_ir:bbbb',
        overlay_digest: 'sha256:bbbb',
      },
      plan_id: 'plan:1',
      plan_digest: 'sha256:plan1',
      approval_receipt_ref: 'receipt:approval1',
      approval_receipt_digest: 'sha256:approval1',
      actor_ref: 'actor:owner',
      occurred_at: '2026-07-01T00:00:00Z',
      commit_receipt_id: 'receipt:commit1',
      commit_receipt_digest: 'sha256:commit1',
      committed_at: '2026-07-01T00:00:01Z',
    },
  ],
}

const pack: InstalledDomainPackPreview = {
  distribution: 'ace-domain-market-intelligence',
  distribution_version: '1.8.0',
  manifest_resource_path: 'domain_packs/market/manifest.json',
  manifest_digest: `sha256:${'a'.repeat(64)}`,
  manifest: {
    contract: 'ace.intelligence.domain-pack-manifest/v1',
    metadata: {
      pack_id: 'market_intelligence',
      version: '1.4.0',
      display_name: 'Market Intelligence',
      description: 'A declarative starting point for market intelligence.',
    },
    resources: [{ resource_id: 'ontology', path: 'ontology.json', digest: `sha256:${'b'.repeat(64)}` }],
    modules: [{ module_id: 'ontology', contract: 'ace.intelligence.ontology/v1alpha1', resource_id: 'ontology', depends_on: [] }],
    capability_requirements: [],
    authority_requests: [],
    overlay_slots: [{ slot_id: 'market_scope', value_kind: 'string_list', required: true }],
  },
  lifecycle: [
    {
      capability_id: 'installed_material',
      label: 'Installed material',
      availability: 'available',
      contract_refs: [],
      endpoint: 'GET /v1/intelligence/catalog/packs',
      boundary: 'The exact validated manifest is installed; no authority is granted.',
    },
    {
      capability_id: 'reviewed_customization',
      label: 'Local customization',
      availability: 'contract_only',
      contract_refs: ['ace.intelligence.organization-overlay/v1alpha1'],
      endpoint: null,
      boundary: 'One slot is declared, but active values are not exposed.',
    },
    {
      capability_id: 'upgrade_discovery',
      label: 'Upgrade',
      availability: 'not_exposed',
      contract_refs: [],
      endpoint: null,
      boundary: 'No update discovery is exposed.',
    },
  ],
}

const consumers: IntelligenceConsumerCatalog = {
  contract: 'ace.http.intelligence-consumer-catalog/v1alpha1',
  interfaces: [
    {
      interface_id: 'intelligence_resource_http',
      label: 'Intelligence Resource API',
      kind: 'api',
      availability: 'available',
      version: 'v1',
      endpoint: 'POST /v1/intelligence/resources/query',
      contract_refs: ['ace.intelligence.resource-plane-page/v1alpha1'],
      operations: ['point-in-time query'],
      permission_boundary: 'Every query reauthenticates product scope.',
      provenance_boundary: 'Every record carries an exact reference and provenance.',
      delivery_boundary: 'Authenticated JSON pages only.',
    },
    {
      interface_id: 'intelligence_webhook',
      label: 'Intelligence webhook',
      kind: 'webhook',
      availability: 'not_exposed',
      version: null,
      endpoint: null,
      contract_refs: [],
      operations: [],
      permission_boundary: 'No authorization contract is exposed.',
      provenance_boundary: 'No signed outbound provenance envelope is exposed.',
      delivery_boundary: 'Existing inbound webhooks are unrelated.',
    },
    {
      interface_id: 'intelligence_subscription',
      label: 'Intelligence subscription',
      kind: 'subscription',
      availability: 'contract_only',
      version: null,
      endpoint: null,
      contract_refs: ['ace.intelligence.subscription/v1alpha1'],
      operations: ['digest'],
      permission_boundary: 'A subscription is not an API credential.',
      provenance_boundary: 'Delivery provenance is not exposed.',
      delivery_boundary: 'No customer-facing delivery endpoint is exposed.',
    },
    {
      interface_id: 'investigation_board',
      label: 'Investigation Board',
      kind: 'handoff',
      availability: 'navigation_only',
      version: null,
      endpoint: '/board',
      contract_refs: [],
      operations: [],
      permission_boundary: 'The application route applies its own boundary.',
      provenance_boundary: 'No consumer payload contract is exposed.',
      delivery_boundary: 'Existing in-product destination only.',
    },
  ],
  unresolved_dependencies: ['Downstream provenance return contract'],
}

describe('Domain Pack and Consumers', () => {
  it('separates release posture from local Pack installation', () => {
    render(<DomainPackLedger packs={[]} onReviewBuild={vi.fn()} />)

    expect(screen.getByText('World Intelligence')).toBeTruthy()
    expect(screen.getByText('Custom Intelligence')).toBeTruthy()
    expect(screen.getByText(/Release posture does not imply local installation/)).toBeTruthy()
  })

  it('distinguishes installed Pack defaults from local override and update state', () => {
    render(<DomainPackLedger packs={[pack]} onReviewBuild={vi.fn()} />)

    expect(screen.getAllByText('Market Intelligence')).toHaveLength(2)
    expect(screen.getByText('Pack 1.4.0')).toBeTruthy()
    expect(screen.getByText('1 modules · 1 resources')).toBeTruthy()
    expect(screen.getByText('1 declared overlay slot')).toBeTruthy()
    expect(screen.getByText('World Intelligence')).toBeTruthy()
    expect(screen.getByText('Custom Intelligence')).toBeTruthy()
    expect(screen.getByText(/Active values are not inferred/)).toBeTruthy()

    screen.getByText('Install, customize, upgrade, history, and rollback').click()
    expect(screen.getByText('Usable now')).toBeTruthy()
    expect(screen.getByText('Defined, not active')).toBeTruthy()
    expect(screen.getByText('Installed material')).toBeTruthy()
    expect(screen.getByText('Local customization')).toBeTruthy()
    expect(screen.getByText('One slot is declared, but active values are not exposed.')).toBeTruthy()
    expect(screen.getAllByText('Defined')).toHaveLength(1)
    expect(screen.queryByText('Contract only')).toBeNull()

    screen.getByText('Not exposed (1)').click()
    expect(screen.getByText('Upgrade')).toBeTruthy()
    expect(screen.getByText('No update discovery is exposed.')).toBeTruthy()
    expect(screen.getByText('Advanced Build and operator detail')).toBeTruthy()
  })

  it('shows exact consumer contracts without promoting unsupported delivery', () => {
    render(
      <MemoryRouter>
        <ConsumerContractLedger catalog={consumers} />
      </MemoryRouter>,
    )

    expect(screen.getByText('Usable now')).toBeTruthy()
    expect(screen.getByText('POST /v1/intelligence/resources/query')).toBeTruthy()
    expect(screen.getByText('ace.intelligence.resource-plane-page/v1alpha1')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Open Investigation Board' }).getAttribute('href')).toBe('/board')
    expect(screen.getByText('Downstream provenance return contract')).toBeTruthy()
    expect(screen.getByText(/consumer subscription is not an API credential/)).toBeTruthy()

    expect(screen.getByRole('heading', { name: 'In-product route' })).toBeTruthy()
    expect(screen.getByText('Bounded in-product navigation, not payload delivery.')).toBeTruthy()

    expect(screen.getByRole('heading', { name: 'Defined' })).toBeTruthy()
    expect(screen.getByText('Intelligence subscription')).toBeTruthy()
    expect(screen.getByText('A contract exists. Nothing is delivered through it yet.')).toBeTruthy()
    const definedBadge = screen.getAllByText('Defined').find((element) => element.tagName === 'SPAN')
    expect(definedBadge).toBeTruthy()
    expect(definedBadge?.className).not.toContain('text-warning')

    screen.getByText('Not exposed (1)').click()
    expect(screen.getByText('Intelligence webhook')).toBeTruthy()
  })
})

describe('groupLifecycleCapabilities', () => {
  it('routes every capability into exactly one group, preserving manifest order within each group', () => {
    const capabilities: DomainPackLifecycleCapability[] = [
      { ...pack.lifecycle[0], capability_id: 'installed_material', availability: 'available' },
      { ...pack.lifecycle[0], capability_id: 'reviewed_customization', availability: 'contract_only' },
      { ...pack.lifecycle[0], capability_id: 'upgrade_discovery', availability: 'not_exposed' },
      { ...pack.lifecycle[0], capability_id: 'activation_history', availability: 'contract_only' },
      { ...pack.lifecycle[0], capability_id: 'rollback', availability: 'not_exposed' },
    ]

    const grouped = groupLifecycleCapabilities(capabilities)

    expect(grouped.usable.map((item) => item.capability_id)).toEqual(['installed_material'])
    expect(grouped.defined.map((item) => item.capability_id)).toEqual(['reviewed_customization', 'activation_history'])
    expect(grouped.notExposed.map((item) => item.capability_id)).toEqual(['upgrade_discovery', 'rollback'])

    const allIds = [...grouped.usable, ...grouped.defined, ...grouped.notExposed].map((item) => item.capability_id)
    expect(allIds).toHaveLength(capabilities.length)
    expect(new Set(allIds).size).toBe(capabilities.length)
  })
})

describe('groupConsumerInterfaces', () => {
  it('routes every interface into exactly one group, preserving catalog order within each group', () => {
    const interfaces: IntelligenceConsumerInterface[] = [
      { ...consumers.interfaces[0], interface_id: 'a', availability: 'available' },
      { ...consumers.interfaces[0], interface_id: 'b', availability: 'contract_only' },
      { ...consumers.interfaces[0], interface_id: 'c', availability: 'not_exposed' },
      { ...consumers.interfaces[0], interface_id: 'd', availability: 'available' },
      { ...consumers.interfaces[0], interface_id: 'e', availability: 'navigation_only' },
      { ...consumers.interfaces[0], interface_id: 'f', availability: 'contract_only' },
    ]

    const grouped = groupConsumerInterfaces(interfaces)

    expect(grouped.usable.map((item) => item.interface_id)).toEqual(['a', 'd'])
    expect(grouped.navigationOnly.map((item) => item.interface_id)).toEqual(['e'])
    expect(grouped.defined.map((item) => item.interface_id)).toEqual(['b', 'f'])
    expect(grouped.notExposed.map((item) => item.interface_id)).toEqual(['c'])

    const allIds = [
      ...grouped.usable,
      ...grouped.navigationOnly,
      ...grouped.defined,
      ...grouped.notExposed,
    ].map((item) => item.interface_id)
    expect(allIds).toHaveLength(interfaces.length)
    expect(new Set(allIds).size).toBe(interfaces.length)
  })
})

describe('PackActivationReader', () => {
  beforeEach(() => {
    vi.mocked(queryDomainPackActivationHistory).mockReset()
  })

  it('shows an empty state and disables reading before an activation key is supplied', () => {
    render(<PackActivationReader />)

    expect(screen.getByText('No activation key has been read yet.')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Read activation' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(/Not inferred from an installed Pack ID/)).toBeTruthy()
  })

  it('reads the exact typed activation key, never an installed Pack ID', async () => {
    vi.mocked(queryDomainPackActivationHistory).mockResolvedValue(activationHistory)

    render(<PackActivationReader />)
    fireEvent.change(screen.getByLabelText('Activation key'), { target: { value: 'world-ai' } })
    fireEvent.click(screen.getByRole('button', { name: 'Read activation' }))

    expect(screen.getByText('Reading activation…')).toBeTruthy()
    await waitFor(() => expect(queryDomainPackActivationHistory).toHaveBeenCalledWith('world-ai'))

    expect(await screen.findByText('live_authority: false')).toBeTruthy()
    expect(screen.getAllByText(/does not authorize customization, upgrade, rollback, or activation/)).toHaveLength(2)
    expect(screen.getByText('Current governed revision')).toBeTruthy()
    expect(screen.getByText('Revision r1')).toBeTruthy()
    expect(screen.getByText(/Append-only history · newest first · 1 revision/)).toBeTruthy()
    expect(screen.getByText('tone')).toBeTruthy()
    expect(screen.getByText('"formal"')).toBeTruthy()
  })

  it('renders a distinct 403 state without exposing any mutation control', async () => {
    vi.mocked(queryDomainPackActivationHistory).mockRejectedValue(
      new IntelligenceCatalogApiError(403, 'Pack activation history requires administer_lifecycle authority'),
    )

    render(<PackActivationReader />)
    fireEvent.change(screen.getByLabelText('Activation key'), { target: { value: 'world-ai' } })
    fireEvent.click(screen.getByRole('button', { name: 'Read activation' }))

    expect(await screen.findByText('Current permission does not authorize this read.')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /edit|activate|upgrade|rollback/i })).toBeNull()
  })

  it('renders a distinct 404 state for an unknown activation key', async () => {
    vi.mocked(queryDomainPackActivationHistory).mockRejectedValue(
      new IntelligenceCatalogApiError(404, 'no activation exists for the exact activation key'),
    )

    render(<PackActivationReader />)
    fireEvent.change(screen.getByLabelText('Activation key'), { target: { value: 'unknown-key' } })
    fireEvent.click(screen.getByRole('button', { name: 'Read activation' }))

    expect(await screen.findByText('No activation exists for this exact activation key.')).toBeTruthy()
  })

  it('renders a distinct conflict/unavailable state on 503', async () => {
    vi.mocked(queryDomainPackActivationHistory).mockRejectedValue(
      new IntelligenceCatalogApiError(503, 'exact Pack activation history is unavailable'),
    )

    render(<PackActivationReader />)
    fireEvent.change(screen.getByLabelText('Activation key'), { target: { value: 'world-ai' } })
    fireEvent.click(screen.getByRole('button', { name: 'Read activation' }))

    expect(await screen.findByText('Exact Pack activation history is unavailable right now.')).toBeTruthy()
  })

  it('renders a distinct 401 state after the API layer exhausts its own retry, and retries on demand', async () => {
    vi.mocked(queryDomainPackActivationHistory).mockRejectedValue(
      new IntelligenceCatalogApiError(401, 'verified token lacks exact product scope'),
    )

    render(<PackActivationReader />)
    fireEvent.change(screen.getByLabelText('Activation key'), { target: { value: 'world-ai' } })
    fireEvent.click(screen.getByRole('button', { name: 'Read activation' }))

    expect(await screen.findByText('ACE retried authentication and still could not read this activation.')).toBeTruthy()
    expect(queryDomainPackActivationHistory).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(queryDomainPackActivationHistory).toHaveBeenCalledTimes(2))
  })
})
