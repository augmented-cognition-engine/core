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
  await expect(page.getByText('Frontier inference costs moved down again').first()).toBeVisible()
  await expect(page.getByText(/cited record/)).toBeVisible()

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
