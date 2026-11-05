"use client";

import { useState } from "react";
import { SAMPLE_ACTIVITY } from "@/lib/sampleData";
import { formatDate } from "@/lib/format";
import { SampleBadge } from "@/components/ui/Badge";

const W = 640;
const H = 260;
const PAD = { top: 16, right: 12, bottom: 30, left: 34 };

/** Hand-drawn SVG chart (no chart library needed): bars = extracted, line = verified. */
export function ActivityChart() {
  const data = SAMPLE_ACTIVITY;
  const [hover, setHover] = useState<number | null>(null);

  const max = Math.ceil(Math.max(...data.map((d) => d.extracted)) / 10) * 10;
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const slot = innerW / data.length;
  const barW = slot * 0.56;
  const x = (i: number) => PAD.left + slot * i + slot / 2;
  const y = (v: number) => PAD.top + innerH - (v / max) * innerH;
  const ticks = [0, max / 4, max / 2, (max * 3) / 4, max];
  const linePath = data.map((d, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(d.verified).toFixed(1)}`).join(" ");

  const active = hover !== null ? data[hover] : null;

  return (
    <div className="card p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Extraction activity</h2>
          <p className="text-xs text-muted">Records per day · last 14 days</p>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted">
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-brand" aria-hidden />Extracted</span>
          <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 rounded bg-accent" aria-hidden />Verified</span>
          <SampleBadge />
        </div>
      </div>

      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Bar and line chart of sample extraction activity over the last 14 days">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} style={{ stroke: "rgb(var(--line))" }} strokeDasharray={t === 0 ? undefined : "3 4"} />
              <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end" fontSize="11" style={{ fill: "rgb(var(--muted))" }}>
                {Math.round(t)}
              </text>
            </g>
          ))}

          {data.map((d, i) => (
            <g key={d.date}>
              <rect
                x={x(i) - barW / 2}
                y={y(d.extracted)}
                width={barW}
                height={y(0) - y(d.extracted)}
                rx={4}
                style={{ fill: "rgb(var(--brand))", opacity: hover === null || hover === i ? 1 : 0.45, transition: "opacity .15s" }}
              />
              {i % 2 === 0 && (
                <text x={x(i)} y={H - 10} textAnchor="middle" fontSize="11" style={{ fill: "rgb(var(--muted))" }}>
                  {d.date.slice(8)}/{d.date.slice(5, 7)}
                </text>
              )}
            </g>
          ))}

          <path d={linePath} fill="none" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" style={{ stroke: "rgb(var(--accent))" }} />
          {data.map((d, i) => (
            <circle key={d.date} cx={x(i)} cy={y(d.verified)} r={hover === i ? 5 : 3} style={{ fill: "rgb(var(--accent))", stroke: "rgb(var(--surface))" }} strokeWidth={2} />
          ))}

          {/* Invisible hover columns */}
          {data.map((d, i) => (
            <rect
              key={`hit-${d.date}`}
              x={PAD.left + slot * i}
              y={PAD.top}
              width={slot}
              height={innerH}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              onTouchStart={() => setHover(i)}
            />
          ))}
        </svg>

        {active && hover !== null && (
          <div
            className="pointer-events-none absolute top-2 z-10 -translate-x-1/2 rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-card"
            style={{ left: `${(x(hover) / W) * 100}%` }}
          >
            <div className="font-semibold">{formatDate(active.date)}</div>
            <div className="text-muted">Extracted: <span className="font-semibold text-ink">{active.extracted}</span></div>
            <div className="text-muted">Verified: <span className="font-semibold text-ink">{active.verified}</span></div>
          </div>
        )}
      </div>
    </div>
  );
}
