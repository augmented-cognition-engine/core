import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import {
  DOMAIN_HEALTH_RESOURCE_KINDS,
  IntelligenceBuildApiError,
  type BoundIntelligenceBuildPlan,
  type IntelligenceBuildApprovalResult,
  type IntelligenceBuildPlan,
  type IntelligenceBuildResult,
  type IntelligenceSystemProjection,
} from '@/api/intelligenceBuildsApi'
import { OnboardingPreview } from './OnboardingPreview'
import type { IntelligenceOnboardingProfile } from './onboardingModel'
import { onboardingProfilesFromResources } from './onboardingModel'

const profile: IntelligenceOnboardingProfile = {
  contract: 'ace.intelligence.onboarding-profile/v1alpha1',
  profile_id: 'onboarding_profile:world',
  profile_digest: `sha256:${'1'.repeat(64)}`,
  topic_id: 'artificial-intelligence',
  display_name: 'AI Command Center',
  domain_label: 'World Intelligence',
  topic_label: 'Artificial intelligence',
  prompt: 'What do you need to stay ahead of?',
  description: 'Build a cited picture of meaningful AI change.',
  starter_prompts: ['Keep me ahead of meaningful AI changes.'],
  outcomes: [{
    outcome_id: 'track-ai',
    label: 'Track AI change',
    description: 'Follow material capability, policy, and adoption shifts.',
    icon_hint: 'research',
    recommended_topic_labels: ['Capability', 'Policy'],
    recommended_intelligence_labels: ['AI shifts'],
  }],
  source_groups: [{
    source_group_id: 'official-records',
    label: 'Official records',
    description: 'Primary official evidence.',
    evidence_role: 'authoritative_record',
    source_ids: ['federal-register'],
    source_labels: ['Federal Register'],
    access_label: 'Recorded public evidence',
    default_selected: true,
  }],
  cadences: [{ cadence_id: 'daily', label: 'Daily', description: 'Orient me daily.' }],
  default_cadence_id: 'daily',
  completion_label: 'Open the first Brief',
}

const selection = {
  contract: 'ace.application.recorded-source-selection-reference/v1alpha1' as const,
  source_group_id: 'official-records',
  selection_id: 'recorded_source_selection:official-policy',
  selection_digest: `sha256:${'2'.repeat(64)}`,
}

const preparedPlan: IntelligenceBuildPlan = {
  contract: 'ace.application.intelligence-build-plan/v1alpha2',
  request: {
    contract: 'ace.application.intelligence-build-plan-request/v1alpha2',
    product_id: 'product:world-ai',
    actor_ref: 'principal:owner',
    client_request_id: 'atrium-request:exact',
    profile_id: profile.profile_id,
    profile_digest: profile.profile_digest ?? '',
    subject: profile.starter_prompts[0],
    outcome_id: profile.outcomes[0].outcome_id,
    source_group_ids: [profile.source_groups[0].source_group_id],
    cadence_id: profile.default_cadence_id,
    proposed_effects: ['connect_sources', 'map_concepts', 'activate_watch', 'create_first_brief'],
    requested_at: '2026-08-13T00:00:00Z',
    request_id: 'intelligence_build_plan_request:exact',
    request_digest: `sha256:${'3'.repeat(64)}`,
  },
  recorded_source_selection_refs: [selection],
  review_projection: {
    contract: 'ace.application.intelligence-build-review-projection/v1alpha1',
    request_id: 'intelligence_build_plan_request:exact',
    request_digest: `sha256:${'3'.repeat(64)}`,
    profile_id: profile.profile_id,
    profile_digest: profile.profile_digest ?? '',
    subject: profile.starter_prompts[0],
    outcome_id: profile.outcomes[0].outcome_id,
    outcome_label: profile.outcomes[0].label,
    sources: [{
      selection,
      label: 'Official records',
      evidence_role: 'authoritative_record',
      source_uri: 'https://example.test/official-policy',
      source_definition_ref: 'source_definition:official-policy',
      entity_type_id: 'policy_record',
      entity_ref: 'entity:artificial-intelligence',
      observed_at: '2026-08-13T00:00:00Z',
    }],
    concepts: [{
      entity_type_id: 'policy_record',
      entity_ref: 'entity:artificial-intelligence',
      display_name: 'Policy record',
      source_selections: [selection],
    }],
    watches: [{
      detector_id: 'policy_progression',
      detector_family: 'categorical_transition',
      entity_type_id: 'policy_record',
      entity_refs: ['entity:artificial-intelligence'],
      attribute_id: 'implementation_state',
      change_rule: 'Declared transitions: directive → implementation',
      shift_type: 'policy_progression',
      signal_type: 'policy_attention',
      cadence_id: 'daily',
      cadence_label: 'Daily',
    }],
    cadence_id: 'daily',
    cadence_label: 'Daily',
    cadence_description: 'Orient me daily.',
    effects: [
      ['connect_sources', 'Review exact evidence'],
      ['map_concepts', 'Map the starting concepts'],
      ['activate_watch', 'Configure the starting watches'],
      ['create_first_brief', 'Assemble the first cited Brief'],
    ].map(([effect, label]) => ({
      effect: effect as 'connect_sources' | 'map_concepts' | 'activate_watch' | 'create_first_brief',
      label,
      what: `What ${label.toLowerCase()} would do.`,
      why: 'Keep the operator decision-ready.',
      how: 'Use only the exact reviewed material.',
      when: 'Only after deliberate activation.',
      unknowns: ['No runtime result exists yet.'],
    })),
    projection_id: 'intelligence_build_review:exact',
    projection_digest: `sha256:${'4'.repeat(64)}`,
  },
  plan_id: 'intelligence_build_plan:exact',
  plan_digest: `sha256:${'5'.repeat(64)}`,
}

