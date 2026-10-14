// Small hand-built SVG charts for the Dashboard. No chart library.
// Colours per account come from chartColors.js.
import { useEffect, useRef, useState } from "react";
import { compact } from "../api";

export function Legend({ items }) {
  return (
    <ul className="legend">
      {items.map((i) => (
        <li key={i.name}><span className="swatch" style={{ background: i.color }} />{i.name}{i.is_us ? " (you)" : ""}</li>
      ))}
    </ul>
  );
}

// Tooltip that follows the pointer inside a chart box.
function useTip() {
  const box = useRef(null);
  const [tip, setTip] = useState(null);
  const show = (e, content) => {
    const r = box.current?.getBoundingClientRect();
    if (!r) return;
    setTip({ x: e.clientX - r.left, y: e.clientY - r.top, w: r.width, content });
  };
  const el = tip && (
    <div className="chart-tip" role="status" style={{ left: Math.min(tip.x + 12, tip.w - 190), top: tip.y + 14 }}>{tip.content}</div>
  );
  return { box, show, hide: () => setTip(null), el };
}

// Horizontal bars with the value at the tip. rows: [{name, value, color, label, sub}]
export function BarList({ rows, format = (v) => compact(v), max }) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.value || 0));
  const t = useTip();
  return (
    <div className="barlist" ref={t.box} onMouseLeave={t.hide}>
      {rows.map((r) => (
        <div className="barlist-row" key={r.name}
          onMouseMove={(e) => t.show(e, <><b>{r.name}</b><span>{r.tip || format(r.value)}</span></>)}>
          <span className="barlist-name" title={r.name}>{r.name}{r.is_us && <span className="you-tag">you</span>}</span>
          <span className="barlist-track">
            <span className="barlist-bar" style={{ width: `${Math.max(((r.value || 0) / top) * 100, r.value ? 1.5 : 0)}%`, background: r.color }} />
            <span className="barlist-val">{r.label ?? format(r.value)}</span>
          </span>
        </div>
      ))}
      {t.el}
    </div>
  );
}

// Grouped columns over time (one group per bucket, one column per series).
export function ColumnChart({ buckets, series, colors, labelOf, height = 220 }) {
  const t = useTip();
  const W = useWidth(t.box, 640), H = height, padL = 32, padB = 22, padT = 8;
  const max = Math.max(1, ...series.flatMap((s) => s.values));
  const ticks = niceTicks(max);
  const top = ticks[ticks.length - 1];
  const groupW = (W - padL) / buckets.length;
  const colW = Math.min(14, (groupW - 8) / series.length - 2);
  const y = (v) => padT + (H - padB - padT) * (1 - v / top);
  return (
    <div className="chart-box" ref={t.box} onMouseLeave={t.hide}>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart-svg" role="img" aria-label="Posts over time per account">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={padL} x2={W} y1={y(v)} y2={y(v)} className="grid" />
            <text x={padL - 6} y={y(v) + 4} className="axis" textAnchor="end">{compact(v)}</text>
          </g>
        ))}
        {buckets.map((b, i) => {
          const gx = padL + i * groupW + (groupW - series.length * (colW + 2)) / 2;
          return (
            <g key={b}
              onMouseMove={(e) => t.show(e, <><b>{labelOf(b)}</b>{series.map((s) => <span key={s.name}><i className="swatch" style={{ background: colors[s.name] }} />{s.name}: {s.values[i]}</span>)}</>)}>
              <rect x={padL + i * groupW} y={padT} width={groupW} height={H - padB - padT} className="hit" />
              {series.map((s, j) => {
                const v = s.values[i];
                const h = (H - padB) - y(v);
                return v > 0 ? <path key={s.name} d={roundedTop(gx + j * (colW + 2), y(v), colW, h)} fill={colors[s.name]} /> : null;
              })}
              <text x={padL + i * groupW + groupW / 2} y={H - 6} className="axis" textAnchor="middle">{labelOf(b)}</text>
            </g>
          );
        })}
      </svg>
      {t.el}
    </div>
  );
}

