import { describe, expect, it } from 'vitest'

import type { IntelligenceResourceRecord } from '@/api/intelligenceResourcesApi'
import {
  onboardingProfileFromResources,
  onboardingProfilesFromResources,
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
  domain_label: 'Test domain',
  topic_label: 'Testing',
  prompt: 'What matters?',
  description: 'Choose an outcome.',
  starter_prompts: ['Keep me ahead of meaningful test changes.'],
  outcomes: [{
    outcome_id: 'test',
    label: 'Track the test',
    description: 'Follow material test changes.',
    icon_hint: 'research',
    recommended_topic_labels: ['Tests'],
    recommended_intelligence_labels: ['Test movement'],
  }],
  source_groups: [{
    source_group_id: 'public_records',
    label: 'Public records',
    description: 'Primary evidence for the test.',
    evidence_role: 'authoritative_record',
    source_ids: ['test_registry'],
    source_labels: ['Test Registry'],
    access_label: 'Public · no credentials',
    default_selected: true,
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
      domain_label: 'Test domain',
      topic_label: 'Testing',
      starter_prompts: ['Keep me ahead of meaningful test changes.'],
      completion_label: 'Open the test brief',
      source_groups: [{ source_group_id: 'public_records', default_selected: true }],
    })
  })

  it('rejects unknown or malformed payloads', () => {
    expect(parseOnboardingProfile({ ...profile, contract: 'unknown' })).toBeNull()
    expect(parseOnboardingProfile({ ...profile, outcomes: [] })).toBeNull()
    expect(parseOnboardingProfile({ ...profile, starter_prompts: [3] })).toBeNull()
    expect(parseOnboardingProfile({ ...profile, source_groups: [{ ...profile.source_groups[0], source_ids: [] }] })).toBeNull()
    expect(parseBuilderSession({ ...session, stage: 'invented' })).toBeNull()
  })

  it('reads a canonical builder profile and otherwise stays domain-neutral', () => {
    expect(onboardingProfileFromResources([resource('builder_profile', profile)]).display_name).toBe('Test Intelligence')
    expect(hasOnboardingProfileResource([resource('builder_profile', profile)])).toBe(true)
    expect(hasOnboardingProfileResource([])).toBe(false)
    expect(onboardingProfileFromResources([]).display_name).toBe('Custom Intelligence')
    expect(onboardingProfileFromResources([]).outcomes.some((item) => item.label.includes('AI'))).toBe(false)
  })

  it('builds a domain-neutral catalog and always offers the custom Builder path', () => {
    const market = { ...profile, profile_id: 'onboarding_profile:market', domain_label: 'Market Intelligence' }
    expect(onboardingProfilesFromResources([
      resource('builder_profile', profile),
      resource('builder_profile', market, 2),
      resource('builder_profile', profile, 3),
    ]).map((item) => item.domain_label)).toEqual(['Test domain', 'Market Intelligence', 'Custom Intelligence'])
    expect(onboardingProfilesFromResources([]).map((item) => item.domain_label)).toEqual(['Custom Intelligence'])
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