const systemProjection = {
  contract: 'ace.intelligence.system-projection/v1alpha1',
  product_id: 'product:world-ai',
  mode: 'proposed',
  blueprint: {
    subject: profile.starter_prompts[0],
    elements: [{
      kind: 'entity',
      element_id: 'policy-record',
      element_ref: 'blueprint_element:entity:policy-record',
      label: 'Policy record',
      rationale: 'Ground the requested domain in the installed Pack vocabulary.',
      confidence: { support: 'unsupported', value: null, reason: 'Blueprint confidence is not contracted.' },
    }],
    gaps: [],
    blueprint_id: 'generated_blueprint:test',
    blueprint_digest: `sha256:${'6'.repeat(64)}`,
  },
  changes: [{
    operation: 'add',
    target_ref: 'blueprint_element:entity:policy-record',
    rationale: 'Add the exact proposed entity.',
    expected_effect: { support: 'unsupported', value: null, reason: 'No prior accepted blueprint exists.' },
    requires_review: true,
    change_id: 'projection_change:test',
    change_digest: `sha256:${'7'.repeat(64)}`,
  }],
  source_bindings: [{
    binding_id: 'source_binding:test',
    source_group_id: 'official-records',
    label: 'Official records',
    evidence_role: 'authoritative_record',
    source_type_ref: 'source_type:public-record',
    source_uri: 'https://example.test/official-policy',
    access_requirement_label: 'Recorded public evidence',
    binding_state: 'proposed',
    permission_state: 'not_evaluated',
    readiness_state: 'not_evaluated',
    requirements: { support: 'unsupported', reason: 'Per-binding requirements are not contracted.' },
  }],
  coverage: [{
    dimension: 'entity',
    target_ref: 'blueprint_element:entity:policy-record',
    target_label: 'Policy record',
    source_binding_ids: ['source_binding:test'],
    predicted: { support: 'unsupported', value: null, reason: 'No estimator is bound.' },
    observed: { support: 'unsupported', value: null, reason: 'No evidence is admitted.' },
  }],
  initialization: [
    'blueprint_generated', 'review', 'permissions_validated', 'source_readiness_validated',
    'evidence_admitted', 'model_initialized', 'first_intelligence_validated', 'maintenance_activated',
  ].map((stage, index) => ({
    sequence: index + 1,
    stage,
    state: index === 0 ? 'complete' : index === 1 ? 'in_progress' : 'pending',
    detail: index === 0 ? 'Generated from exact installed material.' : 'Awaiting the preceding governed stage.',
  })),
  domain_health: [
    'coverage', 'freshness', 'confidence', 'conflicts', 'resolution', 'source_health', 'maintenance_health', 'historical_depth',
  ].map((dimension) => ({
    dimension,
    value: { support: 'unsupported', value: null, reason: `${dimension} is unavailable at proposal time.` },
  })),
  gaps: [],
  generated_at: '2026-08-13T00:00:00Z',
  projection_id: 'intelligence_system_projection:test',
  projection_digest: `sha256:${'8'.repeat(64)}`,
} as IntelligenceSystemProjection

const liveResourceStateProjection = {
  ...systemProjection,
  mode: 'live',
  source_bindings: systemProjection.source_bindings.map((binding) => ({
    ...binding,
    binding_state: 'ready' as const,
    permission_state: 'ready' as const,
    readiness_state: 'ready' as const,
  })),
  initialization: systemProjection.initialization.map((stage) => ({
    ...stage,
    state: 'complete' as const,
    detail: `Recorded ${stage.stage.replace(/_/g, ' ')}.`,
  })),
  gaps: [],
  generated_at: '2026-08-13T00:02:32Z',
  projection_id: 'intelligence_system_projection:live',
  projection_digest: `sha256:${'9'.repeat(64)}`,
} as IntelligenceSystemProjection

const proposedResourceStateProjectionWithGaps = {
  ...systemProjection,
  mode: 'proposed',
  gaps: ['The bound plan is not yet durably active; resource-state reads remain proposal-only.'],
  generated_at: '2026-08-13T00:02:32Z',
  projection_id: 'intelligence_system_projection:proposed-resource-state',
  projection_digest: `sha256:${'0'.repeat(64)}`,
} as IntelligenceSystemProjection

const activatablePlan = {
  ...preparedPlan,
  contract: 'ace.application.intelligence-build-plan/v1alpha3',
  pack_reference: {
    pack_id: 'world-ai',
    pack_version: '1.0.0',
    compiled_pack_id: `pack_ir:${'9'.repeat(32)}`,
    pack_digest: `sha256:${'9'.repeat(64)}`,
  },
  activation_proposal: {
    contract: 'ace.application.intelligence-build-activation-proposal/v1alpha1',
    product_id: preparedPlan.request.product_id,
    activation_key: 'world-ai',
    pack: {
      pack_id: 'world-ai',
      pack_version: '1.0.0',
      compiled_pack_id: `pack_ir:${'9'.repeat(32)}`,
      pack_digest: `sha256:${'9'.repeat(64)}`,
    },
    overlay: {},
    capability_requirement_ids: ['recorded-source-reader'],
    authority_request_ids: ['source-read'],
    proposal_id: 'intelligence_build_activation_proposal:test',
    proposal_digest: `sha256:${'a'.repeat(64)}`,
  },
} as IntelligenceBuildPlan

const boundPlan = {
  contract: 'ace.application.bound-intelligence-build-plan/v1alpha1',
  binding_request: {
    contract: 'ace.application.intelligence-build-plan-bind-request/v1alpha1',
    plan: activatablePlan,
    capability_bindings: [],
    authority_bindings: [],
    bound_at: '2026-08-13T00:01:00Z',
    request_id: 'intelligence_build_plan_bind_request:test',
    request_digest: `sha256:${'b'.repeat(64)}`,
  },
  activation_spec: { spec_id: 'activation_spec:reviewed' },
  execution_request_id: 'intelligence_build:test',
  execution_request_digest: `sha256:${'c'.repeat(64)}`,
  bound_plan_id: 'bound_intelligence_build_plan:test',
  bound_plan_digest: `sha256:${'d'.repeat(64)}`,
} as BoundIntelligenceBuildPlan

