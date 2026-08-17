import { beforeEach, describe, expect, test, vi } from 'vitest'

import { clearToken, getToken } from './auth'
import {
  activateIntelligenceBuilderPlan,
  associateIntelligenceBuildSession,
  approveDomainActivationPlan,
  approveIntelligenceBuildPlan,
  bindIntelligenceBuildPlan,
  configuredIntelligenceBuildActivation,
  createDomainActivationPlanApproveInput,
  createDomainActivationPlanPrepareInput,
  createIntelligenceBuildPlanBindInput,
  createIntelligenceBuildPlanPrepareInput,
  createIntelligenceBuildResourceStateInput,
  createIntelligenceBuildStartInput,
  createIntelligenceBuilderPlanActivateInput,
  DOMAIN_HEALTH_RESOURCE_KINDS,
  prepareDomainActivationPlan,
  prepareIntelligenceBuild,
  projectIntelligenceBuild,
  projectIntelligenceBuildResourceState,
  retryIntelligenceBuildSession,
  startIntelligenceBuild,
  type BoundIntelligenceBuildPlan,
  type IntelligenceBuildPlan,
} from './intelligenceBuildsApi'

vi.mock('./auth', () => ({ clearToken: vi.fn(), getToken: vi.fn() }))

const result = {
  contract: 'ace.http.intelligence-build-result/v1alpha1',
  build_id: 'intelligence_build:test',
  request_digest: `sha256:${'a'.repeat(64)}`,
  product_id: 'product:test',
  actor_ref: 'principal:test',
  accepted_at: '2026-08-13T00:00:00Z',
  authority_use: {},
  resource_page: { items: [], state: 'complete' },
}

const selection = {
  contract: 'ace.application.recorded-source-selection-reference/v1alpha1' as const,
  source_group_id: 'official-records',
  selection_id: 'recorded_source_selection:official-records',
  selection_digest: `sha256:${'2'.repeat(64)}`,
}

const exactPlan = {
  contract: 'ace.application.intelligence-build-plan/v1alpha3',
  request: {
    contract: 'ace.application.intelligence-build-plan-request/v1alpha2',
    product_id: 'product:test',
    actor_ref: 'principal:test',
    client_request_id: 'atrium-request:exact',
    profile_id: 'profile:world-ai',
    profile_digest: `sha256:${'3'.repeat(64)}`,
    subject: 'Keep me ahead of meaningful AI changes.',
    outcome_id: 'outcome:decision-readiness',
    source_group_ids: ['official-records'],
    cadence_id: 'cadence:daily',
    proposed_effects: ['connect_sources', 'map_concepts', 'activate_watch', 'create_first_brief'],
    requested_at: '2026-08-13T00:00:00Z',
    request_id: 'intelligence_build_plan_request:test',
    request_digest: `sha256:${'4'.repeat(64)}`,
  },
  pack_reference: {
    pack_id: 'world-ai',
    pack_version: '1.0.0',
    compiled_pack_id: `pack_ir:${'5'.repeat(32)}`,
    pack_digest: `sha256:${'5'.repeat(64)}`,
  },
  activation_proposal: {
    contract: 'ace.application.intelligence-build-activation-proposal/v1alpha1',
    product_id: 'product:test',
    activation_key: 'world-ai',
    pack: {
      pack_id: 'world-ai',
      pack_version: '1.0.0',
      compiled_pack_id: `pack_ir:${'5'.repeat(32)}`,
      pack_digest: `sha256:${'5'.repeat(64)}`,
    },
    overlay: {},
    capability_requirement_ids: ['recorded-source-reader'],
    authority_request_ids: ['source-read'],
    proposal_id: 'intelligence_build_activation_proposal:test',
    proposal_digest: `sha256:${'6'.repeat(64)}`,
  },
  recorded_source_selection_refs: [selection],
  review_projection: {
    contract: 'ace.application.intelligence-build-review-projection/v1alpha1',
    request_id: 'intelligence_build_plan_request:test',
    request_digest: `sha256:${'4'.repeat(64)}`,
    profile_id: 'profile:world-ai',
    profile_digest: `sha256:${'3'.repeat(64)}`,
    subject: 'Keep me ahead of meaningful AI changes.',
    outcome_id: 'outcome:decision-readiness',
    outcome_label: 'Decision readiness',
    sources: [],
    concepts: [],
    watches: [],
    cadence_id: 'cadence:daily',
    cadence_label: 'Daily',
    cadence_description: 'Once a day.',
    effects: [],
    projection_id: 'intelligence_build_review:test',
    projection_digest: `sha256:${'7'.repeat(64)}`,
  },
  plan_id: 'intelligence_build_plan:test',
  plan_digest: `sha256:${'8'.repeat(64)}`,
} as const satisfies IntelligenceBuildPlan

