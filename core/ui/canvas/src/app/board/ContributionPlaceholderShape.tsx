// core/ui/canvas/src/app/board/ContributionPlaceholderShape.tsx
//
// Ghosted lane shape for a voice that's in the room but hasn't fired
// yet (e.g. product_strategy at "not yet"). Dashed border, recessed
// surface, dimmed type — the room is always visible per the
// partner-never-asks thesis (no empty / waiting state).
import { BaseBoxShapeUtil, HTMLContainer, T } from 'tldraw'

import type { ContributionPlaceholderShape } from './shapes'

export class ContributionPlaceholderShapeUtil extends BaseBoxShapeUtil<ContributionPlaceholderShape> {
  static override type = 'contribution-placeholder' as const

  static override props = {
    w: T.number,
    h: T.number,
    lens: T.string,
    speaker: T.string,
    accent: T.string,
    hint: T.string,
  }

  override getDefaultProps(): ContributionPlaceholderShape['props'] {
    return {
      w: 280,
      h: 140,
      lens: 'voice',
      speaker: 'Voice',
      accent: 'var(--ace-ink-muted)',
      hint: 'not yet',
    }
  }

  override canResize = () => true
  override canEdit = () => false
  override hideRotateHandle = () => true

  override component(shape: ContributionPlaceholderShape) {
    const { w, h, speaker, accent, hint } = shape.props
    return (
      <HTMLContainer
        style={{
          width: w,
          height: h,
          pointerEvents: 'all',
        }}
      >
        <div className="ace-board-placeholder" style={{ borderColor: accent }}>
          <div className="ace-board-placeholder__byline">
            <span className="ace-board-placeholder__speaker" style={{ color: accent }}>
              {speaker}
            </span>
          </div>
          <div className="ace-board-placeholder__hint">{hint}</div>
        </div>
      </HTMLContainer>
    )
  }

  override indicator(shape: ContributionPlaceholderShape) {
    return <rect width={shape.props.w} height={shape.props.h} rx={12} ry={12} />
  }
}
