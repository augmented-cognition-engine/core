import { expect, test } from '@playwright/test'

const availableAt = '2026-08-12T18:00:00.000Z'

function resource(kind: string, id: string, title: string, summary: string, provenance: unknown[] = []) {
  return {
    contract: 'ace.intelligence.resource-plane-record/v1alpha1',
    reference: {
      contract: 'ace.intelligence.resource-plane-reference/v1alpha1',
      product_id: 'product:ai-command-center',
      resource_kind: kind,
      resource_id: `${kind}:${id}`,
      resource_digest: `sha256:${id.padEnd(64, 'a').slice(0, 64)}`,
      resource_contract: `ace.demo.${kind}/v1`,
      revision: 1,
      as_of: availableAt,
      available_at: availableAt,
    },
    availability: 'available',
    title,
    summary,
    subject_refs: ['entity:artificial-intelligence'],
    provenance,
    supersedes: null,
    payload: { topic: 'artificial intelligence' },
    degraded_reason_refs: [],
  }
}

function exactPreparedPlan(body: Record<string, unknown>) {
  const selection = {
    contract: 'ace.application.recorded-source-selection-reference/v1alpha1',
    source_group_id: 'official_records',
    selection_id: 'recorded_source_selection:official-records',
    selection_digest: `sha256:${'3'.repeat(64)}`,
  }
  const effects = [
    ['connect_sources', 'Connect reviewed evidence', 'Admit the exact Federal Register and White House records shown above.', 'Ground every later change in the reviewed public records.', 'Use the installed recorded-source adapters after approval.', 'Only after deliberate owner approval.'],
    ['map_concepts', 'Map the AI policy concepts', 'Resolve the exact policy directive and implementation entities shown above.', 'Connect later evidence to the same concepts without guessing identities.', 'Apply the installed World AI ontology to admitted records.', 'After the reviewed records are admitted.'],
    ['activate_watch', 'Watch policy progression', 'Compare directive status with later reported implementation status.', 'Surface the actual change instead of a vague change notification.', 'Run the declared categorical transition detector.', 'Daily, after activation.'],
    ['create_first_brief', 'Create the first Brief', 'Explain what changed, why it matters, how ACE knows, and when it changed.', 'Give the operator a decision-ready starting picture.', 'Use only admitted evidence and the selected World AI Brief template.', 'After a material reviewed shift is routed.'],
  ] as const
  return {
    contract: 'ace.application.intelligence-build-plan/v1alpha2',
    request: {
      ...body,
      contract: 'ace.application.intelligence-build-plan-request/v1alpha2',
      product_id: 'product:world-ai-command-center',
      actor_ref: 'principal:local-owner',
      request_id: 'intelligence_build_plan_request:world-ai',
      request_digest: `sha256:${'4'.repeat(64)}`,
    },
    recorded_source_selection_refs: [selection],
    review_projection: {
      contract: 'ace.application.intelligence-build-review-projection/v1alpha1',
      request_id: 'intelligence_build_plan_request:world-ai',
      request_digest: `sha256:${'4'.repeat(64)}`,
      profile_id: body.profile_id,
      profile_digest: body.profile_digest,
      subject: body.subject,
      outcome_id: body.outcome_id,
      outcome_label: 'Set strategy or evaluate investments',
      sources: [{
        selection,
        label: 'Federal Register',
        evidence_role: 'authoritative record',
        source_uri: 'https://www.federalregister.gov/',
        source_definition_ref: 'recorded_source_definition:federal-register',
        entity_type_id: 'ai_policy_action',
        entity_ref: 'entity:executive-order-14409',
        observed_at: availableAt,
      }],
      concepts: [{
        entity_type_id: 'ai_policy_action',
        entity_ref: 'entity:executive-order-14409',
        display_name: 'AI policy action',
        source_selections: [selection],
      }],
      watches: [{
        detector_id: 'detector:policy-progression',
        detector_family: 'categorical_transition',
        entity_type_id: 'ai_policy_action',
        entity_refs: ['entity:executive-order-14409'],
        attribute_id: 'implementation_status',
        change_rule: 'directive_issued → implementation_reported',
        shift_type: 'policy_progression',
        signal_type: 'policy_implementation_signal',
        cadence_id: body.cadence_id,
        cadence_label: 'Daily pulse',
      }],
      cadence_id: body.cadence_id,
      cadence_label: 'Daily pulse',
      cadence_description: 'A concise daily orientation.',
      effects: effects.map(([effect, label, what, why, how, when]) => ({
        effect,
        label,
        what,
        why,
        how,
        when,
        unknowns: ['No authority has been granted and no runtime work has started.'],
      })),
      projection_id: 'intelligence_build_review:world-ai',
      projection_digest: `sha256:${'5'.repeat(64)}`,
    },
    plan_id: 'intelligence_build_plan:world-ai',
    plan_digest: `sha256:${'6'.repeat(64)}`,
  }
}

