import { describe, expect, it } from 'vitest'

import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'
import { onboardingProfileFromResources, parseOnboardingProfile } from './onboardingModel'

const profile = {
  contract: 'ace.domain-pack.intelligence-onboarding-profile/v1alpha1',
  display_name: 'Test Intelligence',
  prompt: 'What matters?',
  description: 'Choose an outcome.',
  outcomes: [{
    outcome_id: 'test',
    label: 'Track the test',
    description: 'Follow material test changes.',
    icon_hint: 'research',
    recommended_topic_labels: ['Tests'],
    recommended_intelligence_labels: ['Test movement'],
  }],
  cadences: [{ cadence_id: 'weekly', label: 'Weekly', description: 'Once a week.' }],
  default_cadence_id: 'weekly',
  first_value: { completion_label: 'Open the test brief' },
}

describe('Atrium onboarding profile', () => {
  it('accepts a bounded declarative profile', () => {
    expect(parseOnboardingProfile(profile)).toMatchObject({
      display_name: 'Test Intelligence',
      completion_label: 'Open the test brief',
    })
  })

  it('rejects unknown or malformed payloads', () => {
    expect(parseOnboardingProfile({ ...profile, contract: 'unknown' })).toBeNull()
    expect(parseOnboardingProfile({ ...profile, outcomes: [] })).toBeNull()
  })

  it('reads only an admitted context-manifest projection and otherwise stays domain-neutral', () => {
    const record = {
      reference: { resource_kind: 'context_manifest' },
      payload: { onboarding_profile: profile },
    } as IntelligenceResourceRecord
    expect(onboardingProfileFromResources([record]).display_name).toBe('Test Intelligence')
    expect(onboardingProfileFromResources([]).display_name).toBe('Your Intelligence')
    expect(onboardingProfileFromResources([]).outcomes.some((item) => item.label.includes('AI'))).toBe(false)
  })
})
