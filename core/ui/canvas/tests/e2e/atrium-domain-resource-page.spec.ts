import { readFileSync } from 'node:fs'

import { expect, test } from '@playwright/test'

const fixturePath = process.env.ACE_ATRIUM_RESOURCE_PAGE

test('Atrium renders an external domain resource page without domain UI code', async ({ page }, testInfo) => {
  test.skip(fixturePath === undefined, 'set ACE_ATRIUM_RESOURCE_PAGE to a domain-owned page artifact')
  const resourcePage = JSON.parse(readFileSync(fixturePath!, 'utf-8')) as {
    product_id: string
    items: Array<{ reference: { resource_kind: string }; title: string }>
  }

  await page.route('**/auth/token', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: 'fixture-token' }) }),
  )
  await page.route('**/v1/intelligence/resources/query', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(resourcePage) }),
  )

  await page.goto('/atrium')

  const brief = resourcePage.items.find((item) => item.reference.resource_kind === 'brief')
  await expect(page.getByText('ACE / World AI Command Center')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Intelligence' })).toBeVisible()
  if (brief !== undefined) {
    await expect(page.getByRole('button', { name: `Open ${brief.title}` })).toBeVisible()
  }
  await page.screenshot({ path: testInfo.outputPath('atrium-domain-resource-page.png'), fullPage: true })

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/atrium')
  await expect(page.getByRole('heading', { name: 'Intelligence' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('atrium-domain-resource-page-mobile.png'), fullPage: true })
})
