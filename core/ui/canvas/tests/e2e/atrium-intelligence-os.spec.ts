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
  const packReference = {
    pack_id: 'world-ai',
    pack_version: '1.0.0',
    compiled_pack_id: `pack_ir:${'2'.repeat(32)}`,
    pack_digest: `sha256:${'2'.repeat(64)}`,
  }
  return {
    contract: 'ace.application.intelligence-build-plan/v1alpha3',
    request: {
      ...body,
      contract: 'ace.application.intelligence-build-plan-request/v1alpha2',
      product_id: 'product:world-ai-command-center',
      actor_ref: 'principal:local-owner',
      request_id: 'intelligence_build_plan_request:world-ai',
      request_digest: `sha256:${'4'.repeat(64)}`,
    },
    pack_reference: packReference,
    activation_proposal: {
      contract: 'ace.application.intelligence-build-activation-proposal/v1alpha1',
      product_id: 'product:world-ai-command-center',
      activation_key: 'world-ai',
      pack: packReference,
      overlay: {},
      capability_requirement_ids: ['public-record-reader'],
      authority_request_ids: ['public-record-read'],
      proposal_id: 'intelligence_build_activation_proposal:world-ai',
      proposal_digest: `sha256:${'1'.repeat(64)}`,
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

function exactSystemProjection(plan: ReturnType<typeof exactPreparedPlan>) {
  const unsupported = (reason: string) => ({ support: 'unsupported', value: null, basis: [], reason })
  const stages = [
    'blueprint_generated', 'review', 'permissions_validated', 'source_readiness_validated',
    'evidence_admitted', 'model_initialized', 'first_intelligence_validated', 'maintenance_activated',
  ]
  const dimensions = [
    'coverage', 'freshness', 'confidence', 'conflicts', 'resolution', 'source_health', 'maintenance_health', 'historical_depth',
  ]
  const elements = [
    ['entity', 'ai-policy-action', 'AI policy action'],
    ['event', 'policy-progression', 'Policy progression'],
    ['signal', 'policy-implementation-signal', 'Policy implementation signal'],
    ['question', 'decision-readiness', 'Set strategy or evaluate investments'],
    ['update', 'daily-pulse', 'Daily pulse'],
    ['output', 'first-brief', 'First cited Brief'],
  ].map(([kind, id, label]) => ({
    kind,
    element_id: id,
    element_ref: `blueprint_element:${kind}:${id}`,
    label,
    rationale: `The exact installed Pack declares this ${kind} for the requested domain.`,
    source_material: [],
    confidence: unsupported('Blueprint confidence is not contracted.'),
  }))
  const bindingId = 'source_binding:exact-federal-register'
  return {
    contract: 'ace.intelligence.system-projection/v1alpha1',
    product_id: plan.request.product_id,
    mode: 'proposed',
    plan: {}, request: {}, pack: {},
    blueprint: {
      plan: {}, request: {}, pack: {}, subject: plan.request.subject, elements, gaps: [],
      blueprint_id: 'generated_blueprint:exact', blueprint_digest: `sha256:${'7'.repeat(64)}`,
    },
    changes: elements.map((element, index) => ({
      operation: 'add', target_ref: element.element_ref, before: null, after: {},
      rationale: 'Add this exact proposed blueprint element.',
      expected_effect: unsupported('No prior accepted blueprint revision exists.'), requires_review: true,
      change_id: `projection_change:${index}`, change_digest: `sha256:${String(index).repeat(64).slice(0, 64)}`,
    })),
    source_bindings: [{
      binding_id: bindingId, selection: {}, source_group_id: 'official_records', label: 'Federal Register',
      evidence_role: 'authoritative_record', source_definition_ref: 'recorded_source_definition:federal-register',
      source_type_ref: 'source_type:public-record', source_uri: 'https://www.federalregister.gov/',
      mapping_id: 'policy-record', subject_binding_id: 'world-ai', entity_type_id: 'ai_policy_action',
      entity_ref: 'entity:executive-order-14409', access_requirement_label: 'Public · no credentials',
      binding_state: 'proposed', permission_state: 'not_evaluated', readiness_state: 'not_evaluated',
      capability_requirement_ids: [], authority_request_ids: [],
      requirements: { support: 'unsupported', basis: [], reason: 'Per-binding requirements are not contracted.' },
    }],
    unassigned_capability_requirement_ids: [], unassigned_authority_request_ids: [],
    coverage: elements.filter((element) => ['entity', 'event', 'signal'].includes(element.kind)).map((element) => ({
      dimension: element.kind, target_ref: element.element_ref, target_label: element.label,
      source_binding_ids: [bindingId], predicted: unsupported('No estimator is bound.'),
      observed: unsupported('No runtime evidence is admitted.'),
    })),
    initialization: stages.map((stage, index) => ({
      sequence: index + 1, stage, state: index === 0 ? 'complete' : index === 1 ? 'in_progress' : 'pending',
      detail: index === 0 ? 'Generated from exact installed material.' : 'Awaiting the preceding governed stage.', basis: [],
    })),
    derivations: { availability: { support: 'unsupported', basis: [], reason: 'No live conclusion exists.' }, items: [] },
    domain_health: dimensions.map((dimension) => ({ dimension, value: unsupported(`${dimension} is unavailable at proposal time.`) })),
    generated_at: availableAt, gaps: [], projection_id: 'intelligence_system_projection:exact',
    projection_digest: `sha256:${'8'.repeat(64)}`,
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
  await page.route('**/v1/intelligence/catalog/packs', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contract: 'ace.http.installed-domain-pack-catalog/v1alpha1',
        packs: [{
          distribution: 'ace-ext-world-intelligence',
          distribution_version: '1.4.0',
          manifest_resource_path: 'domain-pack.json',
          manifest_digest: `sha256:${'d'.repeat(64)}`,
          manifest: {
            contract: 'ace.intelligence.domain-pack-manifest/v1alpha1',
            metadata: {
              pack_id: 'world-intelligence', version: '1.4.0', display_name: 'World Intelligence',
              description: 'A maintained operating model for material world events, signals, and evidence.',
            },
            resources: [{ resource_id: 'world-ontology', path: 'ontology.json', digest: `sha256:${'e'.repeat(64)}` }],
            modules: [{ module_id: 'world-model', contract: 'ace.intelligence.ontology-module/v1alpha1', resource_id: 'world-ontology', depends_on: [] }],
            capability_requirements: [{ requirement_id: 'public-record-reader', capability: 'source_snapshot', contract: 'ace.source.snapshot/v1' }],
            authority_requests: [{ request_id: 'public-record-read', authority: 'source_read' }],
            overlay_slots: [{ slot_id: 'watch-cadence', value_kind: 'duration', required: false }],
          },
          lifecycle: [
            { capability_id: 'installed_material', label: 'Installed material', availability: 'available', contract_refs: [], endpoint: 'GET /v1/intelligence/catalog/packs', boundary: 'This exact validated manifest is installed; it grants no activation authority.' },
            { capability_id: 'reviewed_customization', label: 'Local customization', availability: 'contract_only', contract_refs: ['ace.intelligence.organization-overlay/v1alpha1'], endpoint: null, boundary: 'Declared overlay slots exist; no active product overlay is inferred.' },
            { capability_id: 'upgrade_discovery', label: 'Upgrade', availability: 'not_exposed', contract_refs: [], endpoint: null, boundary: 'No compatible newer release is claimed.' },
            { capability_id: 'activation_history', label: 'Version history', availability: 'contract_only', contract_refs: ['ace.intelligence.domain-activation-revision/v1alpha1'], endpoint: null, boundary: 'Append-only revisions exist without a customer history endpoint.' },
            { capability_id: 'rollback', label: 'Rollback', availability: 'contract_only', contract_refs: ['ace.intelligence.domain-activation-revision/v1alpha1'], endpoint: null, boundary: 'Rollback requires a new approved revision; no customer action is exposed.' },
          ],
        }],
      }),
    }),
  )
  await page.route('**/v1/intelligence/catalog/consumers', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contract: 'ace.http.intelligence-consumer-catalog/v1alpha1',
        interfaces: [
          { interface_id: 'intelligence_resource_http', label: 'Intelligence Resource API', kind: 'api', availability: 'available', version: 'v1', endpoint: 'POST /v1/intelligence/resources/query', contract_refs: ['ace.intelligence.resource-plane-record/v1alpha1'], operations: ['point-in-time query'], permission_boundary: 'Every query reauthorizes product scope.', provenance_boundary: 'Every record carries an exact resource reference and upstream provenance.', delivery_boundary: 'Authenticated point-in-time JSON pages only.' },
          { interface_id: 'intelligence_subscription', label: 'Intelligence subscription', kind: 'subscription', availability: 'contract_only', version: null, endpoint: null, contract_refs: ['ace.intelligence.subscription/v1alpha1'], operations: ['digest'], permission_boundary: 'A subscription is not an API credential.', provenance_boundary: 'Delivery provenance is not exposed.', delivery_boundary: 'No customer-facing delivery endpoint is exposed.' },
        ],
        unresolved_dependencies: ['A required downstream provenance-return envelope.'],
      }),
    }),
  )

  await page.setViewportSize({ width: 1440, height: 960 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/atrium')
  await expect(page.locator('.atrium-maintenance-weave path').first()).toHaveCSS('animation-name', 'none')
  expect(await page.getByRole('link', { name: 'Skip to intelligence' }).evaluate((link) => (
    Number.parseFloat(getComputedStyle(link).transitionDuration)
  ))).toBeLessThan(0.001)
  await page.emulateMedia({ reducedMotion: 'no-preference' })

  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to intelligence' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.locator('#atrium-main')).toBeFocused()

  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
  await expect(page).toHaveTitle('Overview — ACE')
  await expect(page.getByRole('link', { name: 'Overview', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('link', { name: 'ACE Intelligence OS overview' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Refresh intelligence' })).toHaveAttribute('aria-busy', 'false')
  await expect(page.locator('svg.lucide-shield-check')).toHaveCount(1)
  await expect(page.getByRole('heading', { name: 'AI Command Brief — capability up, unit cost down' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Explore', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Build', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Operate', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Consumers', exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Domain Health' })).toContainText('Not measured')

  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-living-brief-overview.png') })
  }

  await page.goto('/atrium/build')
  await expect(page.getByRole('heading', { name: 'Build' })).toBeVisible()
  await expect(page).toHaveTitle('Build — ACE')
  await expect(page.getByRole('link', { name: 'Build', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('link', { name: 'Overview', exact: true })).not.toHaveAttribute('aria-current', 'page')
  await expect(page.getByText('Maintenance model', { exact: true })).toBeVisible()
  await expect(page.getByText('Source model', { exact: true })).toBeVisible()
  await expect(page.getByText('Available', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('World Intelligence', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Custom Intelligence', { exact: true })).toBeVisible()
  await page.getByText('Install, customize, upgrade, history, and rollback').click()
  await expect(page.getByRole('list', { name: 'World Intelligence lifecycle · defined' })).toContainText('Defined')
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-build.png'), fullPage: true })
  }

  await page.goto('/atrium/operate')
  await expect(page.getByRole('heading', { name: 'Operate' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Domain Health' })).toContainText('Historical depth')
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-operate.png') })
  }

  await page.goto('/atrium/consumers')
  await expect(page.getByRole('heading', { name: 'Consumers' })).toBeVisible()
  await expect(page.getByText('Intelligence Resource API')).toBeVisible()
  await expect(page.getByText(/consumer subscription is not an API credential/)).toBeVisible()
  await expect(page.getByText('Refresh the AI economic model')).toBeVisible()
  await expect(page.getByText('What changed', { exact: true })).toHaveCount(0)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-consumers.png') })
  }
  await page.goto('/atrium')

  await page.getByRole('link', { name: 'Explore', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Explore' })).toBeVisible()
  await expect(page.getByText('governed sources', { exact: true }).locator('svg.lucide-book-open-check')).toHaveCount(1)

  await page.getByLabel('Ask ACE about current intelligence').fill('What changed in token economics?')
  await page.getByLabel('Ask ACE', { exact: true }).click()
  const askAceAnswer = page.getByRole('region', { name: 'Ask ACE answer' })
  await expect(askAceAnswer.getByText('Published token prices fell while long-context tiers expanded across two providers.').first()).toBeVisible()
  await expect(askAceAnswer.getByText('Why it matters', { exact: true })).toBeVisible()
  await expect(askAceAnswer.getByText('Evidence used', { exact: true })).toBeVisible()
  await expect(askAceAnswer.getByText('Frontier inference costs moved down again')).toBeVisible()
  await expect(askAceAnswer.getByText(/cited record/)).toBeVisible()
  const resultSummary = page.getByRole('complementary', { name: 'Explore result summary' })
  await expect(resultSummary).toContainText('Shifts')
  await expect(resultSummary.getByRole('button')).toHaveCount(0)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-explore-answer.png'), fullPage: true })
  }

  const openWhy = page.getByRole('button', { name: /Open Why/ }).first()
  await openWhy.click()
  const whySheet = page.getByRole('dialog')
  await expect(whySheet).toHaveCSS('color', 'rgb(244, 243, 239)')
  await expect(whySheet).toHaveCSS('background-color', 'rgb(18, 20, 22)')
  await expect(whySheet).toHaveCSS('opacity', '1')
  await expect(page.getByRole('list', { name: 'Evidence-to-conclusion derivation' })).toBeVisible()
  await expect(page.getByText('Supporting evidence', { exact: true })).toBeVisible()
  await expect(page.getByText('Not projected for this assessment')).toBeVisible()
  await expect(page.getByText('Record available', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Open trust layer' })).toBeVisible()
  await page.getByText('Challenge or correct this conclusion').click()
  await expect(whySheet.getByRole('group', { name: 'Supported correction intents' })).toContainText('This claim is outdated')
  const correctionNote = whySheet.getByLabel('What should ACE review?')
  await expect(correctionNote).toBeVisible()
  await expect(whySheet).toContainText('The proposal does not change the record or its downstream effects.')

  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await correctionNote.scrollIntoViewIfNeeded()
    await page.screenshot({ path: testInfo.outputPath('atrium-explore-why.png') })
  }
  await page.keyboard.press('Escape')
  await expect(openWhy).toBeFocused()

  await page.getByRole('link', { name: 'Operate', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Operate' })).toBeVisible()
  const domainHealth = page.getByRole('region', { name: 'Domain Health' })
  await expect(domainHealth).toContainText('Coverage')
  await expect(domainHealth).toContainText('Freshness')
  await expect(domainHealth).toContainText('Confidence')
  await expect(domainHealth).toContainText('Conflicts')
  await expect(domainHealth).toContainText('Resolution')
  await expect(domainHealth).toContainText('Source health')
  await expect(domainHealth).toContainText('Maintenance health')
  await expect(domainHealth).toContainText('Historical depth')

  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.goto('/atrium')
    await page.screenshot({ path: testInfo.outputPath('atrium-living-brief-1280x800.png') })
  }

  await page.setViewportSize({ width: 768, height: 1024 })
  await page.goto('/atrium')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'AI Command Brief — capability up, unit cost down' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Explore', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-living-brief-768x1024.png') })
  }
  await expect(page.getByRole('button', { name: 'Toggle Sidebar' })).toBeVisible()
  await page.getByRole('button', { name: 'Toggle Sidebar' }).click()
  await expect(page.getByText('Consumers', { exact: true })).toBeVisible()

  await page.goto('/atrium/explore')
  await expect(page.getByRole('heading', { name: 'Explore' })).toBeVisible()
  await page.getByLabel('Ask ACE about current intelligence').fill('What changed in token economics?')
  await page.getByLabel('Ask ACE', { exact: true }).click()
  const tabletAskAceAnswer = page.getByRole('region', { name: 'Ask ACE answer' })
  await expect(tabletAskAceAnswer.getByText('Published token prices fell while long-context tiers expanded across two providers.').first()).toBeVisible()
  await expect(tabletAskAceAnswer.getByText('Why it matters', { exact: true })).toBeVisible()
  await expect(tabletAskAceAnswer.getByText('Evidence used', { exact: true })).toBeVisible()
  const tabletResultSummary = page.getByRole('complementary', { name: 'Explore result summary' })
  expect((await tabletResultSummary.boundingBox())?.width).toBeGreaterThan(500)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-explore-answer-768x1024.png'), fullPage: true })
  }

  const tabletOpenWhy = page.getByRole('button', { name: /Open Why/ }).first()
  await tabletOpenWhy.click()
  const tabletWhySheet = page.getByRole('dialog')
  await expect(tabletWhySheet).toBeVisible()
  await expect(tabletWhySheet).toHaveCSS('background-color', 'rgb(18, 20, 22)')
  await expect(tabletWhySheet).toHaveCSS('opacity', '1')
  await expect(page.getByRole('list', { name: 'Evidence-to-conclusion derivation' })).toBeVisible()
  await expect(page.getByText('Supporting evidence', { exact: true })).toBeVisible()
  expect((await tabletWhySheet.boundingBox())?.width).toBeGreaterThan(480)
  expect(await tabletWhySheet.evaluate((sheet) => sheet.scrollWidth <= sheet.clientWidth)).toBe(true)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-explore-why-768x1024.png'), animations: 'disabled' })
  }
  await page.keyboard.press('Escape')
  await expect(tabletOpenWhy).toBeFocused()

  await page.getByRole('link', { name: 'Operate', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Operate' })).toBeVisible()
  expect(await page.evaluate(() => window.scrollY)).toBe(0)
  const tabletDomainHealth = page.getByRole('region', { name: 'Domain Health' })
  await expect(tabletDomainHealth).toContainText('Coverage')
  await expect(tabletDomainHealth).toContainText('Freshness')
  await expect(tabletDomainHealth).toContainText('Confidence')
  await expect(tabletDomainHealth).toContainText('Conflicts')
  await expect(tabletDomainHealth).toContainText('Resolution')
  await expect(tabletDomainHealth).toContainText('Source health')
  await expect(tabletDomainHealth).toContainText('Maintenance health')
  await expect(tabletDomainHealth).toContainText('Historical depth')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-operate-768x1024.png') })
  }

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/atrium')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-living-brief-narrow.png') })
  }
  await page.getByRole('button', { name: 'Toggle Sidebar' }).click()
  await expect(page.getByText('Consumers', { exact: true })).toBeVisible()

  await page.goto('/atrium/explore')
  await page.getByLabel('Ask ACE about current intelligence').fill('What changed in token economics?')
  await page.getByLabel('Ask ACE', { exact: true }).click()
  await expect(page.getByRole('region', { name: 'Ask ACE answer' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-explore-answer-narrow.png') })
  }
  const narrowOpenWhy = page.getByRole('button', { name: /Open Why/ }).first()
  await narrowOpenWhy.click()
  const narrowWhySheet = page.getByRole('dialog')
  await expect(narrowWhySheet).toBeVisible()
  await expect(narrowWhySheet).toHaveCSS('background-color', 'rgb(18, 20, 22)')
  await expect(narrowWhySheet).toHaveCSS('opacity', '1')
  expect((await narrowWhySheet.boundingBox())?.width).toBeGreaterThan(380)
  expect(await narrowWhySheet.evaluate((sheet) => sheet.scrollWidth <= sheet.clientWidth)).toBe(true)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await narrowWhySheet.evaluate((sheet) => { sheet.scrollTop = 0 })
    await page.screenshot({ path: testInfo.outputPath('atrium-explore-why-narrow.png'), animations: 'disabled' })
  }
  await page.keyboard.press('Escape')
  await expect(narrowOpenWhy).toBeFocused()

  for (const [route, heading] of [
    ['/atrium/build', 'Build'],
    ['/atrium/operate', 'Operate'],
    ['/atrium/consumers', 'Consumers'],
  ] as const) {
    await page.goto(route)
    await expect(page.getByRole('heading', { name: heading })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }

  await page.setViewportSize({ width: 768, height: 1024 })
  await page.goto('/atrium/build')
  await expect(page.getByRole('heading', { name: 'Build' })).toBeVisible()
  await page.getByText('Install, customize, upgrade, history, and rollback').click()
  await expect(page.getByRole('list', { name: 'World Intelligence lifecycle · defined' })).toContainText('Defined')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: 'auto' }))
    await page.screenshot({ path: testInfo.outputPath('atrium-build-768x1024.png'), fullPage: true })
  }
  await page.goto('/atrium/consumers')
  await expect(page.getByRole('heading', { name: 'Consumers' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-consumers-768x1024.png') })
  }

  for (const [legacyPath, canonicalPath] of [
    ['/atrium/intelligence', '/atrium'],
    ['/atrium/opportunities', '/atrium'],
    ['/atrium/agents', '/atrium/build'],
    ['/atrium/connections', '/atrium/operate'],
    ['/atrium/strategy', '/atrium/consumers'],
  ] as const) {
    await page.goto(legacyPath, { waitUntil: 'commit' })
    await expect(page).toHaveURL(canonicalPath)
  }
})

test('Atrium keeps a degraded intelligence picture usable and explicit', async ({ page }, testInfo) => {
  const source = resource(
    'source',
    'delayed-policy-feed',
    'Delayed policy record feed',
    'The admitted policy feed is available, but its latest update is delayed.',
  )
  source.availability = 'degraded'
  source.degraded_reason_refs = ['source_health:policy-feed-delayed']
  const brief = resource(
    'brief',
    'policy-watch',
    'AI policy watch — current evidence is partial',
    'ACE preserved the latest cited policy picture while one admitted source awaits a fresher update.',
    [source.reference],
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
        query_id: 'resource_query:degraded',
        query_digest: `sha256:${'8'.repeat(64)}`,
        product_id: 'product:ai-policy-watch',
        actor_ref: 'principal:demo-analyst',
        as_of: availableAt,
        available_at: availableAt,
        evaluated_at: availableAt,
        state: 'degraded',
        items: [source, brief],
        next_cursor: null,
        degraded_reason_refs: ['source_health:policy-feed-delayed'],
        page_id: 'resource_page:degraded',
        page_digest: `sha256:${'9'.repeat(64)}`,
      }),
    }),
  )

  await page.setViewportSize({ width: 1440, height: 960 })
  await page.goto('/atrium')
  await expect(page.getByText('Partial picture', { exact: true })).toBeVisible()
  await expect(page.getByText('Some evidence still needs review')).toBeVisible()
  await expect(page.getByText('1 cited record is marked degraded.')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'AI policy watch — current evidence is partial' })).toBeVisible()
  await expect(page.getByText('Unknown · explicit')).toBeVisible()
  await expect(page.getByText('Delayed policy record feed')).toBeVisible()
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-degraded-overview.png') })
  }

  await page.goto('/atrium/operate')
  await expect(page.getByText('Degraded', { exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Domain Health' })).toContainText('Maintained with limits')
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.evaluate(() => {
      window.scrollTo(0, 0)
      for (const element of document.querySelectorAll<HTMLElement>('[data-slot="sidebar-content"]')) {
        element.scrollTop = 0
      }
    })
    await page.screenshot({ path: testInfo.outputPath('atrium-degraded-operate.png') })
  }

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/atrium')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('Atrium distinguishes an unavailable picture from an empty domain and recovers', async ({ page }, testInfo) => {
  const source = resource(
    'source',
    'recovered-source',
    'Recovered source',
    'The admitted source returned after the resource request recovered.',
  )
  const brief = resource(
    'brief',
    'recovered-brief',
    'Recovered intelligence picture',
    'ACE restored the cited picture after the resource request succeeded.',
    [source.reference],
  )
  let queryCount = 0
  let recover = false

  await page.route('**/auth/token', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: 'test-token' }) }),
  )
  await page.route('**/v1/intelligence/resources/query', (route) => {
    queryCount += 1
    if (!recover) {
      return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Resource plane unavailable.' }) })
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contract: 'ace.intelligence.resource-plane-page/v1alpha1',
        query_id: 'resource_query:recovered',
        query_digest: `sha256:${'a'.repeat(64)}`,
        product_id: 'product:recovered-picture',
        actor_ref: 'principal:demo-analyst',
        as_of: availableAt,
        available_at: availableAt,
        evaluated_at: availableAt,
        state: 'complete',
        items: [source, brief],
        next_cursor: null,
        degraded_reason_refs: [],
        page_id: 'resource_page:recovered',
        page_digest: `sha256:${'b'.repeat(64)}`,
      }),
    })
  })

  await page.setViewportSize({ width: 1440, height: 960 })
  await page.goto('/atrium')
  await expect(page.getByText('ACE could not open this intelligence view')).toBeVisible()
  await expect(page.getByRole('region', { name: 'Unavailable intelligence' })).toBeVisible()
  await expect(page.getByText('No intelligence picture is available in this view.')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'What should ACE understand?' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Propose my intelligence system' })).toHaveCount(0)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.evaluate(() => {
      window.scrollTo(0, 0)
      for (const element of document.querySelectorAll<HTMLElement>('[data-slot="sidebar-content"]')) {
        element.scrollTop = 0
      }
    })
    await page.screenshot({ path: testInfo.outputPath('atrium-unavailable.png') })
  }

  recover = true
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('heading', { name: 'Recovered intelligence picture' })).toBeVisible()
  await expect(page.getByText('ACE could not open this intelligence view')).toHaveCount(0)
  expect(queryCount).toBeGreaterThan(1)
})

