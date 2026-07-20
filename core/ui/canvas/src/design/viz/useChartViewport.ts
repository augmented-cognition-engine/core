import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

/**
 * useChartViewport — interactions for x-axis pan + zoom on the SVG chart.
 *
 * Trading-chart convention: x-axis (time) is the only one the user controls
 * directly. Y-axis (price) auto-fits to whatever data is currently visible
 * in the viewport. Matches Lightweight Charts / TradingView / MT4 / NinjaTrader.
 *
 * Interactions:
 *   - Wheel: zoom in/out anchored at the cursor's time position
 *   - Mouse drag: pan horizontally (drag right → time moves backward)
 *   - Double-click: reset to the default viewport (full session)
 *   - Trackpad two-finger scroll (treated as wheel — pan + zoom)
 *
 * Bounds:
 *   - Viewport can shrink to MIN_RANGE_SEC (60s = a single minute zoom-in cap)
 *   - Viewport can grow to (dataMax - dataMin) × 1.5 (allow some right-padding
 *     so projection endpoints stay visible after a wide zoom-out)
 *   - Pan is unbounded — user can drag past data if they want (handy for
 *     placing markers in projection space)
 */

/**
 * Viewport bounds for both axes.
 *
 *   - start / end:  epoch seconds (x-axis time window)
 *   - yMin / yMax:  explicit price range, OR undefined for auto-fit
 *
 * When yMin/yMax are undefined, the y-axis follows data visible in the
 * current x-viewport (the default trading-chart convention). The user
 * pins them by shift+wheeling or shift+dragging — those interactions
 * exit auto mode and store explicit bounds. Reset clears both.
 */
export type Viewport = {
  start: number
  end: number
  yMin?: number
  yMax?: number
}

type Opts = {
  dataMin: number      // earliest epoch second in the dataset
  dataMax: number      // latest epoch second
  defaultStart: number // viewport.start on reset (typically session open)
  defaultEnd: number   // viewport.end on reset (typically session close)
  /**
   * Ref to the current effective y bounds (after auto-fit or manual
   * overrides). The hook reads this during shift+wheel/drag so y-zoom
   * can anchor at the cursor's current price. Setting via a ref instead
   * of a prop avoids a re-render storm — the hook only needs the value
   * at gesture time, not on every viewport change.
   */
  effectiveY: React.MutableRefObject<{ yMin: number; yMax: number }>
}

const MIN_RANGE_SEC = 60          // 1-minute zoom-in cap
const WHEEL_ZOOM_FACTOR = 1.18    // each wheel notch shrinks/grows the range by this
// Chart layout — should mirror PriceChart's X_DATA_END (82). Cursor positions
// past this fraction of the SVG width fall on the price-axis strip and get
// treated as y-axis interactions regardless of modifier keys.
const PRICE_AXIS_FRAC = 0.82