const buildResult = {
  contract: 'ace.http.intelligence-build-result/v1alpha1',
  build_id: 'intelligence_build:test',
  request_digest: `sha256:${'c'.repeat(64)}`,
  product_id: preparedPlan.request.product_id,
  actor_ref: preparedPlan.request.actor_ref,
  accepted_at: '2026-08-13T00:02:00Z',
  resource_page: {
    state: 'complete',
    items: [],
    as_of: '2026-08-13T00:02:30Z',
    available_at: '2026-08-13T00:02:31Z',
  },
} as unknown as IntelligenceBuildResult

const approvedStartRequest = {
  authority_grant_ref: 'authority_grant:atrium-intelligence-build',
  resource_authority_grant_ref: 'authority_grant:atrium-observe-read',
  activation_approval_receipt_ref: 'approval:intelligence-activation:reviewed',
  activation_approval_subject_ref: 'activation_spec:reviewed',
  client_request_id: activatablePlan.request.client_request_id,
  profile_id: activatablePlan.request.profile_id,
  subject: activatablePlan.request.subject,
  outcome_id: activatablePlan.request.outcome_id,
  source_group_ids: activatablePlan.request.source_group_ids,
  recorded_source_selection_refs: activatablePlan.recorded_source_selection_refs,
  cadence_id: activatablePlan.request.cadence_id,
  approved_effects: activatablePlan.request.proposed_effects,
  requested_at: activatablePlan.request.requested_at,
}

const exactBriefingReady = {
  contract: 'ace.application.intelligence-builder-session-revision/v1alpha1',
  product_id: activatablePlan.request.product_id,
  session_id: 'intelligence_builder_session:world',
  correlation_id: 'correlation:world',
  goal_ref: 'goal:world',
  sequence: 7,
  stage: 'first_briefing_ready',
  prior_revision_id: 'intelligence_builder_session_revision:prior',
  prior_revision_digest: `sha256:${'6'.repeat(64)}`,
  transition_authority: 'core_runtime',
  transition_actor_ref: activatablePlan.request.actor_ref,
  approval_receipt_ref: null,
  artifacts: [],
  block_reason: null,
  resume_stage: null,
  safe_diagnostic: null,
  occurred_at: '2026-08-13T00:02:45Z',
  revision_id: 'intelligence_builder_session_revision:briefing-ready',
  revision_digest: `sha256:${'7'.repeat(64)}`,
} as const

const briefingReadySession = {
  session_id: exactBriefingReady.session_id,
  goal_ref: exactBriefingReady.goal_ref,
  sequence: exactBriefingReady.sequence,
  stage: exactBriefingReady.stage,
  artifacts: [],
  block_reason: null,
  resume_stage: null,
  safe_diagnostic: null,
  exact_revision: exactBriefingReady,
} as const

const exactGoalSelected = {
  ...exactBriefingReady,
  sequence: 1,
  stage: 'goal_selected',
  prior_revision_id: null,
  prior_revision_digest: null,
  occurred_at: '2026-08-13T00:02:00Z',
  revision_id: 'intelligence_builder_session_revision:goal-selected',
  revision_digest: `sha256:${'8'.repeat(64)}`,
} as const

const sourcesConnectingSession = {
  session_id: 'intelligence_builder_session:world',
  goal_ref: 'goal:world',
  sequence: 2,
  stage: 'sources_connecting',
  artifacts: [],
  block_reason: null,
  resume_stage: null,
  safe_diagnostic: null,
} as const

const approvalResult = {
  contract: 'ace.http.intelligence-activation-approval-result/v1alpha1',
  approval: {
    receipt_ref: approvedStartRequest.activation_approval_receipt_ref,
    product_id: activatablePlan.request.product_id,
    subject_ref: 'activation_spec:reviewed',
    actor_ref: activatablePlan.request.actor_ref,
    receipt_hash: 'f'.repeat(64),
    approved_at: '2026-08-13T00:02:00Z',
  },
  bound_plan_id: boundPlan.bound_plan_id,
  bound_plan_digest: boundPlan.bound_plan_digest,
  start_request: approvedStartRequest,
} as IntelligenceBuildApprovalResult