test('Atrium is a briefing-first Intelligence OS over governed resources', async ({ page }, testInfo) => {
  const source = resource(
    'source',
    'model-provider-releases',
    'Model provider release feeds',
    'Official model cards, release notes, and provider announcements.',
  )
  const shift = resource(
    'shift',
    'token-economics',
    'Frontier inference costs moved down again',
    'Published token prices fell while long-context tiers expanded across two providers.',
    [source.reference],
  )
  shift.payload = {
    what_changed: 'Published token prices fell while long-context tiers expanded across two providers.',
    why_it_matters: 'Capability and unit cost are moving independently, changing enterprise build-versus-buy assumptions.',
    how_we_know: 'The admitted provider release feed and its governed shift record support this answer.',
    when_it_changed: 'ACE detected the change in the current watch window.',
  }
  const brief = resource(
    'brief',
    'ai-command-brief',
    'AI Command Brief — capability up, unit cost down',
    'The market is separating model capability from model economics. Buyers can now demand both stronger reasoning and lower unit cost.',
    [source.reference, shift.reference],
  )

  await page.route('**/auth/token', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: 'test-token' }) }),
  )
  await page.route('**/v1/intelligence/resources/query', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contract: 'ace.intelligence.resource-plane-page/v1alpha1',
        query_id: 'resource_query:demo',
        query_digest: `sha256:${'b'.repeat(64)}`,
        product_id: 'product:ai-command-center',
        actor_ref: 'principal:demo-analyst',
        as_of: '2000-01-01T00:00:00.000Z',
        available_at: availableAt,
        evaluated_at: availableAt,
        state: 'complete',
        items: [
          source,
          resource('connection', 'public-web', 'Public web intelligence', 'Authorized public sources connected and admitting evidence.'),
          resource('agent', 'intelligence-analyst', 'Intelligence Analyst', 'Watching model releases, economics, security, policy, and capital flows.'),
          resource('signal', 'provider-pricing', 'Provider pricing signal', 'Three provider price changes entered the current watch window.', [source.reference]),
          shift,
          resource('case', 'enterprise-economics', 'Enterprise AI economics opportunity', 'Revisit build-versus-buy assumptions using current unit economics.', [shift.reference]),
          brief,
          resource('decision', 'refresh-economic-model', 'Refresh the AI economic model', 'Leadership accepted a new cost baseline for scenario planning.', [brief.reference]),
        ],
        next_cursor: null,
        degraded_reason_refs: [],
        page_id: 'resource_page:demo',
        page_digest: `sha256:${'c'.repeat(64)}`,
      }),
    }),
  )

  await page.goto('/atrium')

  await expect(page.getByRole('heading', { name: 'Intelligence' })).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Open AI Command Brief — capability up, unit cost down' }),
  ).toBeVisible()
  await expect(page.getByText('Opportunities', { exact: true })).toBeVisible()
  await expect(page.getByText('Connections', { exact: true })).toBeVisible()

  await page.getByLabel('Ask ACE about current intelligence').fill('What changed in token economics?')
  await page.getByLabel('Ask ACE', { exact: true }).click()
  const askAceAnswer = page.getByRole('region', { name: 'Ask ACE answer' })
  await expect(askAceAnswer.getByText('Published token prices fell while long-context tiers expanded across two providers.').first()).toBeVisible()
  await expect(askAceAnswer.getByText('Why it matters', { exact: true })).toBeVisible()
  await expect(askAceAnswer.getByText('Evidence trail', { exact: true })).toBeVisible()
  await expect(askAceAnswer.getByText('Frontier inference costs moved down again')).toBeVisible()
  await expect(askAceAnswer.getByText(/cited record/)).toBeVisible()

  await page.getByText('Opportunities', { exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Opportunities' })).toBeVisible()
  await expect(page.getByText('Enterprise AI economics opportunity')).toBeVisible()

  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.goto('/atrium')
    await page.screenshot({ path: testInfo.outputPath('atrium-intelligence-os.png'), fullPage: true })
  }

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/atrium')
  await page.getByRole('button', { name: 'Toggle Sidebar' }).click()
  await expect(page.getByText('Connections', { exact: true })).toBeVisible()
})