const boundPlan = {
  contract: 'ace.application.bound-intelligence-build-plan/v1alpha1',
  binding_request: {
    contract: 'ace.application.intelligence-build-plan-bind-request/v1alpha1',
    plan: exactPlan,
    capability_bindings: [],
    authority_bindings: [],
    bound_at: '2026-08-13T00:01:00Z',
    request_id: 'intelligence_build_plan_bind_request:test',
    request_digest: `sha256:${'9'.repeat(64)}`,
  },
  activation_spec: { spec_id: 'activation_spec:reviewed' },
  execution_request_id: 'intelligence_build:test',
  execution_request_digest: `sha256:${'a'.repeat(64)}`,
  bound_plan_id: 'bound_intelligence_build_plan:test',
  bound_plan_digest: `sha256:${'b'.repeat(64)}`,
} as const satisfies BoundIntelligenceBuildPlan

describe('configuredIntelligenceBuildActivation', () => {
  test('keeps activation review-only without exact host bindings', () => {
    vi.stubEnv('VITE_INTELLIGENCE_CAPABILITY_BINDINGS_JSON', '')
    vi.stubEnv('VITE_INTELLIGENCE_AUTHORITY_BINDINGS_JSON', '')

    expect(configuredIntelligenceBuildActivation()).toEqual({
      state: 'unavailable',
      detail: 'This host has no exact capability and authority binding configuration. The plan remains review-only.',
    })
    vi.unstubAllEnvs()
  })

  test('passes only opaque configured bindings to later exact validation', () => {
    vi.stubEnv('VITE_INTELLIGENCE_CAPABILITY_BINDINGS_JSON', JSON.stringify([{
      requirement_id: 'recorded-source-reader',
      capability: 'source_snapshot',
      contract: 'ace.source.snapshot/v1alpha1',
      implementation_id: 'recorded_snapshot_adapter',
      implementation_version: '1.0.0',
      artifact_digest: `sha256:${'e'.repeat(64)}`,
      configuration_ref: null,
      secret_ref: null,
    }]))
    vi.stubEnv('VITE_INTELLIGENCE_AUTHORITY_BINDINGS_JSON', JSON.stringify([{
      request_id: 'source-read',
      authority: 'source_read',
      grant_ref: 'authority_grant:source-read',
    }]))

    expect(configuredIntelligenceBuildActivation()).toMatchObject({
      state: 'configured',
      inputs: {
        capability_bindings: [{ requirement_id: 'recorded-source-reader' }],
        authority_bindings: [{ request_id: 'source-read' }],
      },
    })
    vi.unstubAllEnvs()
  })

  test('fails closed on malformed host binding configuration', () => {
    vi.stubEnv('VITE_INTELLIGENCE_CAPABILITY_BINDINGS_JSON', '{broken')
    vi.stubEnv('VITE_INTELLIGENCE_AUTHORITY_BINDINGS_JSON', '[]')

    expect(configuredIntelligenceBuildActivation()).toEqual({
      state: 'unavailable',
      detail: 'Capability bindings are not valid JSON.',
    })
    vi.unstubAllEnvs()
  })
})

describe('approveIntelligenceBuildPlan', () => {
  beforeEach(() => {
    vi.mocked(getToken).mockReset()
    vi.mocked(getToken).mockResolvedValue('personal-token')
  })

  test('records an explicit owner decision over the exact bound plan', async () => {
    const approved = {
      contract: 'ace.http.intelligence-activation-approval-result/v1alpha1',
      approval: {
        receipt_ref: 'approval:intelligence-activation:exact',
        product_id: exactPlan.request.product_id,
        subject_ref: boundPlan.activation_spec.spec_id,
        actor_ref: exactPlan.request.actor_ref,
        receipt_hash: 'f'.repeat(64),
        approved_at: '2026-08-13T00:02:00Z',
      },
      bound_plan_id: boundPlan.bound_plan_id,
      bound_plan_digest: boundPlan.bound_plan_digest,
      start_request: createIntelligenceBuildStartInput(boundPlan, 'approval:intelligence-activation:exact'),
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(approved), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))

    await expect(approveIntelligenceBuildPlan(boundPlan)).resolves.toMatchObject({
      approval: { receipt_ref: 'approval:intelligence-activation:exact' },
      start_request: { activation_approval_subject_ref: 'activation_spec:reviewed' },
    })
    const [path, options] = vi.mocked(fetch).mock.calls[0] ?? []
    expect(path).toBe('/v1/intelligence/builds/approve')
    expect(JSON.parse(String(options?.body))).toMatchObject({
      decision: 'approve',
      bound_plan: boundPlan,
    })
  })
})

