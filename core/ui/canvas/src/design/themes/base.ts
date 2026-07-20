// frontend/src/design/themes/base.ts
//
// The default ACE theme — empty overrides. All tokens come straight from
// design/tokens.css. This is the theme the open-source / generic ACE
// surface ships with. Branded extension themes override specific
// tokens on top of this.

import type { AceTheme } from './index'

export const baseTheme: AceTheme = {
  id: 'base',
  label: 'ACE base',
  // No overrides — uses everything from tokens.css as-is.
}