test('Atrium loading state preserves the Living Brief hierarchy', async ({ page }, testInfo) => {
  let releaseQuery = () => {}
  const queryGate = new Promise<void>((resolve) => {
    releaseQuery = resolve
  })

  await page.route('**/auth/token', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: 'test-token' }) }),
  )
  await page.route('**/v1/intelligence/resources/query', async (route) => {
    await queryGate
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contract: 'ace.intelligence.resource-plane-page/v1alpha1',
        query_id: 'resource_query:empty-after-load',
        query_digest: `sha256:${'c'.repeat(64)}`,
        product_id: 'product:loading-test',
        actor_ref: 'principal:demo-analyst',
        as_of: availableAt,
        available_at: availableAt,
        evaluated_at: availableAt,
        state: 'complete',
        items: [],
        next_cursor: null,
        degraded_reason_refs: [],
        page_id: 'resource_page:empty-after-load',
        page_digest: `sha256:${'d'.repeat(64)}`,
      }),
    })
  })

  await page.setViewportSize({ width: 1440, height: 960 })
  await page.goto('/atrium')
  await expect(page.getByRole('status', { name: 'Loading intelligence' })).toBeVisible()
  await expect(page.getByText('Loading cited records', { exact: true })).toBeVisible()
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.evaluate(() => {
      window.scrollTo(0, 0)
      for (const element of document.querySelectorAll<HTMLElement>('[data-slot="sidebar-content"]')) {
        element.scrollTop = 0
      }
    })
    await page.screenshot({ path: testInfo.outputPath('atrium-loading.png') })
  }

  releaseQuery()
  await expect(page.getByRole('status', { name: 'Loading intelligence' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'What should ACE understand?' })).toBeVisible()
})