describe('associateIntelligenceBuildSession', () => {
  beforeEach(() => {
    vi.mocked(getToken).mockReset()
    vi.mocked(getToken).mockResolvedValue('personal-token')
  })

  test('sends only the exact bound plan and recorded approval receipt', async () => {
    const association = {
      contract: 'ace.http.intelligence-build-session-association-result/v1alpha1',
      bound_plan_id: boundPlan.bound_plan_id,
      bound_plan_digest: boundPlan.bound_plan_digest,
      approval: {
        receipt_ref: 'approval:intelligence-activation:exact',
        product_id: exactPlan.request.product_id,
        subject_ref: boundPlan.activation_spec.spec_id,
        actor_ref: exactPlan.request.actor_ref,
        receipt_hash: 'f'.repeat(64),
        approved_at: '2026-08-13T00:02:00Z',
      },
      session: {
        contract: 'ace.application.intelligence-builder-session-revision/v1alpha1',
        stage: 'goal_selected',
        sequence: 1,
      },
      replayed: false,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(association), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))

    await expect(associateIntelligenceBuildSession(
      boundPlan,
      'approval:intelligence-activation:exact',
    )).resolves.toMatchObject({ session: { stage: 'goal_selected', sequence: 1 } })
    const [path, options] = vi.mocked(fetch).mock.calls[0] ?? []
    expect(path).toBe('/v1/intelligence/builds/session/associate')
    expect(JSON.parse(String(options?.body))).toEqual({
      bound_plan: boundPlan,
      approval_receipt_ref: 'approval:intelligence-activation:exact',
    })
  })
})

const exactBriefingReadySession = {
  contract: 'ace.application.intelligence-builder-session-revision/v1alpha1',
  product_id: exactPlan.request.product_id,
  session_id: 'intelligence_builder_session:test',
  correlation_id: 'correlation:test',
  goal_ref: 'goal:test',
  sequence: 7,
  stage: 'first_briefing_ready',
  prior_revision_id: 'intelligence_builder_session_revision:prior',
  prior_revision_digest: `sha256:${'e'.repeat(64)}`,
  transition_authority: 'core_runtime',
  transition_actor_ref: exactPlan.request.actor_ref,
  approval_receipt_ref: null,
  artifacts: [],
  block_reason: null,
  resume_stage: null,
  safe_diagnostic: null,
  occurred_at: '2026-08-13T00:02:45Z',
  revision_id: 'intelligence_builder_session_revision:briefing-ready',
  revision_digest: `sha256:${'f'.repeat(64)}`,
} as const

