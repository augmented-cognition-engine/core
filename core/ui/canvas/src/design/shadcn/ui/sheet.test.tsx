import { render } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { Sheet, SheetContent, SheetDescription, SheetTitle } from './sheet'

describe('Sheet', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('forwards the overlay ref required by the dialog portal', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    render(
      <Sheet open>
        <SheetContent>
          <SheetTitle>Evidence detail</SheetTitle>
          <SheetDescription>Inspect the cited resource lineage.</SheetDescription>
        </SheetContent>
      </Sheet>,
    )

    const refWarnings = consoleError.mock.calls.filter(([message]) =>
      String(message).includes('Function components cannot be given refs'),
    )
    expect(refWarnings).toEqual([])
  })
})
