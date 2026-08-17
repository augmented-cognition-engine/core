import { expect, test } from '@playwright/test'

const previousAt = '2026-08-10T12:00:00.000Z'
const currentAt = '2026-08-14T12:00:00.000Z'

function resource(
  kind: string,
  id: string,
  options: {
    title?: string
    summary?: string
    asOf?: string
    subjectRefs?: string[]
    provenance?: unknown[]
    payload?: unknown
  } = {},
) {
  const asOf = options.asOf ?? currentAt
  return {
    contract: 'ace.intelligence.resource-plane-record/v1alpha1',
    reference: {
      contract: 'ace.intelligence.resource-plane-reference/v1alpha1',
      product_id: 'product:world-intelligence',
      resource_kind: kind,
      resource_id: `${kind}:${id}`,
      resource_digest: `sha256:${id.padEnd(64, 'a').slice(0, 64)}`,
      resource_contract: `ace.demo.${kind}/v1`,
      revision: 1,
      as_of: asOf,
      available_at: asOf,
    },
    availability: 'available',
    title: options.title ?? id,
    summary: options.summary ?? null,
    subject_refs: options.subjectRefs ?? [],
    provenance: options.provenance ?? [],
    supersedes: null,
    payload: options.payload ?? {},
    degraded_reason_refs: [],
  }
}

function entity(id: string, asOf: string, posture: string, employees: number, provenance: unknown[] = []) {
  return resource('entity', id, {
    title: 'entity:atlas-labs',
    asOf,
    subjectRefs: ['entity:atlas-labs'],
    provenance,
    payload: {
      value_json: JSON.stringify({
        entity_ref: 'entity:atlas-labs',
        entity_type_ref: 'entity_type:company',
        attributes: {
          value_json: JSON.stringify({
            name: 'Atlas Labs',
            posture,
            employee_count: employees,
          }),
        },
        projected_at: asOf,
        confidence: 0.91,
      }),
    },
  })
}

test('Explore projects honest entity intelligence and depth-limited relationships at desktop and narrow widths', async ({ page }, testInfo) => {
  const observation = resource('observation', 'atlas-pricing', {
    title: 'Published Atlas pricing observation',
    summary: 'The public enterprise tier moved lower.',
    asOf: '2026-08-13T12:00:00.000Z',
    subjectRefs: ['entity:atlas-labs'],
    payload: {
      value_json: JSON.stringify({
        event_effective_at: '2026-08-13T09:00:00.000Z',
        observed_at: '2026-08-13T12:00:00.000Z',
      }),
    },
  })
  const previous = entity('atlas-previous', previousAt, 'steady', 80)
  const current = entity('atlas-current', currentAt, 'expanding', 95, [observation.reference])
  const signal = resource('signal', 'atlas-expansion', {
    title: 'Atlas expansion signal',
    summary: 'Hiring and availability moved together.',
    asOf: '2026-08-14T13:00:00.000Z',
    subjectRefs: ['entity:atlas-labs'],
    provenance: [current.reference],
  })
  const shift = resource('shift', 'atlas-pricing-shift', {
    title: 'Atlas enterprise pricing shifted',
    summary: 'The admitted public tier is lower than the previous baseline.',
    asOf: '2026-08-14T14:00:00.000Z',
    subjectRefs: ['entity:atlas-labs'],
  })
  const conflict = resource('conflict', 'atlas-region-conflict', {
    title: 'Regional availability sources disagree',
    summary: 'Two admitted records report different launch scope.',
    subjectRefs: ['entity:atlas-labs'],
  })
  const uncertainty = resource('uncertainty', 'atlas-adoption-unknown', {
    title: 'Regional adoption remains unknown',
    summary: 'No admitted customer-adoption record closes this question.',
    subjectRefs: ['entity:atlas-labs'],
  })
  const brief = resource('brief', 'atlas-answer', {
    title: 'Atlas is expanding while price pressure rises',
    summary: 'The current cited picture separates operating expansion from pricing pressure.',
    subjectRefs: ['entity:atlas-labs'],
    provenance: [current.reference, signal.reference, shift.reference],
  })

  await page.route('**/auth/token', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: 'test-token' }) }),
  )
  await page.route('**/v1/intelligence/resources/query', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        contract: 'ace.intelligence.resource-plane-page/v1alpha1',
        query_id: 'resource_query:entity-explore',
        query_digest: `sha256:${'b'.repeat(64)}`,
        product_id: 'product:world-intelligence',
        actor_ref: 'principal:demo-analyst',
        as_of: currentAt,
        available_at: currentAt,
        evaluated_at: currentAt,
        state: 'complete',
        items: [observation, previous, current, signal, shift, conflict, uncertainty, brief],
        next_cursor: null,
        degraded_reason_refs: [],
        page_id: 'resource_page:entity-explore',
        page_digest: `sha256:${'c'.repeat(64)}`,
      }),
    }),
  )

  await page.setViewportSize({ width: 1440, height: 960 })
  await page.goto('/atrium/explore')

  await expect(page.getByRole('heading', { name: 'Explore' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Ask, then inspect the basis.' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Inspect the supported world behind the answer.' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Atlas Labs' })).toBeVisible()
  await expect(page.getByText('91%')).toBeVisible()
  await expect(page.getByText('80 → 95')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Recent admitted developments' })).toBeVisible()
  await expect(page.getByText('Atlas expansion signal')).toBeVisible()
  await expect(page.getByText('event effective')).toBeVisible()
  await expect(page.getByText('Regional availability sources disagree')).toBeVisible()
  await expect(page.getByText('Regional adoption remains unknown')).toBeVisible()
  await expect(page.getByText(/First-class event resources are not part/)).toBeVisible()
  await expect(page.getByText(/Semantic entity-to-entity relationships are not projected/)).toBeVisible()

  const depthZero = page.getByRole('button', { name: 'Depth 0' })
  const depthOne = page.getByRole('button', { name: 'Depth 1' })
  await expect(depthZero).toHaveAttribute('aria-pressed', 'true')
  await depthOne.click()
  await expect(depthOne).toHaveAttribute('aria-pressed', 'true')
  const relationships = page.getByRole('list', { name: 'Depth 1 resource relationships' })
  await expect(relationships).toContainText('Exact upstream record')
  await expect(relationships).toContainText('Exact derived record')
  await expect(relationships).toContainText('Published Atlas pricing observation')
  await expect(relationships).toContainText('Atlas expansion signal')

  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-entity-intelligence.png'), fullPage: true })
  }

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/atrium/explore')
  await expect(page.getByRole('heading', { name: 'Atlas Labs' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Depth 0' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  if (process.env.ACE_CAPTURE_ATRIUM === '1') {
    await page.screenshot({ path: testInfo.outputPath('atrium-entity-intelligence-narrow.png') })
  }

  await page.getByRole('button', { name: 'Toggle Sidebar' }).click()
  await expect(page.getByRole('link', { name: 'Explore', exact: true })).toBeVisible()
})
