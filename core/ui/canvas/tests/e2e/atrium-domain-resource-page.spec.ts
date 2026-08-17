import { readFileSync } from 'node:fs'

import { expect, test } from '@playwright/test'

const fixturePath = process.env.ACE_ATRIUM_RESOURCE_PAGE

test('Atrium renders an external domain resource page without domain UI code', async ({ page }, testInfo) => {
  test.skip(fixturePath === undefined, 'set ACE_ATRIUM_RESOURCE_PAGE to a domain-owned page artifact')
  const resourcePage = JSON.parse(readFileSync(fixturePath!, 'utf-8')) as {
    product_id: string
    items: Array<{ reference: { resource_kind: string }; title: string }>
  }

  await page.goto('/atrium')

  const brief = resourcePage.items.find((item) => item.reference.resource_kind === 'brief')
  await expect(page.getByText('ACE / World AI Command Center')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
  if (brief !== undefined) {
    await expect(page.getByRole('heading', { name: brief.title })).toBeVisible()
  }
  if ((resourcePage as { state?: string }).state === 'degraded') {
    await expect(page.getByText('Some evidence still needs review')).toBeVisible()
  }
  await expect(page.getByText(`${resourcePage.items.length} cited records`)).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('atrium-domain-resource-page.png'), fullPage: true })

  const viewBuild = page.getByRole('button', { name: 'Review build' })
  if (await viewBuild.isVisible()) {
    await viewBuild.click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('button', { name: 'View build status' }).click()
    await expect(page.getByRole('heading', { name: 'Your first picture is ready' })).toBeVisible()
    await expect(page.getByText(/A durable first-briefing-ready revision is recorded/)).toBeVisible()
    await expect(page.getByText(/First cited Brief ready · Maintenance not active/)).toBeVisible()
    await page.getByRole('button', { name: 'Open my first briefing' }).click()
  }

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/atrium')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('atrium-domain-resource-page-mobile.png'), fullPage: true })
})