describe('activation-plan coordination', () => {
  beforeEach(() => {
    vi.mocked(getToken).mockReset()
    vi.mocked(getToken).mockResolvedValue('personal-token')
  })

  test('prepareDomainActivationPlan posts the exact current session and bound plan to the preview boundary', async () => {
    const preview = {
      contract: 'ace.application.intelligence-activation-plan/v1alpha2',
      action: 'initial_activation',
      onboarding_handoff: { contract: 'ace.application.activation-onboarding-handoff/v1alpha2', session_id: exactBriefingReadySession.session_id },
      spec: { spec_id: boundPlan.activation_spec.spec_id, activation_key: 'world-ai' },
      requested_effects: ['pack_activation'],
      requested_capabilities: [],
      requested_authorities: [],
      created_at: '2026-08-13T00:02:00Z',
      plan_id: 'intelligence_activation_plan:test',
      plan_digest: `sha256:${'1'.repeat(64)}`,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(preview), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))
    const input = createDomainActivationPlanPrepareInput(exactBriefingReadySession, boundPlan, '2026-08-13T00:02:00Z')

    await expect(prepareDomainActivationPlan(input)).resolves.toMatchObject({ plan_id: 'intelligence_activation_plan:test' })
    const [path, options] = vi.mocked(fetch).mock.calls[0] ?? []
    expect(path).toBe('/v1/intelligence/builds/activation-plan/prepare')
    expect(JSON.parse(String(options?.body))).toEqual({
      current: exactBriefingReadySession,
      bound_plan: boundPlan,
      requested_at: '2026-08-13T00:02:00Z',
    })
  })

  test('approveDomainActivationPlan reuses the exact caller-supplied approved_at and posts the distinct plan decision', async () => {
    const commitReference = {
      contract: 'ace.application.domain-activation-commit-reference/v1alpha2',
      authority_stage: 'historical_reference',
      live_authority: false,
      product_id: exactPlan.request.product_id,
      activation_key: 'world-ai',
      activation_id: 'domain_activation:test',
      state: 'active',
      plan_id: 'intelligence_activation_plan:test',
      plan_digest: `sha256:${'1'.repeat(64)}`,
      revision: 1,
      revision_id: 'activation_revision:test',
      revision_digest: `sha256:${'2'.repeat(64)}`,
      commit_receipt_id: 'commit_receipt:test',
      commit_receipt_digest: `sha256:${'3'.repeat(64)}`,
      committed_at: '2026-08-13T00:02:00Z',
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(commitReference), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))
    const input = createDomainActivationPlanApproveInput(exactBriefingReadySession, boundPlan, '2026-08-13T00:02:00Z')

    await expect(approveDomainActivationPlan(input)).resolves.toMatchObject({ state: 'active', live_authority: false })
    const [path, options] = vi.mocked(fetch).mock.calls[0] ?? []
    expect(path).toBe('/v1/intelligence/builds/activation-plan/approve')
    expect(JSON.parse(String(options?.body))).toEqual({
      decision: 'approve',
      current: exactBriefingReadySession,
      bound_plan: boundPlan,
      approved_at: '2026-08-13T00:02:00Z',
    })
  })

  test('activateIntelligenceBuilderPlan posts the exact spec approval receipt ref and stable timestamp', async () => {
    const activationResult = {
      contract: 'ace.http.intelligence-builder-activation-result/v1alpha1',
      receipt: {
        session_id: exactBriefingReadySession.session_id,
        activated_at: '2026-08-13T00:02:00Z',
      },
      replayed: false,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(activationResult), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))
    const input = createIntelligenceBuilderPlanActivateInput(boundPlan, 'approval:intelligence-activation:exact', '2026-08-13T00:02:00Z')

    await expect(activateIntelligenceBuilderPlan(input)).resolves.toMatchObject({ replayed: false })
    const [path, options] = vi.mocked(fetch).mock.calls[0] ?? []
    expect(path).toBe('/v1/intelligence/builds/activation-plan/activate')
    expect(JSON.parse(String(options?.body))).toEqual({
      bound_plan: boundPlan,
      activation_approval_receipt_ref: 'approval:intelligence-activation:exact',
      requested_at: '2026-08-13T00:02:00Z',
    })
  })

  test('clears the stale token and retries exactly once on 401 before returning the activation-plan preview', async () => {
    const preview = {
      contract: 'ace.application.intelligence-activation-plan/v1alpha2',
      action: 'initial_activation',
      plan_id: 'intelligence_activation_plan:test',
    }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(preview), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    vi.stubGlobal('fetch', fetchMock)
    const input = createDomainActivationPlanPrepareInput(exactBriefingReadySession, boundPlan, '2026-08-13T00:02:00Z')

    await expect(prepareDomainActivationPlan(input)).resolves.toMatchObject({ plan_id: 'intelligence_activation_plan:test' })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(vi.mocked(clearToken)).toHaveBeenCalledTimes(1)
  })

  test('preserves a precise 404 dependency-not-ready status without retrying', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'activation plan requires the exact current briefing-ready session' }),
      { status: 404, headers: { 'Content-Type': 'application/json' } },
    )))
    const input = createIntelligenceBuilderPlanActivateInput(boundPlan, 'approval:intelligence-activation:exact', '2026-08-13T00:02:00Z')

    await expect(activateIntelligenceBuilderPlan(input)).rejects.toMatchObject({
      status: 404,
      message: 'activation plan requires the exact current briefing-ready session',
    })
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1)
  })
})

