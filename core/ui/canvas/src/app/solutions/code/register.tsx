import { lazy, Suspense } from 'react'
import { Code2 } from 'lucide-react'

import type { ExtensionUI } from '../../ext/registry'

const CodeIntelligenceOS = lazy(async () => {
  const module = await import('../../atrium/CodeIntelligenceOS')
  return { default: module.CodeIntelligenceOS }
})

const codeIntelligenceSolution: ExtensionUI = {
  name: 'code-intelligence',
  routes: [
    {
      path: '/atrium/code',
      element: (
        <Suspense fallback={<div role="status">Loading Code Intelligence…</div>}>
          <CodeIntelligenceOS />
        </Suspense>
      ),
    },
  ],
  navItems: [
    { href: '/atrium/code', icon: Code2, label: 'Code' },
  ],
}

export default codeIntelligenceSolution
