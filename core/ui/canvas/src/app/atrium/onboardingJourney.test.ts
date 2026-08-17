import { describe, expect, it } from 'vitest'

import type { IntelligenceBuildPlan } from '@/api/intelligenceBuildsApi'

import type { IntelligenceBuilderSession, IntelligenceOnboardingProfile } from './onboardingModel'
import {
  activationReadiness,
  semanticOnboardingStages,
  sourceBindingReadiness,
} from './onboardingJourney'

const profile: IntelligenceOnboardingProfile = {
  contract: 'ace.intelligence.onboarding-profile/v1alpha1',
  profile_id: 'onboarding_profile:world',
  profile_digest: `sha256:${'1'.repeat(64)}`,
  topic_id: 'world',
  domain_label: 'World Intelligence',
  topic_label: 'Artificial intelligence',
  display_name: 'AI Command Center',
  prompt: 'What should ACE understand?',
  description: 'Build a cited picture of meaningful AI change.',
  starter_prompts: ['Keep me ahead of meaningful AI changes.'],
  outcomes: [{
    outcome_id: 'track-ai',
    label: 'Track AI change',
    description: 'Follow material change.',
    icon_hint: 'research',
    recommended_topic_labels: ['Policy'],
    recommended_intelligence_labels: ['Policy movement'],
  }],
  source_groups: [{
    source_group_id: 'official-records',
    label: 'Official records',
    description: 'Primary official evidence.',
    evidence_role: 'authoritative_record',
    source_ids: ['federal-register'],
    source_labels: ['Federal Register'],
    access_label: 'Public · no credentials',
    default_selected: true,
  }],
  cadences: [{ cadence_id: 'daily', label: 'Daily', description: 'Orient me daily.' }],
  default_cadence_id: 'daily',
  completion_label: 'Open the first Brief',
}

const exactPlan = {
  contract: 'ace.application.intelligence-build-plan/v1alpha3',
  request: {
    contract: 'ace.application.intelligence-build-plan-request/v1alpha2',
    product_id: 'product:world',
    actor_ref: 'user:default',
    client_request_id: 'atrium-request:world',
    profile_id: profile.profile_id,
    profile_digest: profile.profile_digest ?? '',
    subject: profile.starter_prompts[0],
    outcome_id: profile.outcomes[0].outcome_id,
    source_group_ids: ['official-records'],
    cadence_id: 'daily',
    proposed_effects: ['connect_sources', 'map_concepts', 'activate_watch', 'create_first_brief'],
    requested_at: '2026-08-15T00:00:00Z',
    request_id: 'intelligence_build_plan_request:world',
    request_digest: `sha256:${'2'.repeat(64)}`,
  },
  pack_reference: {
    pack_id: 'world',
    pack_version: '1.0.0',
    compiled_pack_id: `pack_ir:${'3'.repeat(32)}`,
    pack_digest: `sha256:${'3'.repeat(64)}`,
  },
  activation_proposal: {
    contract: 'ace.application.intelligence-build-activation-proposal/v1alpha1',
    product_id: 'product:world',
    activation_key: 'world',
    pack: {
      pack_id: 'world',
      pack_version: '1.0.0',
      compiled_pack_id: `pack_ir:${'3'.repeat(32)}`,
      pack_digest: `sha256:${'3'.repeat(64)}`,
    },
    overlay: {},
    capability_requirement_ids: ['recorded-source-reader'],
    authority_request_ids: ['source-read'],
    proposal_id: 'intelligence_build_activation_proposal:world',
    proposal_digest: `sha256:${'4'.repeat(64)}`,
  },
  recorded_source_selection_refs: [{
    contract: 'ace.application.recorded-source-selection-reference/v1alpha1',
    source_group_id: 'official-records',
    selection_id: 'recorded_source_selection:official-records',
    selection_digest: `sha256:${'5'.repeat(64)}`,
  }],
  review_projection: {
    contract: 'ace.application.intelligence-build-review-projection/v1alpha1',
    request_id: 'intelligence_build_plan_request:world',
    request_digest: `sha256:${'2'.repeat(64)}`,
    profile_id: profile.profile_id,
    profile_digest: profile.profile_digest ?? '',
    subject: profile.starter_prompts[0],
    outcome_id: profile.outcomes[0].outcome_id,
    outcome_label: profile.outcomes[0].label,
    sources: [{
      selection: {
        contract: 'ace.application.recorded-source-selection-reference/v1alpha1',
        source_group_id: 'official-records',
        selection_id: 'recorded_source_selection:official-records',
        selection_digest: `sha256:${'5'.repeat(64)}`,
      },
      label: 'Federal Register',
      evidence_role: 'authoritative_record',
      source_uri: 'https://www.federalregister.gov/',
      source_definition_ref: 'source_definition:federal-register',
      entity_type_id: 'policy',
      entity_ref: 'entity:policy',
      observed_at: '2026-08-15T00:00:00Z',
    }],
    concepts: [],
    watches: [],
    cadence_id: 'daily',
    cadence_label: 'Daily',
    cadence_description: 'Orient me daily.',
    effects: [],
    projection_id: 'intelligence_build_review:world',
    projection_digest: `sha256:${'6'.repeat(64)}`,
  },
  plan_id: 'intelligence_build_plan:world',
  plan_digest: `sha256:${'7'.repeat(64)}`,
} as const satisfies IntelligenceBuildPlan

