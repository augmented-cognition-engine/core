// frontend/src/design/components/AskInput.tsx
//
// Persistent interaction primitive — "Ask the team" / "Tell the partner".
// The partnership-thesis affordance that replaces play/restart/submit
// chrome. Always available, never gated.
//
// Three uses today:
//   - Bottom of DeliberationPage (fixed footer, "Ask the team")
//   - Inside ClosingAsk (inline, "Tell the partner")
//   - Future: per-lens follow-up inputs
import { useState } from 'react'

import { Button } from './Button'
import { Eyebrow } from './Eyebrow'
import { Input } from './Input'

export interface AskInputProps {
  /** Small-caps label shown before the input. */
  label: string
  placeholder?: string
  /** Submit handler. Receives the trimmed text. The input clears on submit. */
  onSubmit: (text: string) => void
  /** Compact vs comfortable layout. */
  size?: 'sm' | 'md'
  dataTest?: string
}

export function AskInput({
  label,
  placeholder = '…',
  onSubmit,
  size = 'md',
  dataTest,
}: AskInputProps) {
  const [text, setText] = useState('')
  const submit = (value: string) => {
    onSubmit(value)
    setText('')
  }
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--ace-space-3)',
        fontFamily: 'var(--ace-font-sans)',
      }}
    >
      <Eyebrow>{label}</Eyebrow>
      <div style={{ flex: '1 1 auto', minWidth: 0 }}>
        <Input
          value={text}
          onChange={setText}
          onSubmit={submit}
          placeholder={placeholder}
          size={size}
          ariaLabel={label}
          dataTest={dataTest}
        />
      </div>
      <Button
        variant="primary"
        size={size}
        onClick={() => submit(text.trim())}
        disabled={text.trim().length === 0}
        ariaLabel="Send"
      >
        send ↵
      </Button>
    </div>
  )
}
