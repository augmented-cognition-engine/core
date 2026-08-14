import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { IntelligenceBuildApiError, type IntelligenceBuildPlan } from '@/api/intelligenceBuildsApi'
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

    expect(screen.getByRole('heading', { name: 'What do you need to stay ahead of?' })).toBeTruthy()
    expect(screen.getByLabelText('Describe the intelligence you want')).toBeTruthy()
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

    await waitFor(() => expect(onPrepareBuild).toHaveBeenCalledTimes(1))
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
    expect(screen.getByText('https://example.test/official-policy')).toBeTruthy()
    expect(screen.getByText('Policy record')).toBeTruthy()
    expect(screen.getByText('Declared transitions: directive → implementation')).toBeTruthy()
    expect(screen.getAllByText('Unknowns')).toHaveLength(4)
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