describe('retryIntelligenceBuildSession', () => {
  beforeEach(() => {
    vi.mocked(getToken).mockReset()
    vi.mocked(getToken).mockResolvedValue('personal-token')
  })

  test('submits the exact blocked revision without inventing a second resume path', async () => {
    const blocked = {
      contract: 'ace.application.intelligence-builder-session-revision/v1alpha1',
      product_id: 'product:test',
      session_id: 'intelligence_builder_session:test',
      sequence: 4,
      stage: 'blocked',
      revision_id: 'intelligence_builder_session_revision:blocked',
      revision_digest: `sha256:${'d'.repeat(64)}`,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...blocked,
      sequence: 5,
      stage: 'retrying',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    await expect(retryIntelligenceBuildSession(blocked)).resolves.toMatchObject({ stage: 'retrying' })
    const [path, options] = vi.mocked(fetch).mock.calls[0] ?? []
    expect(path).toBe('/v1/intelligence/builds/retry')
    expect(JSON.parse(String(options?.body))).toMatchObject({ current: blocked })
  })
})

describe('projectIntelligenceBuild', () => {
  beforeEach(() => {
    vi.mocked(getToken).mockReset()
    vi.mocked(getToken).mockResolvedValue('personal-token')
  })

  test('posts the prepared plan unchanged to the read-only canonical projection boundary', async () => {
    const projection = {
      contract: 'ace.intelligence.system-projection/v1alpha1',
      product_id: 'product:test',
      mode: 'proposed',
      blueprint: { elements: [], gaps: [], subject: exactPlan.request.subject },
      changes: [],
      source_bindings: [],
      coverage: [],
      initialization: [],
      domain_health: [],
      gaps: [],
      generated_at: '2026-08-13T00:00:00Z',
      projection_id: 'intelligence_system_projection:test',
      projection_digest: `sha256:${'c'.repeat(64)}`,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(projection), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))

    await expect(projectIntelligenceBuild(exactPlan)).resolves.toMatchObject({
      contract: 'ace.intelligence.system-projection/v1alpha1',
      mode: 'proposed',
    })
    const [path, options] = vi.mocked(fetch).mock.calls[0] ?? []
    expect(path).toBe('/v1/intelligence/builds/projection')
    expect(JSON.parse(String(options?.body))).toEqual({ plan: exactPlan })
    expect(options?.headers).toEqual(expect.objectContaining({ Authorization: 'Bearer personal-token' }))
  })
})

describe('startIntelligenceBuild', () => {
  beforeEach(() => {
    vi.mocked(getToken).mockReset()
    vi.mocked(getToken).mockResolvedValue('personal-token')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(result), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))
  })

  test('submits the reviewed Atrium plan to the governed build boundary', async () => {
    const input = createIntelligenceBuildStartInput(boundPlan, 'approval:reviewed-activation')
    const response = await startIntelligenceBuild(input)

    expect(response.build_id).toBe('intelligence_build:test')
    const [path, options] = vi.mocked(fetch).mock.calls[0] ?? []
    expect(path).toBe('/v1/intelligence/builds/start')
    expect(options?.method).toBe('POST')
    expect(options?.headers).toEqual(expect.objectContaining({ Authorization: 'Bearer personal-token' }))
    const body = JSON.parse(String(options?.body)) as Record<string, unknown>
    expect(body).toEqual(expect.objectContaining({
      profile_id: 'profile:world-ai',
      subject: 'Keep me ahead of meaningful AI changes.',
      outcome_id: 'outcome:decision-readiness',
      source_group_ids: ['official-records'],
      cadence_id: 'cadence:daily',
      activation_approval_receipt_ref: 'approval:reviewed-activation',
      activation_approval_subject_ref: 'activation_spec:reviewed',
      recorded_source_selection_refs: [selection],
      resource_authority_grant_ref: 'authority_grant:atrium-observe-read',
      approved_effects: [
        'connect_sources',
        'map_concepts',
        'activate_watch',
        'create_first_brief',
      ],
    }))
    expect(body.client_request_id).toBe('atrium-request:exact')
    expect(body.requested_at).toBe('2026-08-13T00:00:00Z')
  })

  test('preserves the no-authority response without retrying or weakening the request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'Intelligence build denied' }),
      { status: 403, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(startIntelligenceBuild(
      createIntelligenceBuildStartInput(boundPlan, 'approval:reviewed-activation'),
    )).rejects.toMatchObject({
      status: 403,
      message: 'Intelligence build denied',
    })
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1)
  })
})

