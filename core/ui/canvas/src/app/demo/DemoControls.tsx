// core/ui/canvas/src/app/demo/DemoControls.tsx
//
// Presenter control bar for demo mode — unobtrusive, bottom-right. Lets
// the presenter pause/resume, step to the next beat (to narrate), and
// replay. Rendered only when a demo scenario is active. Design-system
// only: Button + Icon, tokens for spacing/color.
import { Button, Icon } from '@/design/components'

import type { TimelineControls } from './useScriptedTimeline'

export interface DemoControlsProps {
  controls: TimelineControls
  scenarioId: string
}

export function DemoControls({ controls, scenarioId }: DemoControlsProps) {
  const { status, index, total, play, pause, step, replay } = controls
  const playing = status === 'playing'
  return (
    <div
      data-test="demo-controls"
      style={{
        position: 'fixed',
        bottom: 'var(--ace-space-4)',
        right: 'var(--ace-space-4)',
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--ace-space-2)',
        padding: 'var(--ace-space-2) var(--ace-space-3)',
        background: 'var(--ace-surface-raised)',
        border: '1px solid var(--ace-line)',
        borderRadius: 'var(--ace-radius-md)',
        boxShadow: 'var(--ace-shadow-popover)',
        zIndex: 50,
      }}
    >
      <span style={{ fontSize: 'var(--ace-text-xs)', color: 'var(--ace-ink-muted)' }}>
        demo · {scenarioId} · {index}/{total}
      </span>
      <Button
        variant="ghost"
        size="sm"
        onClick={playing ? pause : play}
        ariaLabel={playing ? 'Pause demo' : 'Play demo'}
      >
        <Icon name={playing ? 'pause' : 'play'} ariaLabel={playing ? 'pause' : 'play'} />
      </Button>
      <Button variant="ghost" size="sm" onClick={step} ariaLabel="Step to next beat">
        <Icon name="step" ariaLabel="step" />
      </Button>
      <Button variant="ghost" size="sm" onClick={replay} ariaLabel="Replay demo">
        <Icon name="replay" ariaLabel="replay" />
      </Button>
    </div>
  )
}
