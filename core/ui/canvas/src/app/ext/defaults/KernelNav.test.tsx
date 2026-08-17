// core/ui/canvas/src/app/ext/defaults/KernelNav.test.tsx
//
// Direct regression coverage for the active-nav match rule: exact-href match,
// nested-path match, the '/atrium' root's exact-only carve-out, and the
// literal-prefix trap where one href is a string prefix of an unrelated href.
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { SidebarProvider } from '@/design/shadcn/ui/sidebar'
import { TooltipProvider } from '@/design/shadcn/ui/tooltip'
import { isNavItemActive, KernelNav } from './KernelNav'

describe('isNavItemActive', () => {
  it('matches the exact href', () => {
    expect(isNavItemActive('/atrium/connections', '/atrium/connections')).toBe(true)
  })

  it('matches a path nested under the href', () => {
    expect(isNavItemActive('/atrium/connections/detail', '/atrium/connections')).toBe(true)
  })

  it('treats the "/atrium" root as active on its exact path only, never on a nested one', () => {
    expect(isNavItemActive('/atrium', '/atrium')).toBe(true)
    expect(isNavItemActive('/atrium/connections', '/atrium')).toBe(false)
  })

  it('does not activate on an unrelated href that merely shares a string prefix', () => {
    expect(isNavItemActive('/atrium/code-other', '/atrium/code')).toBe(false)
  })

  it('renders exact, child, and delimiter-safe non-match states consistently', () => {
    for (const [pathname, expectedActive] of [
      ['/atrium/code', true],
      ['/atrium/code/detail', true],
      ['/atrium/code-other', false],
    ] as const) {
      const { unmount } = render(
        <MemoryRouter initialEntries={[pathname]}>
          <TooltipProvider>
            <SidebarProvider>
              <KernelNav />
            </SidebarProvider>
          </TooltipProvider>
        </MemoryRouter>,
      )

      const codeLink = screen.getByRole('link', { name: 'Code' })
      expect(codeLink.getAttribute('data-active')).toBe(String(expectedActive))
      if (expectedActive) {
        expect(codeLink.getAttribute('aria-current')).toBe('page')
      } else {
        expect(codeLink.getAttribute('aria-current')).toBeNull()
      }
      unmount()
    }
  })
})
