import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { SidebarProvider } from '@/design/shadcn/ui/sidebar'
import { TooltipProvider } from '@/design/shadcn/ui/tooltip'

import { KernelNav } from './KernelNav'

describe('KernelNav product identity', () => {
  it('uses the official ACE mark in the top-left shell identity', () => {
    const { container } = render(
      <MemoryRouter>
        <TooltipProvider>
          <SidebarProvider>
            <KernelNav />
          </SidebarProvider>
        </TooltipProvider>
      </MemoryRouter>,
    )

    const mark = container.querySelector<HTMLImageElement>(
      'img[src="/brand/ace_logo_fixed_128.png"]',
    )
    expect(mark).not.toBeNull()
    expect(mark?.alt).toBe('')
  })
})
