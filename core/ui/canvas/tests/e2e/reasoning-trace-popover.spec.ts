import { type Page, test, expect } from '@playwright/test'

// Navigate with a fake session ID so CanvasApp mounts without needing a real backend.
// The popover event listener is registered in useEffect — we wait for tldraw to mount
// before dispatching so the handler is guaranteed to be registered.
async function gotoCanvas(page: Page) {
  await page.goto('/?session=canvas:e2e-test')
  // tldraw always renders .tl-container once the editor mounts
  await page.waitForSelector('.tl-container', { timeout: 15000 })
}

async function openPopover(page: Page) {
  await page.evaluate(() => {
    document.dispatchEvent(
      new CustomEvent('ace-show-reasoning-trace', {
        bubbles: true,
        detail: { shapeId: 'shape:e2e-test' },
      }),
    )
  })
  // Wait for React to flush the state update and render the popover
  await expect(page.getByText('Why did ACE recommend this?')).toBeVisible({ timeout: 3000 })
}

test.describe('ReasoningTracePopover', () => {
  test('popover opens when ace-show-reasoning-trace is dispatched', async ({ page }) => {
    await gotoCanvas(page)
    await openPopover(page)
    await expect(page.getByText('Why did ACE recommend this?')).toBeVisible()
  })

  test('shows fallback text when no trace is stored for the shape', async ({ page }) => {
    await gotoCanvas(page)
    await openPopover(page)
    await expect(page.getByText('Reasoning trace not available for this artifact.')).toBeVisible()
  })

  test('Escape key closes the popover', async ({ page }) => {
    await gotoCanvas(page)
    await openPopover(page)
    await page.keyboard.press('Escape')
    await expect(page.getByText('Why did ACE recommend this?')).not.toBeVisible()
  })

  test('× close button closes the popover', async ({ page }) => {
    await gotoCanvas(page)
    await openPopover(page)
    await page.getByRole('button', { name: 'Close' }).click()
    await expect(page.getByText('Why did ACE recommend this?')).not.toBeVisible()
  })

  test('clicking the backdrop closes the popover', async ({ page }) => {
    await gotoCanvas(page)
    await openPopover(page)
    // Backdrop covers the tldraw area; modal is 420px wide and centered.
    // Click the top-left corner of the backdrop — safely outside the centered modal.
    const backdrop = page.getByTestId('trace-popover-backdrop')
    const box = await backdrop.boundingBox()
    await page.mouse.click(box!.x + 20, box!.y + 20)
    await expect(page.getByText('Why did ACE recommend this?')).not.toBeVisible()
  })

  test('clicking inside the modal does not close the popover', async ({ page }) => {
    await gotoCanvas(page)
    await openPopover(page)
    // Click the "Why did ACE recommend this?" text — inside the modal
    await page.getByText('Why did ACE recommend this?').click()
    await expect(page.getByText('Why did ACE recommend this?')).toBeVisible()
  })
})
