// core/ui/canvas/src/app/board/ContributionNoteShape.tsx
//
// Custom tldraw shape util for a lens contribution as a note on the
// board. Visually mirrors ContributionCard — the chrome translation
// from the spec:
//
//   - white fill (--ace-surface-raised) + hairline-shadow ring
//   - 2px lens-accent border-left
//   - Inter sans byline + serif body for the framing
//   - 12px radius
//   - in-flight: trailing blinking caret + thinkingAbout note in lens accent
//
// All visual values come from the design system tokens; no inline hex.
// The util extends BaseBoxShapeUtil so the shape gets drag/resize/select
// out of the box.
import { BaseBoxShapeUtil, HTMLContainer, T } from 'tldraw'

import type { ContributionNoteShape } from './shapes'

export class ContributionNoteShapeUtil extends BaseBoxShapeUtil<ContributionNoteShape> {
  static override type = 'contribution-note' as const

  static override props = {
    w: T.number,
    h: T.number,
    lens: T.string,
    speaker: T.string,
    accent: T.string,
    framing: T.string,
    landedAt: T.optional(T.string),
    inFlight: T.optional(T.boolean),
    thinkingAbout: T.optional(T.string),
  }

  override getDefaultProps(): ContributionNoteShape['props'] {
    return {
      w: 280,
      h: 200,
      lens: 'voice',
      speaker: 'Voice',
      accent: 'var(--ace-ink-muted)',
      framing: '',
      inFlight: false,
    }
  }

  override canResize = () => true
  override canEdit = () => false
  override hideRotateHandle = () => true

  override component(shape: ContributionNoteShape) {
    const { w, h, speaker, accent, framing, landedAt, inFlight, thinkingAbout } = shape.props
    return (
      <HTMLContainer
        style={{
          width: w,
          height: h,
          pointerEvents: 'all',
        }}
      >
        <div className="ace-board-note" style={{ borderLeftColor: accent }}>
          <div className="ace-board-note__byline">
            <span className="ace-board-note__speaker" style={{ color: accent }}>
              {speaker}
            </span>
            {landedAt !== undefined && (
              <span className="ace-board-note__landed-at">· {landedAt}</span>
            )}
          </div>
          <div className="ace-board-note__framing">
            {framing}
            {inFlight === true && (
              <span
                className="ace-board-note__caret"
                style={{ background: accent }}
                aria-hidden="true"
              />
            )}
          </div>
          {inFlight === true && thinkingAbout !== undefined && (
            <div
              className="ace-board-note__thinking-about"
              style={{ color: accent }}
            >
              thinking about {thinkingAbout}
            </div>
          )}
        </div>
      </HTMLContainer>
    )
  }

  override indicator(shape: ContributionNoteShape) {
    return <rect width={shape.props.w} height={shape.props.h} rx={12} ry={12} />
  }
}
