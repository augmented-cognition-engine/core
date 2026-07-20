// frontend/src/design/components/RosterRow.tsx
//
// Horizontal row of discipline Avatars — the "who's in the room" strip
// in the deliberation topbar. A thin wrapper over Avatar that takes a
// lens array and lays them out with consistent spacing.
import { Avatar } from './Avatar'

export interface RosterRowProps {
  lenses: string[]
  size?: 'sm' | 'md' | 'lg'
}

export function RosterRow({ lenses, size = 'md' }: RosterRowProps) {
  return (
    <div
      style={{
        display: 'flex',
        gap: 'var(--ace-space-1)',
        alignItems: 'center',
        flex: '0 0 auto',
      }}
    >
      {lenses.map((lens) => (
        <Avatar key={lens} lens={lens} size={size} />
      ))}
    </div>
  )
}
