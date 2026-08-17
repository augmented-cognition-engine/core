import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, test } from 'vitest'

const SRC_ROOT = path.resolve(__dirname, '..', '..')

function source(relativePath: string): string {
  return fs.readFileSync(path.join(SRC_ROOT, relativePath), 'utf-8')
}

describe('Code Intelligence Canvas composition boundary', () => {
  test.each([
    'main.tsx',
    path.join('app', 'ext', 'defaults', 'KernelNav.tsx'),
  ])('%s does not bind the installed Code solution by name', (relativePath) => {
    const text = source(relativePath)
    expect(text).not.toContain('CodeIntelligenceOS')
    expect(text).not.toContain('/atrium/code')
  })

  test('the installed solution registration owns its route and surface import', () => {
    const text = source(path.join('app', 'solutions', 'code', 'register.tsx'))
    expect(text).toContain("import('../../atrium/CodeIntelligenceOS')")
    expect(text).toContain("path: '/atrium/code'")
    expect(text).toContain("href: '/atrium/code'")
  })
})