describe('projectIntelligenceBuildResourceState', () => {
  const resourcePage = {
    contract: 'ace.http.intelligence-resource-page/v1alpha1',
    query_id: 'intelligence_resource_query:test',
    query_digest: `sha256:${'f'.repeat(64)}`,
    product_id: 'product:test',
    actor_ref: 'principal:test',
    as_of: '2026-08-13T00:02:30Z',
    available_at: '2026-08-13T00:02:31Z',
    evaluated_at: '2026-08-13T00:02:31Z',
    state: 'complete' as const,
    items: [],
    next_cursor: null,
    degraded_reason_refs: [],
    page_id: 'intelligence_resource_page:test',
    page_digest: `sha256:${'0'.repeat(64)}`,
  }

  const liveProjection = {
    contract: 'ace.intelligence.system-projection/v1alpha1',
    product_id: 'product:test',
    mode: 'live',
    blueprint: {
      elements: [],
      gaps: [],
      subject: exactPlan.request.subject,
      blueprint_id: 'generated_blueprint:live',
      blueprint_digest: `sha256:${'1'.repeat(64)}`,
    },
    changes: [],
    source_bindings: [],
    coverage: [],
    initialization: [],
    domain_health: [],
    gaps: [],
    generated_at: '2026-08-13T00:02:32Z',
    projection_id: 'intelligence_system_projection:live',
    projection_digest: `sha256:${'2'.repeat(64)}`,
  }

  beforeEach(() => {
    vi.mocked(getToken).mockReset()
    vi.mocked(clearToken).mockReset()
    vi.mocked(getToken).mockResolvedValueOnce('first-token').mockResolvedValue('refreshed-token')
  })

  test('posts the exact bound plan, receipt, grant, and server page timestamps to the live resource-state boundary', async () => {
    const input = createIntelligenceBuildResourceStateInput(
      boundPlan,
      'approval:intelligence-activation:exact',
      'authority_grant:atrium-observe-read',
      resourcePage,
    )
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(liveProjection), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))

    await expect(projectIntelligenceBuildResourceState(input)).resolves.toMatchObject({ mode: 'live' })
    const [path, options] = vi.mocked(fetch).mock.calls[0] ?? []
    expect(path).toBe('/v1/intelligence/builds/projection/resource-state')
    expect(options?.method).toBe('POST')
    expect(JSON.parse(String(options?.body))).toEqual({
      bound_plan: boundPlan,
      activation_approval_receipt_ref: 'approval:intelligence-activation:exact',
      selector: {
        authority_grant_ref: 'authority_grant:atrium-observe-read',
        resource_kinds: DOMAIN_HEALTH_RESOURCE_KINDS,
        subject_refs: [],
        as_of: resourcePage.as_of,
        available_at: resourcePage.available_at,
        page_size: 200,
        cursor: null,
      },
    })
    expect(options?.headers).toEqual(expect.objectContaining({ Authorization: 'Bearer first-token' }))
  })

  test('clears the stale token and retries exactly once on 401 before returning the live projection', async () => {
    const input = createIntelligenceBuildResourceStateInput(
      boundPlan,
      'approval:intelligence-activation:exact',
      'authority_grant:atrium-observe-read',
      resourcePage,
    )
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(liveProjection), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(projectIntelligenceBuildResourceState(input)).resolves.toMatchObject({ mode: 'live' })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(vi.mocked(clearToken)).toHaveBeenCalledTimes(1)
    expect(vi.mocked(getToken)).toHaveBeenCalledTimes(2)
    const secondOptions = fetchMock.mock.calls[1]?.[1]
    expect(secondOptions?.headers).toEqual(expect.objectContaining({ Authorization: 'Bearer refreshed-token' }))
  })

  test('preserves the exact degraded status without a second retry on non-auth failures', async () => {
    const input = createIntelligenceBuildResourceStateInput(
      boundPlan,
      'approval:intelligence-activation:exact',
      'authority_grant:atrium-observe-read',
      resourcePage,
    )
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'The bound plan is not durably approved.' }),
      { status: 409, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(projectIntelligenceBuildResourceState(input)).rejects.toMatchObject({
      status: 409,
      message: 'The bound plan is not durably approved.',
    })
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1)
  })
})