// You vs competitors share per category, as paired bars. rows: [{label, ours, theirs}]
export function PairedBars({ rows, oursLabel = "You", theirsLabel = "Competitors" }) {
  const t = useTip();
  return (
    <div className="paired" ref={t.box} onMouseLeave={t.hide}>
      {rows.map((r) => (
        <div className="paired-row" key={r.label}
          onMouseMove={(e) => t.show(e, <><b>{r.label}</b><span>{oursLabel}: {r.ours}%{r.oursN != null ? ` (${r.oursN})` : ""}</span><span>{theirsLabel}: {r.theirs}%{r.theirsN != null ? ` (${r.theirsN})` : ""}</span></>)}>
          <span className="paired-label">{r.label}</span>
          <span className="paired-bars">
            <span className="barlist-track"><span className="barlist-bar" style={{ width: `${r.ours}%`, background: "var(--series-1)" }} /><span className="barlist-val">{r.ours}%</span></span>
            <span className="barlist-track"><span className="barlist-bar" style={{ width: `${r.theirs}%`, background: "var(--series-muted)" }} /><span className="barlist-val">{r.theirs}%</span></span>
          </span>
        </div>
      ))}
      {t.el}
    </div>
  );
}

// Weekday × time-of-day grid. Sequential single hue: darker = posts did better than usual.
export function Heatmap({ data }) {
  const t = useTip();
  const vals = data.grid.map((c) => c.median_relative).filter((v) => v != null);
  const lo = Math.min(...vals, 1), hi = Math.max(...vals, 1.0001);
  const step = (v) => (v == null ? null : Math.round(((v - lo) / (hi - lo)) * 5));
  return (
    <div className="heat" ref={t.box} onMouseLeave={t.hide}>
      <div className="heat-grid" style={{ gridTemplateColumns: `72px repeat(${data.days.length}, 1fr)` }}>
        <span />
        {data.days.map((d) => <span key={d} className="heat-head">{d}</span>)}
        {data.slots.map((sl) => (
          <HeatRow key={sl} slot={sl} data={data} step={step} t={t} />
        ))}
      </div>
      <div className="heat-scale"><span>Below usual</span>{[0, 1, 2, 3, 4, 5].map((i) => <i key={i} className={`h${i}`} />)}<span>Above usual</span><span className="muted"> · blank = too few posts</span></div>
      {t.el}
    </div>
  );
}

function HeatRow({ slot, data, step, t }) {
  return (
    <>
      <span className="heat-slot">{slot}</span>
      {data.days.map((d) => {
        const c = data.grid.find((x) => x.day === d && x.slot === slot);
        const s = step(c.median_relative);
        return (
          <span key={d} className={`heat-cell ${s == null ? "empty" : `h${s}`}`}
            onMouseMove={(e) => t.show(e, <><b>{d} · {slot}</b><span>{c.posts} competitor post{c.posts === 1 ? "" : "s"}</span><span>{c.median_relative != null ? `${c.median_relative}× their usual (median of ${c.sample})` : "Too few measured posts"}</span></>)}>
            {c.median_relative != null ? `${c.median_relative}×` : ""}
          </span>
        );
      })}
    </>
  );
}

export function Sparkline({ points, width = 96, height = 28 }) {
  if (!points || points.length < 2) return null;
  const vals = points.map((p) => p.value);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const span = hi - lo || 1;
  const d = vals.map((v, i) => `${i ? "L" : "M"}${(i / (vals.length - 1)) * (width - 4) + 2},${height - 3 - ((v - lo) / span) * (height - 6)}`).join(" ");
  const last = vals.length - 1;
  return (
    <svg width={width} height={height} className="spark" aria-hidden="true">
      <path d={d} fill="none" stroke="var(--series-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={width - 2} cy={height - 3 - ((vals[last] - lo) / span) * (height - 6)} r="3" fill="var(--series-1)" />
    </svg>
  );
}

// The chart is drawn at its real pixel width, so text stays the same size on every screen.
function useWidth(ref, fallback) {
  const [w, setW] = useState(fallback);
  useEffect(() => {
    if (!ref.current) return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

function niceTicks(max) {
  const raw = max / 4;
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) || mag;
  const out = [];
  for (let v = 0; v <= max + step - 0.0001; v += step) out.push(Math.round(v * 100) / 100);
  return out.length > 1 ? out : [0, 1];
}

// A column with a 4px rounded top and a square base.
function roundedTop(x, y, w, h) {
  const r = Math.min(4, w / 2, h);
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`;
}
