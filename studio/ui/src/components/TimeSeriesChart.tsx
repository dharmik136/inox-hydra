import { useEffect, useMemo, useRef, useState } from "react";

export interface SeriesPoint {
  date: string;
  value: number | null;
}

interface TimeSeriesChartProps {
  points: SeriesPoint[];
  /** Names what is plotted. A single series needs no legend, so this carries it. */
  label: string;
  formatValue?: (value: number) => string;
}

const PAD = { top: 16, right: 20, bottom: 26, left: 48 };
const HEIGHT = 260;

/** Clean axis ceilings, so ticks land on numbers a reader would choose. */
function niceCeiling(max: number): number {
  if (max <= 0) return 10;
  const magnitude = 10 ** Math.floor(Math.log10(max));
  const normalised = max / magnitude;
  const step = normalised <= 1 ? 1 : normalised <= 2 ? 2 : normalised <= 5 ? 5 : 10;
  return step * magnitude;
}

function defaultFormat(value: number): string {
  if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

/**
 * One measure over time, with a crosshair (blueprint section 13).
 *
 * Drawn as SVG rather than through a chart library. This is a single series
 * with one axis, and the marks follow fixed specs, a 2px line, an 8px end
 * marker carrying a 2px ring in the surface colour, a 10% area wash and
 * hairline gridlines. Reaching those through a library's escape hatches is
 * more code than drawing them, and this bundle ships to a local machine where
 * a second copy of a plotting runtime buys nothing. A library earns its place
 * when this surface needs several chart forms rather than one.
 *
 * There is deliberately no second y-axis and no second series. Two measures of
 * different scale get two charts.
 */
export function TimeSeriesChart({ points, label, formatValue = defaultFormat }: TimeSeriesChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [width, setWidth] = useState(640);

  const measured = useMemo(() => points.filter((p) => p.value !== null), [points]);

  const scale = useMemo(() => {
    const max = niceCeiling(Math.max(...measured.map((p) => p.value ?? 0), 1));
    const plotWidth = Math.max(width - PAD.left - PAD.right, 10);
    const plotHeight = HEIGHT - PAD.top - PAD.bottom;
    const x = (index: number) =>
      PAD.left + (points.length <= 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth);
    const y = (value: number) => PAD.top + plotHeight - (value / max) * plotHeight;
    return { max, x, y, plotWidth, plotHeight };
  }, [points, measured, width]);

  // Observe the container so the chart fills the column it is given. A
  // callback ref would construct a new observer on every render and never
  // disconnect the previous one, leaving one observer per render alive for the
  // life of the page.
  const containerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  if (measured.length === 0) {
    return (
      <div className="grid h-[260px] place-items-center rounded-md border border-edge">
        <p className="studio-meta text-ink-muted">NOTHING MEASURED IN THIS RANGE</p>
      </div>
    );
  }

  const path = points
    .map((point, index) =>
      point.value === null ? null : `${scale.x(index)},${scale.y(point.value)}`,
    )
    .filter(Boolean)
    .map((pair, index) => `${index === 0 ? "M" : "L"}${pair}`)
    .join(" ");

  const areaPath = `${path} L${scale.x(points.length - 1)},${HEIGHT - PAD.bottom} L${scale.x(0)},${HEIGHT - PAD.bottom} Z`;

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((fraction) => scale.max * fraction);
  const lastIndex = points.reduce((acc, p, i) => (p.value !== null ? i : acc), 0);
  const peakIndex = points.reduce(
    (acc, p, i) => (p.value !== null && p.value > (points[acc]?.value ?? -1) ? i : acc),
    lastIndex,
  );

  const activeIndex = hover ?? null;
  const active = activeIndex !== null ? points[activeIndex] : null;

  function onMove(event: React.PointerEvent<SVGSVGElement>) {
    const box = svgRef.current?.getBoundingClientRect();
    if (!box) return;
    // Snap to the nearest data position. The reader aims at a date, never at a
    // 2px line, so the hit target is the whole column.
    const relative = event.clientX - box.left - PAD.left;
    const step = scale.plotWidth / Math.max(points.length - 1, 1);
    const index = Math.round(relative / step);
    setHover(Math.min(Math.max(index, 0), points.length - 1));
  }

  return (
    <div ref={containerRef} className="relative">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${width} ${HEIGHT}`}
        width="100%"
        height={HEIGHT}
        role="img"
        aria-label={`${label} over time. ${measured.length} measured points.`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {/* Gridlines and ticks. Hairline, solid, recessive, and the text wears
            a text token rather than the series colour. */}
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={PAD.left}
              x2={width - PAD.right}
              y1={scale.y(tick)}
              y2={scale.y(tick)}
              className="stroke-edge"
              strokeWidth={1}
            />
            <text
              x={PAD.left - 8}
              y={scale.y(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-ink-muted font-mono text-[10px]"
            >
              {formatValue(tick)}
            </text>
          </g>
        ))}

        <path d={areaPath} className="fill-chart-1" opacity={0.1} />
        <path
          d={path}
          fill="none"
          className="stroke-chart-1"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* The crosshair finds the X. */}
        {active && (
          <line
            x1={scale.x(activeIndex!)}
            x2={scale.x(activeIndex!)}
            y1={PAD.top}
            y2={HEIGHT - PAD.bottom}
            className="stroke-edge-strong"
            strokeWidth={1}
          />
        )}

        {/* End marker and peak, labelled selectively rather than every point.
            Each carries a 2px ring in the surface colour so it stays legible
            where it crosses the line. */}
        {[peakIndex, lastIndex].map((index) =>
          points[index]?.value === null ? null : (
            <circle
              key={index}
              cx={scale.x(index)}
              cy={scale.y(points[index].value!)}
              r={4}
              className="fill-chart-1 stroke-ink"
              strokeWidth={2}
            />
          ),
        )}

        {active && active.value !== null && (
          <circle
            cx={scale.x(activeIndex!)}
            cy={scale.y(active.value)}
            r={4}
            className="fill-chart-1 stroke-ink"
            strokeWidth={2}
          />
        )}

        {/* X labels at the ends only. A date on every point is unreadable. */}
        <text x={PAD.left} y={HEIGHT - 8} className="fill-ink-muted font-mono text-[10px]">
          {points[0]?.date.slice(5)}
        </text>
        <text
          x={width - PAD.right}
          y={HEIGHT - 8}
          textAnchor="end"
          className="fill-ink-muted font-mono text-[10px]"
        >
          {points[points.length - 1]?.date.slice(5)}
        </text>
      </svg>

      {/* Tooltip: the value leads, the label follows, because the reader
          already has the series and wants the number. */}
      {active && active.value !== null && (
        <div
          className="pointer-events-none absolute top-2 rounded-md border border-edge bg-raised px-2 py-1.5 shadow-lg"
          style={{
            left: Math.min(Math.max(scale.x(activeIndex!) - 50, 0), Math.max(width - 110, 0)),
          }}
        >
          <p className="text-[13px] font-medium text-ink-primary tabular-nums">
            {formatValue(active.value)}
          </p>
          <p className="studio-meta flex items-center gap-1.5 text-[10px]">
            <span className="inline-block h-0.5 w-3 bg-chart-1" aria-hidden="true" />
            {active.date}
          </p>
        </div>
      )}

      {/* The table view, so the values are reachable without a pointer. */}
      <details className="mt-2">
        <summary className="studio-meta cursor-pointer text-[10px] text-ink-muted hover:text-ink-secondary">
          TABLE VIEW
        </summary>
        <table className="mt-2 w-full text-left">
          <caption className="sr-only">{label} by date</caption>
          <thead>
            <tr className="studio-meta text-[10px]">
              <th scope="col" className="py-1 font-normal">DATE</th>
              <th scope="col" className="py-1 text-right font-normal">{label.toUpperCase()}</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.date} className="border-t border-edge">
                <td className="studio-meta py-1 text-[11px]">{point.date}</td>
                <td className="studio-meta py-1 text-right text-[11px] text-ink-secondary">
                  {point.value === null ? "not measured" : formatValue(point.value)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
