import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { OnboardingPreview } from './OnboardingPreview'
import type { IntelligenceOnboardingProfile } from './onboardingModel'

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
})