test('Atrium makes Custom proposal-only and stops before unsupported v1 execution', async ({ page }, testInfo) => {
  const onboardingProfile = {
    contract: 'ace.domain-pack.intelligence-onboarding-profile/v1alpha1',
    profile_id: 'intelligence_onboarding_profile:world-ai-command-center',
    profile_digest: `sha256:${'7'.repeat(64)}`,
    domain_label: 'World Intelligence',
    topic_label: 'Artificial intelligence',
    display_name: 'AI Command Center',
    prompt: 'What do you need to stay ahead of?',
    description: 'Choose the AI decision context. ACE recommends the sources, concepts, watches, and briefing system.',
    starter_prompts: ['Keep me ahead of meaningful AI capability, cost, policy, and adoption shifts.'],
    outcomes: [
      { outcome_id: 'strategy', label: 'Set strategy or evaluate investments', description: 'See which capital and capability moves are becoming durable advantage.', icon_hint: 'strategy', recommended_topic_labels: ['Capital', 'Capabilities'], recommended_intelligence_labels: ['Capital-to-capability'] },
      { outcome_id: 'frontier', label: 'Track frontier research and products', description: 'Follow advances into evaluated products.', icon_hint: 'research', recommended_topic_labels: ['Open research', 'Models & capabilities'], recommended_intelligence_labels: ['Research-to-product diffusion'] },
    ],
    source_groups: [
      { source_group_id: 'official_records', label: 'Official records', description: 'Policy, filings, and authoritative publications.', evidence_role: 'authoritative_record', source_ids: ['federal_register', 'sec_edgar'], source_labels: ['Federal Register', 'SEC EDGAR'], access_label: 'Public · no credentials', default_selected: true },
      { source_group_id: 'open_ecosystem', label: 'Open ecosystem', description: 'Research and repository movement.', evidence_role: 'leading_indicator', source_ids: ['arxiv', 'github'], source_labels: ['arXiv', 'GitHub'], access_label: 'Public · optional token', default_selected: true },
    ],
    cadences: [
      { cadence_id: 'daily', label: 'Daily pulse', description: 'A concise daily orientation.' },
      { cadence_id: 'weekly', label: 'Weekly briefing', description: "The week's movement." },
    ],
    default_cadence_id: 'weekly',
    first_value: { completion_label: 'Open my first briefing' },
  }
  const contextManifest = {
    ...resource('context_manifest', 'world-ai-onboarding', 'AI intelligence setup', 'The reviewed first-run profile.'),
    payload: { onboarding_profile: onboardingProfile },
  }
  const marketProfile = {
    ...onboardingProfile,
    contract: 'ace.intelligence.onboarding-profile/v1alpha1',
    profile_id: 'onboarding_profile:market-intelligence',
    topic_id: 'market_intelligence',
    domain_label: 'Marketing Intelligence',
    topic_label: 'Your market and competitors',
    display_name: 'Marketing Intelligence Command Center',
    description: 'Understand markets, competitors, customers, products, and go-to-market movement.',
    starter_prompts: ['Keep me ahead of competitor, customer, product, and market shifts.'],
  }
  const marketProfileResource = {
    ...resource('builder_profile', 'market-intelligence', 'Marketing Intelligence', 'A governed commercial starting point.'),
    payload: {
      contract: 'ace.intelligence.canonical-json-value/v1alpha1',
      value_json: JSON.stringify(marketProfile),
    },
  }
  await page.route('**/auth/token', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: 'test-token' }) }),
  )
  await page.route('**/v1/intelligence/resources/query', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contract: 'ace.intelligence.resource-plane-page/v1alpha1',
        query_id: 'resource_query:empty',
        query_digest: `sha256:${'d'.repeat(64)}`,
        product_id: 'product:world-ai-command-center',
        actor_ref: 'principal:demo-analyst',
        as_of: availableAt,
        available_at: availableAt,
        evaluated_at: availableAt,
        state: 'complete',
        items: [contextManifest, marketProfileResource],
        next_cursor: null,
        degraded_reason_refs: [],
        page_id: 'resource_page:empty',
        page_digest: `sha256:${'e'.repeat(64)}`,
      }),
    }),
  )
  let buildStartRequests = 0
  let prepareRequests = 0
  await page.route('**/v1/intelligence/builds/prepare', async (route) => {
    prepareRequests += 1
    const body = route.request().postDataJSON() as Record<string, unknown>
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(exactPreparedPlan(body)) })
  })
  await page.route('**/v1/intelligence/builds/start', (route) => {
    buildStartRequests += 1
    return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Custom execution must not be called.' }) })
  })

  await page.goto('/atrium')
  await expect(page.getByRole('heading', { name: 'What do you need to stay ahead of?' })).toBeVisible()
  await page.getByRole('button', { name: 'Build my intelligence' }).click()

  await expect(page.getByRole('heading', { name: 'What kind of intelligence do you want to build?' })).toBeVisible()
  await expect(page.getByRole('button', { name: /World Intelligence/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Marketing Intelligence/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Custom Intelligence/ })).toBeVisible()
  await page.getByRole('button', { name: /World Intelligence/ }).click()
  await page.getByRole('button', { name: 'Use this intelligence' }).click()
  await page.getByRole('button', { name: 'Choose evidence' }).click()
  await page.getByRole('button', { name: 'Prepare exact plan' }).click()
  await expect(page.getByText('Exact proposal', { exact: true })).toBeVisible()
  await expect(page.getByText('Prepared for review—not connected or activated')).toBeVisible()
  await expect(page.getByText('Federal Register', { exact: true })).toBeVisible()
  await expect(page.getByText('directive_issued → implementation_reported')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Activation unavailable' })).toBeDisabled()
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-exact-plan-review.png'), fullPage: true })
    await page.getByRole('heading', { name: 'What would happen next' }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: testInfo.outputPath('atrium-exact-plan-effects.png'), fullPage: true })
  }
  expect(prepareRequests).toBe(1)
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Build my intelligence' }).click()
  await page.getByRole('button', { name: /Custom Intelligence/ }).click()
  await expect(page.getByText('Custom Intelligence is a proposal preview.')).toBeVisible()
  await expect(page.getByText(/does not run a Custom first-Brief executor/)).toBeVisible()
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-custom-preview-choice.png'), fullPage: true })
  }
  await expect(page.getByLabel('Step 1 of 5: Choose')).toBeVisible()
  await page.getByRole('button', { name: 'Preview this intelligence' }).click()
  await expect(page.getByRole('heading', { name: 'What do you need to stay ahead of?' })).toBeVisible()
  await page.getByRole('button', { name: 'Choose evidence' }).click()
  await expect(page.getByRole('heading', { name: 'Choose the evidence ACE can use' })).toBeVisible()
  await page.getByRole('button', { name: 'Review the plan' }).click()
  await expect(page.getByRole('heading', { name: 'Review what ACE will build' })).toBeVisible()
  await expect(page.getByText('Nothing is connected or activated silently.')).toBeVisible()
  await expect(page.getByText('Draft proposal only')).toBeVisible()
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-custom-preview-review.png'), fullPage: true })
  }
  await page.getByRole('button', { name: 'View draft proposal' }).click()
  await expect(page.getByLabel('Step 5 of 5: Preview')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Your Custom proposal is ready' })).toBeVisible()
  await expect(page.getByText('Not supported for Custom Intelligence in v1')).toBeVisible()
  await expect(page.getByText('Preview complete · No runtime execution performed')).toBeVisible()
  expect(buildStartRequests).toBe(0)
  expect(prepareRequests).toBe(1)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-custom-preview-complete.png'), fullPage: true })
  }
  await page.getByRole('button', { name: 'Return to Atrium' }).click()
  await expect(page.getByRole('dialog')).not.toBeVisible()
})

