import { describe, expect, it } from 'vitest'

import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'
import {
  onboardingProfileFromResources,
  onboardingSessionFromResources,
  hasOnboardingProfileResource,
  parseBuilderSession,
  parseOnboardingProfile,
} from './onboardingModel'

const profile = {
  contract: 'ace.intelligence.onboarding-profile/v1alpha1',
  profile_id: 'onboarding_profile:test',
  topic_id: 'test-topic',
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

const session = {
  contract: 'ace.application.intelligence-builder-session-revision/v1alpha1',
  session_id: 'intelligence_builder_session:test',
  goal_ref: 'goal:test',
  sequence: 7,
  stage: 'first_briefing_ready',
  artifacts: [{
    artifact_kind: 'first_briefing_preview',
    artifact_id: 'brief:test',
    artifact_digest: `sha256:${'a'.repeat(64)}`,
  }],
  block_reason: null,
  resume_stage: null,
  safe_diagnostic: null,
}

function resource(kind: 'builder_profile' | 'builder_session', payload: unknown, revision = 1): IntelligenceResourceRecord {
  return {
    reference: {
      resource_kind: kind,
      revision,
      available_at: `2026-08-13T12:0${revision}:00Z`,
    },
    payload: {
      contract: 'ace.intelligence.canonical-json-value/v1alpha1',
      value_json: JSON.stringify(payload),
    },
  } as IntelligenceResourceRecord
}

describe('Atrium onboarding resources', () => {
  it('accepts the Core-owned declarative profile contract', () => {
    expect(parseOnboardingProfile(profile)).toMatchObject({
      display_name: 'Test Intelligence',
      completion_label: 'Open the test brief',
    })
  })

  it('rejects unknown or malformed payloads', () => {
    expect(parseOnboardingProfile({ ...profile, contract: 'unknown' })).toBeNull()
    expect(parseOnboardingProfile({ ...profile, outcomes: [] })).toBeNull()
    expect(parseBuilderSession({ ...session, stage: 'invented' })).toBeNull()
  })

  it('reads a canonical builder profile and otherwise stays domain-neutral', () => {
    expect(onboardingProfileFromResources([resource('builder_profile', profile)]).display_name).toBe('Test Intelligence')
    expect(hasOnboardingProfileResource([resource('builder_profile', profile)])).toBe(true)
    expect(hasOnboardingProfileResource([])).toBe(false)
    expect(onboardingProfileFromResources([]).display_name).toBe('Your Intelligence')
    expect(onboardingProfileFromResources([]).outcomes.some((item) => item.label.includes('AI'))).toBe(false)
  })

  it('uses the latest exact builder session revision', () => {
    const older = resource('builder_session', { ...session, sequence: 6, stage: 'intelligence_model_approved' }, 6)
    const latest = resource('builder_session', session, 7)
    expect(onboardingSessionFromResources([latest, older])).toMatchObject({
      sequence: 7,
      stage: 'first_briefing_ready',
      artifacts: [{ artifact_kind: 'first_briefing_preview' }],
    })
  })
})
