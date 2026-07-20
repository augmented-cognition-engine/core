// app/journey/CapabilityGraph.tsx
//
// Mini visualization for the Frame stage — load-bearing capabilities and
// the dependency edges between them. Lifted from the original
// multiplayer.html cs-frame-graph idiom.
//
// SVG-based, responsive, uses semantic shadcn tokens (currentColor variants)
// so it themes correctly in light/dark mode.

interface CapabilityNode {
  id: string
  label: string
  state: 'load-bearing' | 'out-of-scope'
}

interface CapabilityEdge {
  from: string
  to: string
  /** When dashed, signals the relationship is implicit / tentative. */
  dashed?: boolean
}

interface CapabilityGraphProps {
  nodes: CapabilityNode[]
  edges: CapabilityEdge[]
}

const NODE_RADIUS = 7
const HEIGHT = 140
const SIDE_PAD = 60
const ROW_GAP = 36

export function CapabilityGraph({ nodes, edges }: CapabilityGraphProps) {
  // Two rows: load-bearing on top, out-of-scope on bottom. Each row lays
  // out only its own nodes so labels never crowd each other.
  const loadBearing = nodes.filter((n) => n.state === 'load-bearing')
  const outOfScope = nodes.filter((n) => n.state === 'out-of-scope')

  // Width scales with the wider of the two rows; min 120px per slot.
  const widestRow = Math.max(loadBearing.length, outOfScope.length, 1)
  const innerWidth = Math.max(360, widestRow * 130)
  const WIDTH = innerWidth + SIDE_PAD * 2

  const positions = new Map<string, { x: number; y: number; node: CapabilityNode }>()
  const placeRow = (row: CapabilityNode[], y: number) => {
    const step = row.length > 0 ? innerWidth / row.length : 0
    row.forEach((n, i) => {
      positions.set(n.id, {
        x: SIDE_PAD + step * (i + 0.5),
        y,
        node: n,
      })
    })
  }
  placeRow(loadBearing, HEIGHT / 2 - ROW_GAP / 2)
  placeRow(outOfScope, HEIGHT / 2 + ROW_GAP / 2)

  return (
    <div className="rounded-2xl border border-border bg-card/50 px-4 py-3">
      <div className="flex items-center justify-between pb-2">
        <span className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
          capability map · L5
        </span>
        <div className="flex items-center gap-3 font-mono text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className="h-2 w-2 rounded-full bg-primary" />
            load-bearing
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className="h-2 w-2 rounded-full bg-muted-foreground/40 border border-muted-foreground" />
            out of scope
          </span>
        </div>
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        preserveAspectRatio="xMidYMid meet"
        className="w-full h-auto text-muted-foreground"
        role="img"
        aria-label="capability map"
      >
        {/* Edges */}
        {edges.map((e, i) => {
          const from = positions.get(e.from)
          const to = positions.get(e.to)
          if (from === undefined || to === undefined) return null
          return (
            <line
              key={`e-${i}`}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke="currentColor"
              strokeWidth={1}
              strokeDasharray={e.dashed === true ? '3 3' : undefined}
              opacity={0.5}
            />
          )
        })}

        {/* Nodes */}
        {nodes.map((n) => {
          const pos = positions.get(n.id)
          if (pos === undefined) return null
          const isLoadBearing = n.state === 'load-bearing'
          return (
            <g key={n.id}>
              <circle
                cx={pos.x}
                cy={pos.y}
                r={NODE_RADIUS}
                className={
                  isLoadBearing
                    ? 'fill-primary stroke-primary'
                    : 'fill-card stroke-muted-foreground'
                }
                strokeWidth={1.5}
              />
              <text
                x={pos.x}
                y={isLoadBearing ? pos.y - NODE_RADIUS - 8 : pos.y + NODE_RADIUS + 16}
                textAnchor="middle"
                className={
                  isLoadBearing ? 'fill-foreground' : 'fill-muted-foreground'
                }
                style={{
                  fontFamily:
                    'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                  fontSize: 11,
                }}
              >
                {n.label}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