describe('Atrium Intelligence Builder onboarding', () => {
  it('starts with the intelligence choice before asking for intent', () => {
    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={null}
        onPrepareBuild={vi.fn()}
        onOpenBrief={vi.fn()}
      />,
    )

    expect(screen.getByRole('heading', { name: 'What kind of intelligence do you want to build?' })).toBeTruthy()
    expect(screen.getByText('World Intelligence')).toBeTruthy()
    expect(screen.queryByLabelText('Describe the intelligence you want')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))

    expect(screen.getByRole('heading', { name: 'What should ACE understand?' })).toBeTruthy()
    expect(screen.getByLabelText('Describe the intelligence you want')).toBeTruthy()
    expect(screen.getByRole('complementary', { name: 'Build context' })).toBeTruthy()
    expect(screen.getByText('Authority not granted')).toBeTruthy()
    expect(screen.getByText(/Predicted coverage and binding readiness are not projected/)).toBeTruthy()
  })

  it('keeps Custom unmistakably in Preview and never starts unsupported execution', async () => {
    const onPrepareBuild = vi.fn()
    const custom = onboardingProfilesFromResources([])[0]

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[custom]}
        session={null}
        onPrepareBuild={onPrepareBuild}
        onOpenBrief={vi.fn()}
      />,
    )

    expect(screen.getAllByText('Preview').length).toBeGreaterThan(0)
    expect(screen.getByText('Custom Intelligence is a proposal preview.')).toBeTruthy()
    expect(screen.getByText(/does not run a Custom first-Brief executor/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /Preview this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Review the plan/ }))

    expect(screen.getByText('Draft proposal only')).toBeTruthy()
    expect(screen.getByText(/v1 does not activate this Custom plan/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /View draft proposal/ }))

    expect(screen.getByRole('heading', { name: 'Your Custom proposal is ready' })).toBeTruthy()
    expect(screen.getByText('Not supported for Custom Intelligence in v1')).toBeTruthy()
    expect(screen.getByText('Preview complete · No runtime execution performed')).toBeTruthy()
    expect(onPrepareBuild).not.toHaveBeenCalled()
  })

  it('prepares and renders only the exact server review while activation stays unavailable', async () => {
    const onPrepareBuild = vi.fn().mockResolvedValue(preparedPlan)
    const onProjectBuild = vi.fn().mockResolvedValue(systemProjection)

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={null}
        onPrepareBuild={onPrepareBuild}
        onProjectBuild={onProjectBuild}
        onOpenBrief={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact plan/ }))

    await waitFor(() => expect(onPrepareBuild).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(onProjectBuild).toHaveBeenCalledWith(preparedPlan))
    expect(onPrepareBuild).toHaveBeenCalledWith(expect.objectContaining({
      profile_id: profile.profile_id,
      profile_digest: profile.profile_digest,
      subject: profile.starter_prompts[0],
      outcome_id: profile.outcomes[0].outcome_id,
      source_group_ids: [profile.source_groups[0].source_group_id],
      cadence_id: profile.default_cadence_id,
      proposed_effects: ['connect_sources', 'map_concepts', 'activate_watch', 'create_first_brief'],
    }))
    expect(screen.getByRole('heading', { name: 'Review the exact plan ACE prepared' })).toBeTruthy()
    expect(screen.getAllByText('https://example.test/official-policy')).toHaveLength(2)
    expect(screen.getAllByText('Policy record').length).toBeGreaterThan(0)
    expect(screen.getByText('Declared transitions: directive → implementation')).toBeTruthy()
    expect(screen.getAllByText('Unknowns')).toHaveLength(4)
    expect(screen.getByRole('heading', { name: 'Blueprint, bindings, coverage, and readiness' })).toBeTruthy()
    expect(screen.getByRole('list', { name: 'Predicted and observed coverage' })).toBeTruthy()
    expect(screen.getByRole('list', { name: 'Canonical initialization stages' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Checked before ACE touches anything' })).toBeTruthy()
    expect(screen.getByText('Validate inputs')).toBeTruthy()
    expect(screen.getByText('Setup unavailable')).toBeTruthy()
    expect(screen.getByText('Unavailable')).toBeTruthy()
    expect(screen.getAllByText('Not supported').length).toBeGreaterThan(0)
    expect((screen.getByRole('button', { name: /Activation unavailable/ }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.queryByText(/activation_spec/)).toBeNull()
  })

  it('retries with the byte-equivalent cached prepare input after a precise unavailable state', async () => {
    const onPrepareBuild = vi.fn()
      .mockRejectedValueOnce(new IntelligenceBuildApiError(503, 'No planner is registered for this profile.'))
      .mockResolvedValueOnce(preparedPlan)

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={null}
        onPrepareBuild={onPrepareBuild}
        onOpenBrief={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact plan/ }))
    await screen.findByText('Exact planning is not available yet.')
    fireEvent.click(screen.getByRole('button', { name: /Retry exact plan/ }))
    await screen.findByRole('heading', { name: 'Review the exact plan ACE prepared' })

    expect(onPrepareBuild).toHaveBeenCalledTimes(2)
    expect(onPrepareBuild.mock.calls[1]?.[0]).toEqual(onPrepareBuild.mock.calls[0]?.[0])
  })

  it('binds and starts only with explicit reviewed activation inputs', async () => {
    const onBindBuild = vi.fn().mockResolvedValue(boundPlan)
    const onApproveBuild = vi.fn().mockResolvedValue(approvalResult)
    const onStartBuild = vi.fn().mockResolvedValue(buildResult)
    const onBuildStarted = vi.fn()

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={null}
        onPrepareBuild={vi.fn().mockResolvedValue(activatablePlan)}
        onProjectBuild={vi.fn().mockResolvedValue(systemProjection)}
        activationSetup={{
          state: 'configured',
          inputs: {
            capability_bindings: [],
            authority_bindings: [],
          },
        }}
        onBindBuild={onBindBuild}
        onApproveBuild={onApproveBuild}
        onStartBuild={onStartBuild}
        onBuildStarted={onBuildStarted}
        onOpenBrief={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact plan/ }))
    await screen.findByRole('button', { name: /Approve and initialize/ })
    expect(screen.getByText('Supplied · pending validation')).toBeTruthy()
    expect(screen.getByText('Awaiting decision')).toBeTruthy()
    expect(screen.getAllByText('0 supplied · 1 required')).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: /Approve and initialize/ }))

    await waitFor(() => expect(onBindBuild).toHaveBeenCalledTimes(1))
    expect(onBindBuild).toHaveBeenCalledWith(expect.objectContaining({
      contract: 'ace.application.intelligence-build-plan-bind-request/v1alpha1',
      plan: activatablePlan,
      capability_bindings: [],
      authority_bindings: [],
    }))
    await waitFor(() => expect(onApproveBuild).toHaveBeenCalledWith(boundPlan))
    await waitFor(() => expect(onStartBuild).toHaveBeenCalledTimes(1))
    expect(onStartBuild).toHaveBeenCalledWith(approvedStartRequest)
    expect(onBuildStarted).toHaveBeenCalledWith(buildResult)
    expect(screen.getByRole('heading', { name: 'Builder state is not available' })).toBeTruthy()
    expect(screen.getByText('No durable Builder revision is available for this reviewed plan.')).toBeTruthy()
  })

  it('projects and renders the live resource-state read through the existing SystemProjectionReview after a successful start', async () => {
    const onBindBuild = vi.fn().mockResolvedValue(boundPlan)
    const onApproveBuild = vi.fn().mockResolvedValue(approvalResult)
    const onStartBuild = vi.fn().mockResolvedValue(buildResult)
    const onProjectResourceState = vi.fn().mockResolvedValue(liveResourceStateProjection)

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={null}
        onPrepareBuild={vi.fn().mockResolvedValue(activatablePlan)}
        onProjectBuild={vi.fn().mockResolvedValue(systemProjection)}
        activationSetup={{
          state: 'configured',
          inputs: {
            capability_bindings: [],
            authority_bindings: [],
          },
        }}
        onBindBuild={onBindBuild}
        onApproveBuild={onApproveBuild}
        onStartBuild={onStartBuild}
        onProjectResourceState={onProjectResourceState}
        onOpenBrief={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact plan/ }))
    await screen.findByRole('button', { name: /Approve and initialize/ })
    fireEvent.click(screen.getByRole('button', { name: /Approve and initialize/ }))

    await waitFor(() => expect(onProjectResourceState).toHaveBeenCalledTimes(1))
    expect(onProjectResourceState).toHaveBeenCalledWith({
      bound_plan: boundPlan,
      activation_approval_receipt_ref: approvedStartRequest.activation_approval_receipt_ref,
      selector: {
        authority_grant_ref: approvedStartRequest.resource_authority_grant_ref,
        resource_kinds: DOMAIN_HEALTH_RESOURCE_KINDS,
        subject_refs: [],
        as_of: '2026-08-13T00:02:30Z',
        available_at: '2026-08-13T00:02:31Z',
        page_size: 200,
        cursor: null,
      },
    })
    expect(screen.getByRole('heading', { name: 'Builder state is not available' })).toBeTruthy()
    await screen.findByText('Live · point-in-time read')
    expect(screen.getByRole('heading', { name: 'Blueprint, bindings, coverage, and readiness' })).toBeTruthy()
    expect(screen.getAllByText('Ready across 1 exact source binding')).toHaveLength(2)
    expect(screen.getAllByText('Recorded evidence admitted.')).toHaveLength(2)
  })

  it("renders the proposed resource-state read's exact gaps when the bound plan is not yet durably active", async () => {
    const onBindBuild = vi.fn().mockResolvedValue(boundPlan)
    const onApproveBuild = vi.fn().mockResolvedValue(approvalResult)
    const onStartBuild = vi.fn().mockResolvedValue(buildResult)
    const onProjectResourceState = vi.fn().mockResolvedValue(proposedResourceStateProjectionWithGaps)

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={null}
        onPrepareBuild={vi.fn().mockResolvedValue(activatablePlan)}
        onProjectBuild={vi.fn().mockResolvedValue(systemProjection)}
        activationSetup={{
          state: 'configured',
          inputs: {
            capability_bindings: [],
            authority_bindings: [],
          },
        }}
        onBindBuild={onBindBuild}
        onApproveBuild={onApproveBuild}
        onStartBuild={onStartBuild}
        onProjectResourceState={onProjectResourceState}
        onOpenBrief={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact plan/ }))
    await screen.findByRole('button', { name: /Approve and initialize/ })
    fireEvent.click(screen.getByRole('button', { name: /Approve and initialize/ }))

    await screen.findByText('Proposal · no authority')
    expect(screen.getByText('1 exact gap')).toBeTruthy()
    expect(screen.getByText(proposedResourceStateProjectionWithGaps.gaps[0])).toBeTruthy()
  })

  it('preserves the successful start result and shows a precise non-blocking error when the live resource-state read fails', async () => {
    const onBindBuild = vi.fn().mockResolvedValue(boundPlan)
    const onApproveBuild = vi.fn().mockResolvedValue(approvalResult)
    const onStartBuild = vi.fn().mockResolvedValue(buildResult)
    const onBuildStarted = vi.fn()
    const onProjectResourceState = vi.fn().mockRejectedValue(
      new IntelligenceBuildApiError(409, 'The bound plan is not durably approved.'),
    )

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={null}
        onPrepareBuild={vi.fn().mockResolvedValue(activatablePlan)}
        onProjectBuild={vi.fn().mockResolvedValue(systemProjection)}
        activationSetup={{
          state: 'configured',
          inputs: {
            capability_bindings: [],
            authority_bindings: [],
          },
        }}
        onBindBuild={onBindBuild}
        onApproveBuild={onApproveBuild}
        onStartBuild={onStartBuild}
        onBuildStarted={onBuildStarted}
        onProjectResourceState={onProjectResourceState}
        onOpenBrief={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact plan/ }))
    await screen.findByRole('button', { name: /Approve and initialize/ })
    fireEvent.click(screen.getByRole('button', { name: /Approve and initialize/ }))

    await waitFor(() => expect(onProjectResourceState).toHaveBeenCalledTimes(1))
    expect(onBuildStarted).toHaveBeenCalledWith(buildResult)
    expect(screen.getByRole('heading', { name: 'Builder state is not available' })).toBeTruthy()
    await screen.findByText('The bound plan is not durably approved.')
    expect(screen.getByText('Canonical projection unavailable')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('keeps the exact plan reviewable when governed activation is unavailable', async () => {
    const onBindBuild = vi.fn().mockResolvedValue(boundPlan)
    const onApproveBuild = vi.fn().mockResolvedValue(approvalResult)
    const onStartBuild = vi.fn().mockRejectedValue(
      new IntelligenceBuildApiError(503, 'No reviewed activation approval resolver is registered.'),
    )

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={null}
        onPrepareBuild={vi.fn().mockResolvedValue(activatablePlan)}
        activationSetup={{
          state: 'configured',
          inputs: {
            capability_bindings: [],
            authority_bindings: [],
          },
        }}
        onBindBuild={onBindBuild}
        onApproveBuild={onApproveBuild}
        onStartBuild={onStartBuild}
        onOpenBrief={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact plan/ }))
    await screen.findByRole('button', { name: /Approve and initialize/ })
    fireEvent.click(screen.getByRole('button', { name: /Approve and initialize/ }))

    await screen.findByText('The activation runtime is not connected.')
    expect(screen.getByText('Activation response · 503')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Review the exact plan ACE prepared' })).toBeTruthy()
    expect(onStartBuild).toHaveBeenCalledTimes(1)
  })

  it('previews the exact activation plan and requires a second explicit confirmation before its separate approval and the existing start', async () => {
    const onBindBuild = vi.fn().mockResolvedValue(boundPlan)
    const onApproveBuild = vi.fn().mockResolvedValue(approvalResult)
    const activationPlanPreview = {
      contract: 'ace.application.intelligence-activation-plan/v1alpha2',
      action: 'initial_activation',
      onboarding_handoff: { session_id: exactBriefingReady.session_id },
      spec: { spec_id: boundPlan.activation_spec.spec_id, activation_key: 'world-ai' },
      requested_effects: ['pack_activation'],
      requested_capabilities: [],
      requested_authorities: [],
      created_at: approvalResult.approval.approved_at,
      plan_id: 'intelligence_activation_plan:test',
      plan_digest: `sha256:${'8'.repeat(64)}`,
    }
    const activationCommitReference = {
      contract: 'ace.application.domain-activation-commit-reference/v1alpha2',
      authority_stage: 'historical_reference',
      live_authority: false,
      product_id: activatablePlan.request.product_id,
      activation_key: 'world-ai',
      activation_id: 'domain_activation:test',
      state: 'active',
      plan_id: activationPlanPreview.plan_id,
      plan_digest: activationPlanPreview.plan_digest,
      revision: 1,
      revision_id: 'activation_revision:test',
      revision_digest: `sha256:${'9'.repeat(64)}`,
      commit_receipt_id: 'commit_receipt:test',
      commit_receipt_digest: `sha256:${'0'.repeat(64)}`,
      committed_at: approvalResult.approval.approved_at,
    }
    const builderActivationResult = {
      contract: 'ace.http.intelligence-builder-activation-result/v1alpha1',
      receipt: { session_id: exactBriefingReady.session_id, activated_at: approvalResult.approval.approved_at },
      replayed: false,
    }
    const callOrder: string[] = []
    const onPrepareActivationPlan = vi.fn().mockImplementation(async () => {
      callOrder.push('prepare')
      return activationPlanPreview
    })
    const onApproveActivationPlan = vi.fn().mockImplementation(async () => {
      callOrder.push('approve-plan')
      return activationCommitReference
    })
    const onActivatePlan = vi.fn().mockImplementation(async () => {
      callOrder.push('activate')
      return builderActivationResult
    })
    const onStartBuild = vi.fn().mockImplementation(async () => {
      callOrder.push('start')
      return buildResult
    })

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={briefingReadySession}
        onPrepareBuild={vi.fn().mockResolvedValue(activatablePlan)}
        onProjectBuild={vi.fn().mockResolvedValue(systemProjection)}
        activationSetup={{
          state: 'configured',
          inputs: { capability_bindings: [], authority_bindings: [] },
        }}
        onBindBuild={onBindBuild}
        onApproveBuild={onApproveBuild}
        onPrepareActivationPlan={onPrepareActivationPlan}
        onApproveActivationPlan={onApproveActivationPlan}
        onActivatePlan={onActivatePlan}
        onStartBuild={onStartBuild}
        onOpenBrief={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact plan/ }))
    await screen.findByRole('button', { name: /Approve reviewed plan/ })
    expect(screen.getByText('Decision 1 of 2 · Validate inputs')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Approve reviewed plan/ }))

    await waitFor(() => expect(onPrepareActivationPlan).toHaveBeenCalledWith({
      current: exactBriefingReady,
      bound_plan: boundPlan,
      requested_at: approvalResult.approval.approved_at,
    }))
    expect(onStartBuild).not.toHaveBeenCalled()
    expect(screen.getByRole('heading', { name: 'Nothing starts until you authorize this' })).toBeTruthy()
    expect(screen.getByText('Decision 2 of 2 · Authorize & maintain')).toBeTruthy()
    expect(screen.getByText(/recorded and approved separately/)).toBeTruthy()
    const confirmButton = await screen.findByRole('button', { name: /Authorize ACE to start and maintain/ })
    expect(screen.queryByRole('button', { name: /^Approve reviewed plan/ })).toBeNull()

    fireEvent.click(confirmButton)

    await waitFor(() => expect(onStartBuild).toHaveBeenCalledTimes(1))
    expect(onApproveActivationPlan).toHaveBeenCalledWith({
      decision: 'approve',
      current: exactBriefingReady,
      bound_plan: boundPlan,
      approved_at: approvalResult.approval.approved_at,
    })
    expect(onActivatePlan).toHaveBeenCalledWith({
      bound_plan: boundPlan,
      activation_approval_receipt_ref: approvalResult.approval.receipt_ref,
      requested_at: approvalResult.approval.approved_at,
    })
    expect(onStartBuild).toHaveBeenCalledWith(approvedStartRequest)
    expect(callOrder).toEqual(['prepare', 'approve-plan', 'activate', 'start'])
    expect(screen.getByRole('heading', { name: 'Your first picture is ready' })).toBeTruthy()
    expect(screen.getByRole('list', { name: 'Source readiness, initialization, and first-Brief status' })).toBeTruthy()
    expect(screen.getByText('First-briefing-ready revision recorded')).toBeTruthy()
    expect(screen.getByText('Not active — maintenance requires its own governed activation')).toBeTruthy()
    expect(screen.getByText('Builder revision 7 · First cited Brief ready · Maintenance not active')).toBeTruthy()
  })

  it('shows only the current durable waiting state while initialization is incomplete', async () => {
    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={sourcesConnectingSession}
        onPrepareBuild={vi.fn().mockResolvedValue(activatablePlan)}
        onProjectBuild={vi.fn().mockResolvedValue(systemProjection)}
        onOpenBrief={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact plan/ }))
    await screen.findByRole('button', { name: /View build status/ })
    fireEvent.click(screen.getByRole('button', { name: /View build status/ }))

    expect(screen.getByRole('heading', { name: 'Initialization status' })).toBeTruthy()
    expect(screen.getByText('Current durable revision: sources connecting')).toBeTruthy()
    expect(screen.getByText('Waiting for a durable first-Brief result with citations')).toBeTruthy()
    expect(screen.getByText('Builder revision 2 · sources connecting')).toBeTruthy()
    expect(screen.queryByText(/assembling/i)).toBeNull()
  })

  it('fails closed before any activation write when no exact Builder session exists yet', async () => {
    const onBindBuild = vi.fn().mockResolvedValue(boundPlan)
    const onApproveBuild = vi.fn().mockResolvedValue(approvalResult)
    const onStartBuild = vi.fn().mockResolvedValue(buildResult)
    const onPrepareActivationPlan = vi.fn()
    const onApproveActivationPlan = vi.fn()
    const onActivatePlan = vi.fn()

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={null}
        onPrepareBuild={vi.fn().mockResolvedValue(activatablePlan)}
        onProjectBuild={vi.fn().mockResolvedValue(systemProjection)}
        activationSetup={{
          state: 'configured',
          inputs: { capability_bindings: [], authority_bindings: [] },
        }}
        onBindBuild={onBindBuild}
        onApproveBuild={onApproveBuild}
        onPrepareActivationPlan={onPrepareActivationPlan}
        onApproveActivationPlan={onApproveActivationPlan}
        onActivatePlan={onActivatePlan}
        onStartBuild={onStartBuild}
        onOpenBrief={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact plan/ }))
    await screen.findByRole('button', { name: /Approve reviewed plan/ })
    fireEvent.click(screen.getByRole('button', { name: /Approve reviewed plan/ }))

    await screen.findByText('ACE cannot ask you to authorize maintenance yet.')
    expect(onBindBuild).not.toHaveBeenCalled()
    expect(onApproveBuild).not.toHaveBeenCalled()
    expect(onStartBuild).not.toHaveBeenCalled()
    expect(onPrepareActivationPlan).not.toHaveBeenCalled()
    expect(onApproveActivationPlan).not.toHaveBeenCalled()
    expect(onActivatePlan).not.toHaveBeenCalled()
    expect(screen.getByText('ACE cannot ask you to authorize maintenance yet.')).toBeTruthy()
    expect(screen.getByText(/ACE has no current Builder session associated with this reviewed plan\./)).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Review the exact plan ACE prepared' })).toBeTruthy()
  })

  it('records the reviewed-build association and shows only its exact goal-selected state', async () => {
    const onBindBuild = vi.fn().mockResolvedValue(boundPlan)
    const onApproveBuild = vi.fn().mockResolvedValue(approvalResult)
    const onAssociateBuilderSession = vi.fn().mockResolvedValue({
      contract: 'ace.http.intelligence-build-session-association-result/v1alpha1',
      bound_plan_id: boundPlan.bound_plan_id,
      bound_plan_digest: boundPlan.bound_plan_digest,
      approval: approvalResult.approval,
      session: exactGoalSelected,
      replayed: false,
    })
    const onStartBuild = vi.fn().mockResolvedValue(buildResult)
    const onPrepareActivationPlan = vi.fn()
    const onApproveActivationPlan = vi.fn()
    const onActivatePlan = vi.fn()

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={null}
        onPrepareBuild={vi.fn().mockResolvedValue(activatablePlan)}
        onProjectBuild={vi.fn().mockResolvedValue(systemProjection)}
        activationSetup={{
          state: 'configured',
          inputs: { capability_bindings: [], authority_bindings: [] },
        }}
        onBindBuild={onBindBuild}
        onApproveBuild={onApproveBuild}
        onAssociateBuilderSession={onAssociateBuilderSession}
        onPrepareActivationPlan={onPrepareActivationPlan}
        onApproveActivationPlan={onApproveActivationPlan}
        onActivatePlan={onActivatePlan}
        onStartBuild={onStartBuild}
        onOpenBrief={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact plan/ }))
    await screen.findByRole('button', { name: /Approve reviewed plan/ })
    fireEvent.click(screen.getByRole('button', { name: /Approve reviewed plan/ }))

    await waitFor(() => expect(onAssociateBuilderSession).toHaveBeenCalledWith(
      boundPlan,
      approvalResult.approval.receipt_ref,
    ))
    expect(onBindBuild).toHaveBeenCalledTimes(1)
    expect(onApproveBuild).toHaveBeenCalledTimes(1)
    expect(onPrepareActivationPlan).not.toHaveBeenCalled()
    expect(onApproveActivationPlan).not.toHaveBeenCalled()
    expect(onActivatePlan).not.toHaveBeenCalled()
    expect(onStartBuild).not.toHaveBeenCalled()
    expect(screen.getByRole('heading', { name: 'Initialization status' })).toBeTruthy()
    expect(screen.getByText(/The latest durable Builder revision is goal selected/)).toBeTruthy()
    expect(screen.getByText(/Maintenance authorization requires an exact first-briefing-ready revision/)).toBeTruthy()
    expect(screen.getByText('Builder revision 1 · goal selected')).toBeTruthy()
  })

  it('stops before the existing start when the activation-plan preview itself fails', async () => {
    const onBindBuild = vi.fn().mockResolvedValue(boundPlan)
    const onApproveBuild = vi.fn().mockResolvedValue(approvalResult)
    const onStartBuild = vi.fn().mockResolvedValue(buildResult)
    const onPrepareActivationPlan = vi.fn().mockRejectedValue(
      new IntelligenceBuildApiError(503, 'No activation-plan coordinator is registered.'),
    )
    const onApproveActivationPlan = vi.fn()
    const onActivatePlan = vi.fn()

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={briefingReadySession}
        onPrepareBuild={vi.fn().mockResolvedValue(activatablePlan)}
        onProjectBuild={vi.fn().mockResolvedValue(systemProjection)}
        activationSetup={{
          state: 'configured',
          inputs: { capability_bindings: [], authority_bindings: [] },
        }}
        onBindBuild={onBindBuild}
        onApproveBuild={onApproveBuild}
        onPrepareActivationPlan={onPrepareActivationPlan}
        onApproveActivationPlan={onApproveActivationPlan}
        onActivatePlan={onActivatePlan}
        onStartBuild={onStartBuild}
        onOpenBrief={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact plan/ }))
    await screen.findByRole('button', { name: /Approve reviewed plan/ })
    fireEvent.click(screen.getByRole('button', { name: /Approve reviewed plan/ }))

    await screen.findByText('The activation runtime is not connected.')
    expect(screen.getByText(/No activation-plan coordinator is registered\./)).toBeTruthy()
    expect(onApproveActivationPlan).not.toHaveBeenCalled()
    expect(onActivatePlan).not.toHaveBeenCalled()
    expect(onStartBuild).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /Authorize ACE to start and maintain/ })).toBeNull()
  })

  it('retries only from an exact loaded blocked Builder revision', async () => {
    const exactBlocked = {
      contract: 'ace.application.intelligence-builder-session-revision/v1alpha1',
      product_id: activatablePlan.request.product_id,
      session_id: 'intelligence_builder_session:world',
      correlation_id: 'correlation:world',
      goal_ref: 'goal:world',
      sequence: 8,
      stage: 'blocked',
      prior_revision_id: 'intelligence_builder_session_revision:prior',
      prior_revision_digest: `sha256:${'1'.repeat(64)}`,
      transition_authority: 'core_runtime',
      transition_actor_ref: activatablePlan.request.actor_ref,
      approval_receipt_ref: null,
      artifacts: [],
      block_reason: 'source_unavailable',
      resume_stage: 'sources_connecting',
      safe_diagnostic: 'One reviewed source is temporarily unavailable.',
      occurred_at: '2026-08-13T00:03:00Z',
      revision_id: 'intelligence_builder_session_revision:blocked',
      revision_digest: `sha256:${'2'.repeat(64)}`,
    } as const
    const blockedSession = {
      session_id: exactBlocked.session_id,
      goal_ref: exactBlocked.goal_ref,
      sequence: exactBlocked.sequence,
      stage: exactBlocked.stage,
      artifacts: [],
      block_reason: exactBlocked.block_reason,
      resume_stage: exactBlocked.resume_stage,
      safe_diagnostic: exactBlocked.safe_diagnostic,
      exact_revision: exactBlocked,
    } as const
    const onRetryBuild = vi.fn().mockResolvedValue({
      ...exactBlocked,
      sequence: 9,
      stage: 'retrying',
      prior_revision_id: exactBlocked.revision_id,
      prior_revision_digest: exactBlocked.revision_digest,
      revision_id: 'intelligence_builder_session_revision:retrying',
      revision_digest: `sha256:${'3'.repeat(64)}`,
    })

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={blockedSession}
        onPrepareBuild={vi.fn().mockResolvedValue(activatablePlan)}
        onRetryBuild={onRetryBuild}
        onOpenBrief={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact plan/ }))
    await screen.findByRole('button', { name: /View build status/ })
    fireEvent.click(screen.getByRole('button', { name: /View build status/ }))
    expect(screen.getByRole('heading', { name: 'ACE needs your attention' })).toBeTruthy()
    expect(screen.getAllByText('One reviewed source is temporarily unavailable.')).toHaveLength(2)
    expect(screen.getAllByText('Not reported').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: /Retry governed step/ }))

    await waitFor(() => expect(onRetryBuild).toHaveBeenCalledWith(exactBlocked))
    expect(screen.getByRole('heading', { name: 'Retry recorded' })).toBeTruthy()
    expect(screen.getByText('Retrying revision recorded; a later durable revision must confirm the outcome.')).toBeTruthy()
  })

  it.each([
    [404, 'This starting point is no longer installed.'],
    [409, 'This proposed plan is out of date.'],
    [503, 'Exact planning is not available yet.'],
  ])('renders the bounded %s prepare state without advancing', async (status, title) => {
    const onPrepareBuild = vi.fn().mockRejectedValue(
      new IntelligenceBuildApiError(status, `Exact prepare stopped with ${status}.`),
    )
    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={null}
        onPrepareBuild={onPrepareBuild}
        onOpenBrief={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Prepare exact plan/ }))

    await screen.findByText(title)
    expect(screen.getByText(`Prepare response · ${status}`)).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Choose the evidence ACE can use' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Activation unavailable/ })).toBeNull()
  })
})