export function useChartViewport({ dataMin, dataMax, defaultStart, defaultEnd, effectiveY }: Opts) {
  const [viewport, setViewport] = useState<Viewport>({
    start: defaultStart,
    end: defaultEnd,
  })
  // Ref mirrors state so the drag handler reads the current viewport
  // without re-binding mousemove on every render.
  const viewportRef = useRef(viewport)
  useEffect(() => {
    viewportRef.current = viewport
  }, [viewport])

  // (Previously: auto-reset viewport when defaults changed. Removed —
  // every TanStack Query poll handed us a new data reference, which
  // sometimes shifted defaultStart/End by a second or two, which then
  // snapped the user out of any zoom they'd dialled in. Edwin's call:
  // reset is an explicit action via the RESET button. The user's
  // viewport persists across data refreshes until they reset it.)

  const maxRange = useMemo(
    () => Math.max(60 * 60, (dataMax - dataMin) * 1.5),
    [dataMin, dataMax],
  )

  const clamp = useCallback(
    (vp: Viewport): Viewport => {
      let { start, end } = vp
      let range = end - start
      // Min/max range
      if (range < MIN_RANGE_SEC) {
        const mid = (start + end) / 2
        start = mid - MIN_RANGE_SEC / 2
        end = mid + MIN_RANGE_SEC / 2
        range = MIN_RANGE_SEC
      } else if (range > maxRange) {
        const mid = (start + end) / 2
        start = mid - maxRange / 2
        end = mid + maxRange / 2
      }
      // Preserve yMin/yMax — clamp only touches the time axis. Returning
      // bare {start, end} would silently drop the y-pin and snap the
      // price axis back to auto-fit on the next render. (This was the
      // "y resets when I click" bug.)
      return { ...vp, start, end }
    },
    [maxRange],
  )

  const reset = useCallback(() => {
    // Reset to full session AND clear y overrides so the y-axis snaps
    // back to auto-fit. Log so any unexpected callers show up in the
    // console — Edwin previously saw the chart "reset" without pressing
    // the button; this trace lets us catch the next regression.
    console.log('[chart] reset() called', new Error().stack?.split('\n')[2]?.trim())
    setViewport({ start: defaultStart, end: defaultEnd })
  }, [defaultStart, defaultEnd])

  // Y-pin pattern: inside each x-action path we read effectiveY.current
  // and merge into the next viewport when yMin/yMax are still null. This
  // makes the first interaction freeze the auto-fit, so subsequent data
  // refreshes don't shift the price range under the user.

  // Ref for the SVG element (drag state ref declared later — both axes).
  const svgRef = useRef<SVGSVGElement>(null)

  // Cursor-anchored x-zoom. Locks y on first interaction so subsequent
  // data refreshes don't shift the price range under the user.
  const zoomXAtCursor = useCallback(
    (cursorClientX: number, factor: number) => {
      const svg = svgRef.current
      if (!svg) return
      const rect = svg.getBoundingClientRect()
      const cursorFrac = Math.max(0, Math.min(1, (cursorClientX - rect.left) / rect.width))
      const vp = viewportRef.current
      const range = vp.end - vp.start
      const cursorTime = vp.start + range * cursorFrac
      const newRange = Math.max(MIN_RANGE_SEC, Math.min(maxRange, range * factor))
      const newStart = cursorTime - newRange * cursorFrac
      const newEnd = newStart + newRange
      // Pin y if it's still auto so the user's view stays put on refresh.
      const yPin =
        vp.yMin == null || vp.yMax == null
          ? { yMin: effectiveY.current.yMin, yMax: effectiveY.current.yMax }
          : {}
      setViewport(clamp({ ...vp, ...yPin, start: newStart, end: newEnd }))
    },
    [clamp, maxRange, effectiveY],
  )

  // Cursor-anchored y-zoom. Exits auto-fit mode — yMin/yMax become
  // explicit. Reset clears them.
  const zoomYAtCursor = useCallback((cursorClientY: number, factor: number) => {
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const cursorFracY = Math.max(0, Math.min(1, (cursorClientY - rect.top) / rect.height))
    const { yMin: curMin, yMax: curMax } = effectiveY.current
    const curRange = curMax - curMin
    if (curRange <= 0) return
    // Cursor's price = top - frac * range (y=0 is top).
    const cursorPrice = curMax - curRange * cursorFracY
    const newRange = curRange * factor
    const newMax = cursorPrice + newRange * cursorFracY
    const newMin = newMax - newRange
    setViewport((vp) => ({ ...vp, yMin: newMin, yMax: newMax }))
  }, [effectiveY])

  const onWheel = useCallback(
    (e: React.WheelEvent<SVGSVGElement>) => {
      e.preventDefault?.()
      const svg = svgRef.current
      if (!svg) return
      const rect = svg.getBoundingClientRect()
      const cursorXFrac = (e.clientX - rect.left) / rect.width

      // Y-axis intent: explicit modifier (shift / alt / cmd), OR cursor is
      // over the right-side price-axis strip (TradingView convention).
      // macOS quirk: shift+scroll on a trackpad inverts deltaY → deltaX,
      // so for y-zoom we read whichever delta has a non-zero value.
      const wantsY = e.shiftKey || e.altKey || cursorXFrac >= PRICE_AXIS_FRAC
      if (wantsY) {
        const rawDelta = e.deltaY !== 0 ? e.deltaY : e.deltaX
        if (rawDelta === 0) return
        const factor = rawDelta > 0 ? WHEEL_ZOOM_FACTOR : 1 / WHEEL_ZOOM_FACTOR
        zoomYAtCursor(e.clientY, factor)
        return
      }

      // Trackpad horizontal scroll without modifier → x-pan.
      const horizontalDominant =
        Math.abs(e.deltaX) > Math.abs(e.deltaY) && !e.ctrlKey && !e.metaKey
      if (horizontalDominant) {
        const range = viewportRef.current.end - viewportRef.current.start
        const delta = (e.deltaX / rect.width) * range
        const vp = viewportRef.current
        const yPin =
          vp.yMin == null || vp.yMax == null
            ? { yMin: effectiveY.current.yMin, yMax: effectiveY.current.yMax }
            : {}
        setViewport(clamp({ ...vp, ...yPin, start: vp.start + delta, end: vp.end + delta }))
        return
      }
      // Plain wheel → x-zoom.
      const rawDelta = e.deltaY !== 0 ? e.deltaY : e.deltaX
      if (rawDelta === 0) return
      const factor = rawDelta > 0 ? WHEEL_ZOOM_FACTOR : 1 / WHEEL_ZOOM_FACTOR
      zoomXAtCursor(e.clientX, factor)
    },
    [clamp, zoomXAtCursor, zoomYAtCursor],
  )

  // Drag-axis state: captured at mousedown so the entire gesture stays
  // on the axis it started on (avoids jitter if user mid-gesture releases
  // shift). 'x' = pan time, 'y' = pan price.
  const dragRef2 = useRef<
    | {
        axis: 'x' | 'y'
        startX: number
        startY: number
        vpStart: number
        vpEnd: number
        yMin: number
        yMax: number
        svgWidth: number
        svgHeight: number
      }
    | null
  >(null)

  const onMouseDown = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      // Only left-button drags pan. Right-click reserved for future menu.
      if (e.button !== 0) return
      const svg = svgRef.current
      if (!svg) return
      const rect = svg.getBoundingClientRect()
      const cursorXFrac = (e.clientX - rect.left) / rect.width
      const { yMin: curYMin, yMax: curYMax } = effectiveY.current
      // Y-axis drag intent: shift OR alt modifier, OR cursor over the
      // right-side price-axis strip (TradingView convention).
      const wantsY = e.shiftKey || e.altKey || cursorXFrac >= PRICE_AXIS_FRAC
      dragRef2.current = {
        axis: wantsY ? 'y' : 'x',
        startX: e.clientX,
        startY: e.clientY,
        vpStart: viewportRef.current.start,
        vpEnd: viewportRef.current.end,
        yMin: curYMin,
        yMax: curYMax,
        svgWidth: rect.width,
        svgHeight: rect.height,
      }
      // Pin y on first interaction — a click alone (no drag) counts.
      // Without this, clicking the chart without moving leaves y in
      // auto-fit mode, so the next data refresh shifts the price range
      // and feels like a reset. Once pinned, only the RESET button
      // releases the pin.
      setViewport((vp) => {
        if (vp.yMin != null && vp.yMax != null) return vp
        return { ...vp, yMin: curYMin, yMax: curYMax }
      })
    },
    [effectiveY],
  )

  // mousemove + mouseup attached to window so dragging past the SVG's edges
  // still works (a common gotcha if you only attach to the SVG itself).
  useEffect(() => {
    function onMove(e: MouseEvent) {
      const d = dragRef2.current
      if (!d) return
      if (d.axis === 'x') {
        const deltaPx = e.clientX - d.startX
        const range = d.vpEnd - d.vpStart
        const deltaTime = -(deltaPx / d.svgWidth) * range
        setViewport((vp) => {
          const yPin =
            vp.yMin == null || vp.yMax == null
              ? { yMin: effectiveY.current.yMin, yMax: effectiveY.current.yMax }
              : {}
          return clamp({
            ...vp,
            ...yPin,
            start: d.vpStart + deltaTime,
            end: d.vpEnd + deltaTime,
          })
        })
      } else {
        // y-pan: drag down → prices shift up (chart slides down). Sign of
        // delta inverted because canvas y=0 is top.
        const deltaPx = e.clientY - d.startY
        const range = d.yMax - d.yMin
        const deltaPrice = (deltaPx / d.svgHeight) * range
        setViewport((vp) => ({
          ...vp,
          yMin: d.yMin + deltaPrice,
          yMax: d.yMax + deltaPrice,
        }))
      }
    }
    function onUp() {
      dragRef2.current = null
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [clamp, effectiveY])

  const isDragging = useCallback(() => dragRef2.current !== null, [])
  const dragAxis = useCallback(() => dragRef2.current?.axis ?? null, [])

  return {
    viewport,
    setViewport,
    reset,
    isDragging,
    dragAxis,
    svgRef,
    handlers: {
      onWheel,
      onMouseDown,
    },
  }
}