test('Atrium renders a durable first-brief-ready Builder session instead of simulated progress', async ({ page }, testInfo) => {
  const onboardingProfile = {
    contract: 'ace.intelligence.onboarding-profile/v1alpha1',
    profile_id: 'intelligence_onboarding_profile:world-ai-command-center',
    profile_digest: `sha256:${'8'.repeat(64)}`,
    topic_id: 'artificial_intelligence',
    domain_label: 'World Intelligence',
    topic_label: 'Artificial intelligence',
    display_name: 'AI Command Center',
    prompt: 'What do you need to stay ahead of?',
    description: 'Build an evidence-grounded picture of the AI landscape.',
    starter_prompts: ['Keep me ahead of material AI policy, capability, and adoption changes.'],
    outcomes: [{
      outcome_id: 'strategy',
      label: 'Set strategy or evaluate investments',
      description: 'Track material AI movement.',
      icon_hint: 'strategy',
      recommended_topic_labels: ['Policy', 'Models'],
      recommended_intelligence_labels: ['Policy progression'],
    }],
    source_groups: [{
      source_group_id: 'official_records',
      label: 'Official records',
      description: 'Primary policy evidence.',
      evidence_role: 'authoritative_record',
      source_ids: ['federal_register', 'white_house'],
      source_labels: ['Federal Register', 'White House'],
      access_label: 'Public · no credentials',
      default_selected: true,
    }],
    cadences: [{ cadence_id: 'daily', label: 'Daily pulse', description: 'A concise daily orientation.' }],
    default_cadence_id: 'daily',
    first_value: { completion_label: 'Open my first briefing' },
  }
  const profileResource = {
    ...resource('builder_profile', 'world-ai-command-center', 'AI Command Center', 'The admitted starting profile.'),
    payload: {
      contract: 'ace.intelligence.canonical-json-value/v1alpha1',
      value_json: JSON.stringify(onboardingProfile),
    },
  }
  const sessionStages = [
    'goal_selected',
    'sources_connecting',
    'sources_ready',
    'concept_model_proposed',
    'concept_model_approved',
    'intelligence_model_proposed',
    'intelligence_model_approved',
    'first_briefing_ready',
  ]
  const sessions = sessionStages.map((stage, index) => {
    const item = resource('builder_session', `world-ai-${index + 1}`, `Builder stage ${index + 1}`, stage)
    return {
      ...item,
      reference: {
        ...item.reference,
        resource_id: 'intelligence_builder_session:world-ai',
        revision: index + 1,
        available_at: `2026-08-12T18:00:0${index + 1}.000Z`,
      },
      payload: {
        contract: 'ace.intelligence.canonical-json-value/v1alpha1',
        value_json: JSON.stringify({
          contract: 'ace.application.intelligence-builder-session-revision/v1alpha1',
          session_id: 'intelligence_builder_session:world-ai',
          goal_ref: 'goal:track-ai-change',
          sequence: index + 1,
          stage,
          artifacts: stage === 'first_briefing_ready' ? [{
            artifact_kind: 'first_briefing_preview',
            artifact_id: 'first_briefing_preview:world-ai',
            artifact_digest: `sha256:${'f'.repeat(64)}`,
          }] : [],
          block_reason: null,
          resume_stage: null,
          safe_diagnostic: null,
        }),
      },
    }
  })
  const brief = resource(
    'brief',
    'world-ai-first',
    'AI policy moved from directive to reported implementation',
    'Two admitted official lineages show a material policy progression.',
  )

  await page.route('**/auth/token', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: 'test-token' }) }),
  )
  await page.route('**/v1/intelligence/resources/query', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contract: 'ace.intelligence.resource-plane-page/v1alpha1',
        query_id: 'resource_query:live-builder',
        query_digest: `sha256:${'1'.repeat(64)}`,
        product_id: 'product:world-ai-command-center',
        actor_ref: 'principal:demo-analyst',
        as_of: availableAt,
        available_at: availableAt,
        evaluated_at: availableAt,
        state: 'complete',
        items: [profileResource, ...sessions, brief],
        next_cursor: null,
        degraded_reason_refs: [],
        page_id: 'resource_page:live-builder',
        page_digest: `sha256:${'2'.repeat(64)}`,
      }),
    }),
  )
  await page.route('**/v1/intelligence/builds/prepare', async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(exactPreparedPlan(body)),
    })
  })

  await page.goto('/atrium')
  await page.getByRole('button', { name: 'View build' }).click()
  await page.getByRole('button', { name: 'Use this intelligence' }).click()
  await page.getByRole('button', { name: 'Choose evidence' }).click()
  await page.getByRole('button', { name: 'Prepare exact plan' }).click()
  await expect(page.getByText('Exact proposal', { exact: true })).toBeVisible()
  await expect(page.getByText('directive_issued → implementation_reported')).toBeVisible()
  await page.getByRole('button', { name: 'View live build' }).click()
  await expect(page.getByRole('heading', { name: 'Your first picture is ready' })).toBeVisible()
  await expect(page.getByText('Complete', { exact: true })).toHaveCount(4)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-live-builder-ready.png'), fullPage: true })
  }
  await page.getByRole('button', { name: 'Open my first briefing' }).click()
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(page.getByRole('button', { name: `Open ${brief.title}` })).toBeVisible()
})