describe('bindIntelligenceBuildPlan', () => {
  beforeEach(() => {
    vi.mocked(getToken).mockReset()
    vi.mocked(getToken).mockResolvedValue('personal-token')
  })

  test('binds only caller-supplied exact capability and authority material', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(boundPlan), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))
    const input = createIntelligenceBuildPlanBindInput(exactPlan, {
      capability_bindings: [],
      authority_bindings: [],
    })

    await expect(bindIntelligenceBuildPlan(input)).resolves.toMatchObject({
      bound_plan_id: 'bound_intelligence_build_plan:test',
      activation_spec: { spec_id: 'activation_spec:reviewed' },
    })
    const [path, options] = vi.mocked(fetch).mock.calls[0] ?? []
    expect(path).toBe('/v1/intelligence/builds/bind')
    expect(JSON.parse(String(options?.body))).toEqual(input)
  })

  test('refuses to bind the legacy activation-bearing plan shape', () => {
    expect(() => createIntelligenceBuildPlanBindInput(
      { ...exactPlan, contract: 'ace.application.intelligence-build-plan/v1alpha2', activation_proposal: undefined },
      { capability_bindings: [], authority_bindings: [] },
    )).toThrow('Only an exact v1alpha3 activation proposal can be bound.')
  })
})

describe('prepareIntelligenceBuild', () => {
  const selection = {
    profile_id: 'onboarding_profile:world-ai',
    profile_digest: `sha256:${'b'.repeat(64)}`,
    subject: 'Keep me ahead of material AI changes.',
    outcome_id: 'decision-readiness',
    source_group_ids: ['official-records'],
    cadence_id: 'daily',
  }

  beforeEach(() => {
    vi.mocked(getToken).mockReset()
    vi.mocked(getToken).mockResolvedValue('personal-token')
  })

  test('posts the exact reusable prepare input and returns server review material', async () => {
    const input = createIntelligenceBuildPlanPrepareInput(selection)
    const plan = {
      contract: 'ace.application.intelligence-build-plan/v1alpha2',
      request: {
        ...input,
        contract: 'ace.application.intelligence-build-plan-request/v1alpha2',
        product_id: 'product:local',
        actor_ref: 'principal:local-owner',
        request_id: 'intelligence_build_plan_request:test',
        request_digest: `sha256:${'c'.repeat(64)}`,
      },
      recorded_source_selection_refs: [],
      review_projection: {
        contract: 'ace.application.intelligence-build-review-projection/v1alpha1',
        request_id: 'intelligence_build_plan_request:test',
        request_digest: `sha256:${'c'.repeat(64)}`,
        profile_id: selection.profile_id,
        profile_digest: selection.profile_digest,
        subject: selection.subject,
        outcome_id: selection.outcome_id,
        outcome_label: 'Decision readiness',
        sources: [],
        concepts: [],
        watches: [],
        cadence_id: selection.cadence_id,
        cadence_label: 'Daily',
        cadence_description: 'Once a day.',
        effects: [],
        projection_id: 'intelligence_build_review:test',
        projection_digest: `sha256:${'d'.repeat(64)}`,
      },
      plan_id: 'intelligence_build_plan:test',
      plan_digest: `sha256:${'e'.repeat(64)}`,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(plan), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))

    await expect(prepareIntelligenceBuild(input)).resolves.toMatchObject({
      plan_id: 'intelligence_build_plan:test',
      review_projection: { projection_id: 'intelligence_build_review:test' },
    })
    const [path, options] = vi.mocked(fetch).mock.calls[0] ?? []
    expect(path).toBe('/v1/intelligence/builds/prepare')
    expect(JSON.parse(String(options?.body))).toEqual(input)
    expect(options?.headers).toEqual(expect.objectContaining({ Authorization: 'Bearer personal-token' }))
  })

  test.each([404, 409, 503])('preserves the exact degraded status %s', async (status) => {
    const input = createIntelligenceBuildPlanPrepareInput(selection)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: `bounded failure ${status}` }),
      { status, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(prepareIntelligenceBuild(input)).rejects.toMatchObject({
      status,
      message: `bounded failure ${status}`,
    })
  })

  test('rejects a successful response that has no exact review projection', async () => {
    const input = createIntelligenceBuildPlanPrepareInput(selection)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      contract: 'ace.application.intelligence-build-plan/v1alpha2',
      review_projection: null,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    await expect(prepareIntelligenceBuild(input)).rejects.toMatchObject({ status: 409 })
  })
})
