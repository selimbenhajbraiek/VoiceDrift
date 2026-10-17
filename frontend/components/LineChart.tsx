"use client";
// A small single-series line chart in SVG: ink line and points (hollow = baseline readings), optional labeled
// background bands, hover tooltip, value at the end. Status is never shown by color alone: bands carry their names.
import { useEffect, useRef, useState } from "react";

export interface Point {
  label: string;      // x-axis label (a short date)
  y: number;
  hollow?: boolean;   // a baseline reading
  tip: string[];      // tooltip lines
}

export interface Band {
  from: number;
  to: number;
  fill: string;
  label?: string;
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.round(e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

export function LineChart({ points, domain, bands = [], ticks = [], height = 220, endLabel, format = (v) => String(v), ariaLabel }: {
  points: Point[];
  domain: [number, number];
  bands?: Band[];
  ticks?: number[];
  height?: number;
  endLabel?: string;
  format?: (v: number) => string;
  ariaLabel: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const pad = { top: 12, right: endLabel ? 76 : 16, bottom: 26, left: 40 };
  const w = Math.max(0, width - pad.left - pad.right);
  const h = height - pad.top - pad.bottom;
  const [lo, hi] = domain;
  const x = (i: number) => pad.left + (points.length === 1 ? w / 2 : (i / (points.length - 1)) * w);
  const y = (v: number) => pad.top + h - ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * h;
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.y).toFixed(1)}`).join(" ");
  const showLabel = (i: number) => points.length <= 8 || i === 0 || i === points.length - 1 || i % Math.ceil(points.length / 6) === 0;
  const step = points.length > 1 ? w / (points.length - 1) : w;

  return (
    <div className="chart" ref={ref} style={{ height }}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={ariaLabel} onMouseLeave={() => setHover(null)}>
          {bands.map((b) => (
            <g key={`${b.from}-${b.to}`}>
              <rect x={pad.left} width={w} y={y(b.to)} height={Math.max(0, y(b.from) - y(b.to))} style={{ fill: b.fill }} />
              {b.label && <text className="band-label" x={pad.left + w - 6} y={y(b.to) + 14} textAnchor="end">{b.label}</text>}
            </g>
          ))}
          {ticks.map((t) => (
            <g key={t}>
              <line className="grid" x1={pad.left} x2={pad.left + w} y1={y(t)} y2={y(t)} />
              <text className="tick" x={pad.left - 8} y={y(t) + 4} textAnchor="end">{format(t)}</text>
            </g>
          ))}
          <path d={path} className="series" />
          {points.map((p, i) => (
            <g key={i}>
              {showLabel(i) && <text className="tick" x={x(i)} y={height - 6} textAnchor="middle">{p.label}</text>}
              <circle cx={x(i)} cy={y(p.y)} r={hover === i ? 6 : 4.5} className={p.hollow ? "pt hollow" : "pt"} />
              {/* a hit area wider than the mark */}
              <rect x={x(i) - step / 2} width={step} y={pad.top} height={h} fill="transparent"
                onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)} tabIndex={0} aria-label={p.tip.join(", ")} />
            </g>
          ))}
          {endLabel && points.length > 0 && (
            <text className="end-label" x={x(points.length - 1) + 12} y={y(points[points.length - 1].y) + 4}>{endLabel}</text>
          )}
          {hover !== null && <line className="crosshair" x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + h} />}
        </svg>
      )}
      {hover !== null && width > 0 && (
        <div className="chart-tip" style={{ left: Math.min(Math.max(x(hover), 70), width - 70), top: Math.max(0, y(points[hover].y) - 64) }}>
          {points[hover].tip.map((line, i) => <span key={i} className={i ? "" : "strong"}>{line}</span>)}
        </div>
      )}
    </div>
  );
}