test('Atrium labels retained intelligence honestly when a refresh fails', async ({ page }, testInfo) => {
  const brief = resource(
    'brief',
    'retained-intelligence',
    'Enterprise AI economics remain the material planning constraint',
    'ACE retained the last successfully loaded cited picture after a refresh could not complete.',
  )
  let failRefresh = false

  await page.route('**/auth/token', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: 'test-token' }) }),
  )
  await page.route('**/v1/intelligence/resources/query', async (route) => {
    if (failRefresh) {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'The admitted source plane did not answer the refresh.' }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contract: 'ace.intelligence.resource-plane-page/v1alpha1',
        query_id: 'resource_query:retained',
        query_digest: `sha256:${'4'.repeat(64)}`,
        product_id: 'product:enterprise-ai-economics',
        actor_ref: 'principal:demo-analyst',
        as_of: availableAt,
        available_at: availableAt,
        evaluated_at: availableAt,
        state: 'complete',
        items: [brief],
        next_cursor: null,
        degraded_reason_refs: [],
        page_id: 'resource_page:retained',
        page_digest: `sha256:${'5'.repeat(64)}`,
      }),
    })
  })

  await page.setViewportSize({ width: 1440, height: 960 })
  await page.goto('/atrium')
  await expect(page.getByText('Picture current', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Enterprise AI economics remain the material planning constraint' })).toBeVisible()

  failRefresh = true
  await page.getByRole('button', { name: 'Refresh intelligence' }).click()
  await expect(page.getByText('Last loaded picture', { exact: true })).toBeVisible()
  await expect(page.getByText('ACE could not refresh this intelligence view')).toBeVisible()
  await expect(page.getByText(/The last loaded cited picture remains visible\./)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Enterprise AI economics remain the material planning constraint' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Unavailable intelligence' })).toHaveCount(0)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.evaluate(() => {
      window.scrollTo(0, 0)
      for (const element of document.querySelectorAll<HTMLElement>('[data-slot="sidebar-content"]')) {
        element.scrollTop = 0
      }
    })
    await page.screenshot({ path: testInfo.outputPath('atrium-refresh-failed.png') })
  }

  failRefresh = false
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByText('Picture current', { exact: true })).toBeVisible()
  await expect(page.getByText('ACE could not refresh this intelligence view')).toHaveCount(0)
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
  await page.route('**/v1/intelligence/builds/projection', async (route) => {
    const body = route.request().postDataJSON() as { plan: ReturnType<typeof exactPreparedPlan> }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(exactSystemProjection(body.plan)) })
  })
  await page.route('**/v1/intelligence/builds/start', (route) => {
    buildStartRequests += 1
    return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Custom execution must not be called.' }) })
  })

  await page.setViewportSize({ width: 1440, height: 960 })
  await page.goto('/atrium')
  await expect(page.getByRole('heading', { name: 'What should ACE understand?' })).toBeVisible()
  await page.getByRole('button', { name: 'Propose my intelligence system' }).click()

  await expect(page.getByRole('heading', { name: 'What kind of intelligence do you want to build?' })).toBeVisible()
  await expect(page.getByRole('button', { name: /World Intelligence/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Marketing Intelligence/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Custom Intelligence/ })).toBeVisible()
  await expect(page.locator('[aria-current="step"]')).toContainText('Choose')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('dialog')).toHaveCount(1)
  expect(await page.evaluate(() => document.querySelector('[role="dialog"]')?.contains(document.activeElement))).toBe(true)
  await page.getByRole('button', { name: /World Intelligence/ }).click()
  await expect(page.getByRole('button', { name: /World Intelligence/ })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'Use this intelligence' }).click()
  await expect(page.getByRole('complementary', { name: 'Build context' })).toContainText('Authority not granted')
  await expect(page.getByRole('complementary', { name: 'Build context' })).toContainText('Predicted coverage')
  await page.getByRole('button', { name: 'Choose evidence' }).click()
  await page.getByRole('button', { name: 'Prepare exact plan' }).click()
  await expect(page.getByText('Exact proposal', { exact: true })).toBeVisible()
  await expect(page.getByText('Prepared for review—not connected or activated')).toBeVisible()
  await expect(page.getByRole('list', { name: 'Exact source bindings' }).getByText('Federal Register', { exact: true })).toBeVisible()
  await expect(page.getByText('directive_issued → implementation_reported')).toBeVisible()
  await expect(page.getByRole('list', { name: 'Exact source bindings' })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Reviewable proposed effects' })).toContainText('Rationale')
  await expect(page.getByRole('list', { name: 'Reviewable proposed effects' })).toContainText('Method')
  await expect(page.getByRole('list', { name: 'Reviewable proposed effects' })).toContainText('Timing')
  await expect(page.getByRole('heading', { name: 'Blueprint, bindings, coverage, and readiness' })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Predicted and observed coverage' })).toContainText('Not supported')
  await expect(page.getByRole('list', { name: 'Canonical initialization stages' })).toContainText('in progress')
  await expect(page.getByText('Decision 1 of 2 · Validate inputs')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Approve reviewed plan' })).toBeVisible()
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-exact-plan-review.png'), fullPage: true })
    await page.getByRole('heading', { name: 'Blueprint, bindings, coverage, and readiness' }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: testInfo.outputPath('atrium-canonical-system-projection.png') })
    await page.getByRole('heading', { name: 'What would happen next' }).scrollIntoViewIfNeeded()
    await expect(page.getByRole('list', { name: 'Reviewable proposed effects' })).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('atrium-exact-plan-effects.png') })
    await page.getByRole('heading', { name: 'Checked before ACE touches anything' }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: testInfo.outputPath('atrium-activation-readiness.png') })
    await page.setViewportSize({ width: 768, height: 1024 })
    await page.getByRole('dialog').evaluate((dialog) => {
      dialog.scrollTop = 0
    })
    await page.screenshot({ path: testInfo.outputPath('atrium-exact-plan-review-768x1024.png'), fullPage: true })
    await page.setViewportSize({ width: 1440, height: 960 })
  }
  expect(prepareRequests).toBe(1)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Propose my intelligence system' })).toBeFocused()
  await page.getByRole('button', { name: 'Propose my intelligence system' }).click()
  await page.getByRole('button', { name: /Custom Intelligence/ }).click()
  await expect(page.getByRole('button', { name: /Custom Intelligence/ })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('button', { name: /World Intelligence/ })).toHaveAttribute('aria-pressed', 'false')
  await expect(page.getByText('Custom Intelligence is a proposal preview.')).toBeVisible()
  await expect(page.getByText(/does not run a Custom first-Brief executor/)).toBeVisible()
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    const closeDialog = page.getByRole('button', { name: 'Close' })
    await closeDialog.focus()
    await expect(closeDialog).toBeFocused()
    await page.screenshot({ path: testInfo.outputPath('atrium-custom-preview-choice.png'), fullPage: true, animations: 'disabled' })
  }
  await expect(page.getByLabel('Step 1 of 5: Choose')).toBeVisible()
  await page.getByRole('button', { name: 'Preview this intelligence' }).click()
  await expect(page.getByRole('heading', { name: 'What should ACE understand?' })).toBeVisible()
  await page.getByRole('button', { name: 'Choose evidence' }).click()
  await expect(page.getByRole('heading', { name: 'Choose the evidence ACE can use' })).toBeVisible()
  await page.getByRole('button', { name: 'Review the plan' }).click()
  await expect(page.getByRole('heading', { name: 'Review what ACE will build' })).toBeVisible()
  await expect(page.getByText('Nothing is connected or activated silently.')).toBeVisible()
  await expect(page.getByText('Draft proposal only')).toBeVisible()
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-custom-preview-review.png'), fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('dialog').evaluate((dialog) => {
      dialog.scrollTop = 0
    })
    expect(await page.getByRole('dialog').evaluate((dialog) => dialog.scrollWidth <= dialog.clientWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('atrium-custom-preview-review-narrow.png') })
    await page.setViewportSize({ width: 1440, height: 960 })
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
          product_id: 'product:world-ai-command-center',
          session_id: 'intelligence_builder_session:world-ai',
          correlation_id: 'correlation:world-ai',
          goal_ref: 'goal:track-ai-change',
          sequence: index + 1,
          stage,
          prior_revision_id: index === 0 ? null : `intelligence_builder_session_revision:world-ai-${index}`,
          prior_revision_digest: index === 0 ? null : `sha256:${String(index).repeat(64).slice(0, 64)}`,
          transition_authority: 'core_runtime',
          transition_actor_ref: 'principal:local-owner',
          approval_receipt_ref: null,
          artifacts: stage === 'first_briefing_ready' ? [{
            artifact_kind: 'first_briefing_preview',
            artifact_id: 'first_briefing_preview:world-ai',
            artifact_digest: `sha256:${'f'.repeat(64)}`,
          }] : [],
          block_reason: null,
          resume_stage: null,
          safe_diagnostic: null,
          occurred_at: `2026-08-12T18:00:0${index + 1}.000Z`,
          revision_id: `intelligence_builder_session_revision:world-ai-${index + 1}`,
          revision_digest: `sha256:${String(index + 1).repeat(64).slice(0, 64)}`,
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
  await page.route('**/v1/intelligence/builds/projection', async (route) => {
    const body = route.request().postDataJSON() as { plan: ReturnType<typeof exactPreparedPlan> }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(exactSystemProjection(body.plan)) })
  })

  const exactBriefingReady = JSON.parse(sessions[sessions.length - 1].payload.value_json) as Record<string, unknown>
  const approvedAt = '2026-08-12T18:01:00.000Z'
  const approvalReceiptRef = 'approval:intelligence-activation:world-ai'
  const activationOrder: string[] = []
  const activationRequests: Record<string, Record<string, unknown>> = {}
  let boundPlan: Record<string, unknown> | null = null

  await page.route('**/v1/intelligence/builds/bind', async (route) => {
    activationOrder.push('bind')
    const body = route.request().postDataJSON() as Record<string, unknown>
    activationRequests.bind = body
    boundPlan = {
      contract: 'ace.application.bound-intelligence-build-plan/v1alpha1',
      binding_request: body,
      activation_spec: { spec_id: 'activation_spec:world-ai-reviewed', activation_key: 'world-ai' },
      execution_request_id: 'intelligence_build:world-ai',
      execution_request_digest: `sha256:${'a'.repeat(64)}`,
      bound_plan_id: 'bound_intelligence_build_plan:world-ai',
      bound_plan_digest: `sha256:${'b'.repeat(64)}`,
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(boundPlan) })
  })
  await page.route('**/v1/intelligence/builds/approve', async (route) => {
    activationOrder.push('approve-reviewed-plan')
    const body = route.request().postDataJSON() as Record<string, unknown>
    activationRequests.approveReviewedPlan = body
    const exactBoundPlan = body.bound_plan as Record<string, unknown>
    const bindingRequest = exactBoundPlan.binding_request as Record<string, unknown>
    const plan = bindingRequest.plan as ReturnType<typeof exactPreparedPlan>
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contract: 'ace.http.intelligence-activation-approval-result/v1alpha1',
        approval: {
          receipt_ref: approvalReceiptRef,
          product_id: plan.request.product_id,
          subject_ref: 'activation_spec:world-ai-reviewed',
          actor_ref: plan.request.actor_ref,
          receipt_hash: 'c'.repeat(64),
          approved_at: approvedAt,
        },
        bound_plan_id: exactBoundPlan.bound_plan_id,
        bound_plan_digest: exactBoundPlan.bound_plan_digest,
        start_request: {
          authority_grant_ref: 'authority_grant:atrium-intelligence-build',
          resource_authority_grant_ref: 'authority_grant:atrium-observe-read',
          activation_approval_receipt_ref: approvalReceiptRef,
          activation_approval_subject_ref: 'activation_spec:world-ai-reviewed',
          client_request_id: plan.request.client_request_id,
          profile_id: plan.request.profile_id,
          subject: plan.request.subject,
          outcome_id: plan.request.outcome_id,
          source_group_ids: plan.request.source_group_ids,
          recorded_source_selection_refs: plan.recorded_source_selection_refs,
          cadence_id: plan.request.cadence_id,
          approved_effects: plan.request.proposed_effects,
          requested_at: plan.request.requested_at,
        },
      }),
    })
  })
  await page.route('**/v1/intelligence/builds/activation-plan/prepare', async (route) => {
    activationOrder.push('preview-activation-plan')
    const body = route.request().postDataJSON() as Record<string, unknown>
    activationRequests.previewActivationPlan = body
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contract: 'ace.application.intelligence-activation-plan/v1alpha2',
        action: 'initial_activation',
        onboarding_handoff: { session_id: exactBriefingReady.session_id },
        spec: { spec_id: 'activation_spec:world-ai-reviewed', activation_key: 'world-ai' },
        requested_effects: ['pack_activation'],
        requested_capabilities: [],
        requested_authorities: [],
        created_at: approvedAt,
        plan_id: 'intelligence_activation_plan:world-ai',
        plan_digest: `sha256:${'d'.repeat(64)}`,
      }),
    })
  })
  await page.route('**/v1/intelligence/builds/activation-plan/approve', async (route) => {
    activationOrder.push('approve-activation-plan')
    activationRequests.approveActivationPlan = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contract: 'ace.application.domain-activation-commit-reference/v1alpha2',
        authority_stage: 'historical_reference',
        live_authority: false,
        product_id: 'product:world-ai-command-center',
        activation_key: 'world-ai',
        activation_id: 'domain_activation:world-ai',
        state: 'active',
        plan_id: 'intelligence_activation_plan:world-ai',
        plan_digest: `sha256:${'d'.repeat(64)}`,
        revision: 1,
        revision_id: 'domain_activation_revision:world-ai-1',
        revision_digest: `sha256:${'e'.repeat(64)}`,
        commit_receipt_id: 'domain_activation_commit:world-ai-1',
        commit_receipt_digest: `sha256:${'f'.repeat(64)}`,
        committed_at: approvedAt,
      }),
    })
  })
  await page.route('**/v1/intelligence/builds/activation-plan/activate', async (route) => {
    activationOrder.push('activate-builder-plan')
    activationRequests.activateBuilderPlan = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contract: 'ace.http.intelligence-builder-activation-result/v1alpha1',
        receipt: { session_id: exactBriefingReady.session_id, activated_at: approvedAt },
        replayed: false,
      }),
    })
  })
  await page.route('**/v1/intelligence/builds/start', async (route) => {
    activationOrder.push('start')
    activationRequests.start = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contract: 'ace.http.intelligence-build-result/v1alpha1',
        build_id: 'intelligence_build:world-ai',
        request_digest: `sha256:${'a'.repeat(64)}`,
        product_id: 'product:world-ai-command-center',
        actor_ref: 'principal:local-owner',
        accepted_at: approvedAt,
        resource_page: {
          contract: 'ace.intelligence.resource-plane-page/v1alpha1',
          state: 'complete',
          items: [profileResource, ...sessions, brief],
          as_of: availableAt,
          available_at: availableAt,
        },
      }),
    })
  })

  await page.goto('/atrium')
  await page.getByRole('button', { name: 'View build' }).click()
  await page.getByRole('button', { name: 'Use this intelligence' }).click()
  await page.getByRole('button', { name: 'Choose evidence' }).click()
  await page.getByRole('button', { name: 'Prepare exact plan' }).click()
  await expect(page.getByText('Exact proposal', { exact: true })).toBeVisible()
  await expect(page.getByText('directive_issued → implementation_reported')).toBeVisible()
  await expect(page.getByText('Decision 1 of 2 · Validate inputs')).toBeVisible()
  await page.getByRole('button', { name: 'Approve reviewed plan' }).click()
  await expect(page.getByRole('heading', { name: 'Nothing starts until you authorize this' })).toBeVisible()
  await expect(page.getByText('Decision 2 of 2 · Authorize & maintain')).toBeVisible()
  expect(activationOrder).toEqual(['bind', 'approve-reviewed-plan', 'preview-activation-plan'])
  await page.getByRole('button', { name: 'Authorize ACE to start and maintain' }).click()
  await expect(page.getByRole('heading', { name: 'Your first picture is ready' })).toBeVisible()
  expect(activationOrder).toEqual([
    'bind',
    'approve-reviewed-plan',
    'preview-activation-plan',
    'approve-activation-plan',
    'activate-builder-plan',
    'start',
  ])
  expect(activationRequests.previewActivationPlan).toEqual({
    current: exactBriefingReady,
    bound_plan: boundPlan,
    requested_at: approvedAt,
  })
  expect(activationRequests.approveActivationPlan).toEqual({
    decision: 'approve',
    current: exactBriefingReady,
    bound_plan: boundPlan,
    approved_at: approvedAt,
  })
  expect(activationRequests.activateBuilderPlan).toEqual({
    bound_plan: boundPlan,
    activation_approval_receipt_ref: approvalReceiptRef,
    requested_at: approvedAt,
  })
  expect(activationRequests.start.activation_approval_receipt_ref).toBe(approvalReceiptRef)
  const arrivalStatus = page.getByRole('list', { name: 'Source readiness, initialization, and first-Brief status' })
  await expect(arrivalStatus).toBeVisible()
  await expect(arrivalStatus.getByText('Sources-ready Builder revision recorded')).toBeVisible()
  await expect(arrivalStatus.getByText('First-briefing-ready revision recorded')).toBeVisible()
  await expect(arrivalStatus.getByText('Not active — maintenance requires its own governed activation')).toBeVisible()
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-live-builder-ready.png'), fullPage: true })
    await page.setViewportSize({ width: 768, height: 1024 })
    await page.screenshot({ path: testInfo.outputPath('atrium-live-builder-ready-768x1024.png'), fullPage: true })
    await page.setViewportSize({ width: 1440, height: 960 })
  }
  await page.getByRole('button', { name: 'Open my first briefing' }).click()
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(page.getByRole('heading', { name: brief.title })).toBeVisible()
})