function session(stage: IntelligenceBuilderSession['stage'], overrides: Partial<IntelligenceBuilderSession> = {}): IntelligenceBuilderSession {
  return {
    session_id: 'intelligence_builder_session:world',
    goal_ref: 'goal:world',
    sequence: 8,
    stage,
    artifacts: [],
    block_reason: null,
    resume_stage: null,
    safe_diagnostic: null,
    ...overrides,
  }
}

describe('eight-stage onboarding reconciliation', () => {
  it('keeps exact planning distinct from binding, authority, coverage, and runtime progress', () => {
    const stages = semanticOnboardingStages({
      subject: profile.starter_prompts[0],
      plan: exactPlan,
      session: null,
      customPreview: false,
    })

    expect(stages).toHaveLength(8)
    expect(stages.map((stage) => [stage.number, stage.chapter, stage.id])).toEqual([
      [1, 'Intent', 'define_goal'],
      [2, 'Intent', 'generate_blueprint'],
      [3, 'Review', 'review_refine'],
      [4, 'Evidence', 'build_source_plan'],
      [5, 'Evidence', 'estimate_coverage'],
      [6, 'Activate', 'initialize_domain'],
      [7, 'Activate', 'validate_first_model'],
      [8, 'Activate', 'activate_maintenance'],
    ])
    expect(stages.find((stage) => stage.id === 'build_source_plan')?.state).toBe('complete')
    expect(stages.find((stage) => stage.id === 'estimate_coverage')?.state).toBe('unsupported')
    expect(stages.find((stage) => stage.id === 'initialize_domain')?.state).toBe('waiting')
    expect(stages.find((stage) => stage.id === 'activate_maintenance')?.detail).toContain('no implementation binding')
  })

  it('uses durable session revisions for first-Brief readiness and retry state', () => {
    const ready = semanticOnboardingStages({
      subject: profile.starter_prompts[0],
      plan: exactPlan,
      session: session('first_briefing_ready'),
      customPreview: false,
    })
    expect(ready.find((stage) => stage.id === 'initialize_domain')?.state).toBe('complete')
    expect(ready.find((stage) => stage.id === 'validate_first_model')?.state).toBe('complete')
    expect(ready.find((stage) => stage.id === 'activate_maintenance')?.state).toBe('waiting')

    const retrying = semanticOnboardingStages({
      subject: profile.starter_prompts[0],
      plan: exactPlan,
      session: session('retrying', {
        resume_stage: 'sources_connecting',
        block_reason: 'failed_connector',
        safe_diagnostic: 'The admitted public source did not respond.',
      }),
      customPreview: false,
    })
    expect(retrying.find((stage) => stage.id === 'initialize_domain')).toMatchObject({
      state: 'current',
      detail: expect.stringContaining('later revision'),
    })
  })

  it('never treats a public access label or exact selection as readiness', () => {
    expect(sourceBindingReadiness(profile, ['official-records'], exactPlan)).toEqual([expect.objectContaining({
      source_group_id: 'official-records',
      access_label: 'Public · no credentials',
      state: 'unsupported',
      detail: expect.stringContaining('readiness are not projected'),
    })])
  })

  it('keeps Custom proposal-only through initialization, validation, and maintenance', () => {
    const stages = semanticOnboardingStages({
      subject: 'Track the changes that matter to me.',
      plan: null,
      session: null,
      customPreview: true,
    })
    expect(stages.find((stage) => stage.id === 'initialize_domain')?.state).toBe('unsupported')
    expect(stages.find((stage) => stage.id === 'validate_first_model')?.detail).toContain('no first-Brief executor')
    expect(stages.find((stage) => stage.id === 'activate_maintenance')?.state).toBe('unsupported')
    expect(activationReadiness(null, true)).toMatchObject({ state: 'proposal_only' })
  })
})
