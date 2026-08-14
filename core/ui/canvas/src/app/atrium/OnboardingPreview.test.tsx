import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { OnboardingPreview } from './OnboardingPreview'
import type { IntelligenceOnboardingProfile } from './onboardingModel'
import { onboardingProfilesFromResources } from './onboardingModel'

const profile: IntelligenceOnboardingProfile = {
  contract: 'ace.intelligence.onboarding-profile/v1alpha1',
  profile_id: 'onboarding_profile:world',
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

describe('Atrium Intelligence Builder onboarding', () => {
  it('starts with the intelligence choice before asking for intent', () => {
    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={null}
        onStartBuild={vi.fn()}
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
    const onStartBuild = vi.fn()
    const custom = onboardingProfilesFromResources([])[0]

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[custom]}
        session={null}
        onStartBuild={onStartBuild}
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
    expect(onStartBuild).not.toHaveBeenCalled()
  })

  it('preserves supported domain build execution', async () => {
    const onStartBuild = vi.fn().mockResolvedValue(undefined)

    render(
      <OnboardingPreview
        open
        onOpenChange={vi.fn()}
        profiles={[profile]}
        session={null}
        onStartBuild={onStartBuild}
        onOpenBrief={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Use this intelligence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Choose evidence/ }))
    fireEvent.click(screen.getByRole('button', { name: /Review the plan/ }))
    fireEvent.click(screen.getByRole('button', { name: /Build my intelligence/ }))

    await waitFor(() => expect(onStartBuild).toHaveBeenCalledTimes(1))
    expect(onStartBuild).toHaveBeenCalledWith({
      profile_id: profile.profile_id,
      subject: profile.starter_prompts[0],
      outcome_id: profile.outcomes[0].outcome_id,
      source_group_ids: [profile.source_groups[0].source_group_id],
      cadence_id: profile.default_cadence_id,
    })
  })
})
