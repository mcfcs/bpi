"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ChartBar, ChartSpec } from "@/lib/types";
import { fmtValue, monthYear, n } from "@/lib/format";
import { TierBadge } from "./Citation";

type Datum = ChartBar & { tipLabel: string };

interface ValueLabelProps {
  x?: number | string;
  y?: number | string;
  width?: number | string;
  height?: number | string;
  value?: number | string | boolean | null;
}

interface TickProps {
  x?: number | string;
  y?: number | string;
  index?: number;
  payload?: { value: string };
}

function useNarrow(breakpoint = 560): boolean {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const query = window.matchMedia(`(max-width: ${breakpoint}px)`);
    const update = () => setNarrow(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, [breakpoint]);
  return narrow;
}

function axis(max: number, unit: string): { top: number; ticks: number[] } {
  const padded = max * 1.12;
  const step = padded > 50 ? 20 : 10;
  const top = unit === "%" ? Math.min(100, Math.ceil(padded / step) * step) : Math.ceil(padded / step) * step;
  const ticks: number[] = [];
  for (let t = 0; t <= top; t += step) ticks.push(t);
  return { top, ticks };
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: ReadonlyArray<{ payload?: Datum }> }) {
  const bar = payload?.[0]?.payload;
  if (!active || !bar) return null;
  return (
    <div className="chart-tooltip">
      <strong>{fmtValue(bar.value, bar.unit)}</strong> <span className="muted">base n={n(bar.base_n)}</span>
      <div>{bar.label}</div>
      {bar.disputed && <div className="flag-text">Studies differ; an S&amp;I analyst is checking this figure.</div>}
      <div className="muted">
        {bar.study_code} · Tier {bar.tier ?? "not set"} · {bar.region_label} · fieldwork ended {monthYear(bar.fieldwork_end)}
      </div>
      <div className="muted">{bar.study_title}</div>
    </div>
  );
}

/** Horizontal bars, one per study or subgroup, sorted by value; numbers come from the database. */
export function MetricChart({ chart }: { chart: ChartSpec }) {
  const narrow = useNarrow();
  const [showTable, setShowTable] = useState(false);
  // A disputed bar says so in its row label, not only by its style, so the table and screen readers carry it too.
  const data: Datum[] = chart.bars.map((b) => ({
    ...b,
    detail: b.disputed ? `${b.detail} · S&I checking` : b.detail,
    tipLabel: `${fmtValue(b.value, b.unit)} · n=${n(b.base_n)} · ${b.tier ?? "–"}`,
  }));
  const anyDisputed = data.some((d) => d.disputed);
  const { top, ticks } = axis(Math.max(...data.map((d) => d.value)), chart.unit);
  // Size the label column to the longest label (bounded) so long groups are not clipped.
  const longest = Math.max(...data.map((d) => Math.max(d.label.length, (d.detail ?? "").length)));
  const labelWidth = Math.round(Math.min(narrow ? 170 : 280, Math.max(narrow ? 124 : 168, (narrow ? 22 : longest) * 6.6 + 16)));
  const rowHeight = narrow ? 58 : 46;
  const summary = data
    .map((d) => `${d.label}: ${fmtValue(d.value, d.unit)}, base ${n(d.base_n)}, tier ${d.tier}${d.disputed ? ", studies differ, S&I checking" : ""}`)
    .join("; ");

  // Row label: the group on one line (two on narrow screens, split at the comma), study and year below.
  const renderTick = ({ x, y, index, payload }: TickProps) => {
    const datum = index != null ? data[index] : undefined;
    const label = datum?.label ?? payload?.value ?? "";
    const cut = label.indexOf(", ");
    const space = label.lastIndexOf(" ", Math.ceil(label.length / 2));
    const lines = !narrow ? [label]
      : cut > 0 ? [label.slice(0, cut + 1), label.slice(cut + 2)]
      : label.length > 22 && space > 0 ? [label.slice(0, space), label.slice(space + 1)] : [label];
    const top = -2 - (lines.length - 1) * 13;
    return (
      <g transform={`translate(${Number(x) - 8},${Number(y)})`}>
        <text textAnchor="end" fill="var(--ink)" fontSize={12} fontFamily="var(--sans)">
          {lines.map((line, i) => (
            <tspan key={i} x={0} dy={i === 0 ? top : 13}>{line}</tspan>
          ))}
        </text>
        <text textAnchor="end" fill={datum?.disputed ? "var(--flag)" : "var(--muted)"} fontSize={11} fontFamily="var(--sans)" dy={12}>
          {datum?.detail}
        </text>
      </g>
    );
  };

  // Value, base n and tier at the bar tip, on one line (never wrapped or clipped by the bar).
  const renderValue = ({ x, y, width, height, value }: ValueLabelProps) => (
    <text
      x={Number(x) + Number(width) + 8}
      y={Number(y) + Number(height) / 2}
      dy={4}
      fill="var(--ink)"
      fontSize={narrow ? 11.5 : 12}
      fontFamily="var(--sans)"
    >
      {String(value ?? "")}
    </text>
  );

  return (
    <figure className="chart" style={{ margin: "8px 0 20px" }}>
      <figcaption>
        <p className="chart-title">{chart.title}</p>
        <p className="chart-sub">
          {chart.unit === "%" ? "Share of respondents (%)" : "Score"}. Each bar uses its own study&apos;s base; labels
          show value, base n and robustness tier.
        </p>
        {anyDisputed && (
          <p className="chart-sub flag-text">
            Bars marked &ldquo;S&amp;I checking&rdquo; come from studies that found different results for the same group; neither is
            settled yet.
          </p>
        )}
      </figcaption>
      <div className="chart-plot" style={{ width: "100%", height: data.length * rowHeight + 34 }} role="img" aria-label={`${chart.title}. ${summary}`}>
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: narrow ? 122 : 138, bottom: 4, left: 0 }} barCategoryGap={12}>
            <CartesianGrid horizontal={false} stroke="var(--rule)" strokeWidth={1} />
            <XAxis
              type="number"
              domain={[0, top]}
              ticks={ticks}
              interval="preserveStartEnd"
              tickFormatter={(v: number) => (chart.unit === "%" ? `${v}%` : String(v))}
              tick={{ fill: "var(--muted)", fontSize: 11, fontFamily: "var(--sans)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--rule)" }}
            />
            <YAxis type="category" dataKey="finding_id" width={labelWidth} tick={renderTick} tickLine={false} axisLine={{ stroke: "var(--rule)" }} interval={0} />
            <Tooltip
              cursor={{ fill: "var(--rule)", fillOpacity: 0.3 }}
              content={(props) => <ChartTooltip active={props.active} payload={props.payload as ReadonlyArray<{ payload?: Datum }>} />}
              isAnimationActive={false}
            />
            <Bar dataKey="value" fill="var(--link)" barSize={18} radius={[0, 4, 4, 0]} isAnimationActive={false}>
              {data.map((d) => (
                <Cell
                  key={d.finding_id}
                  fill="var(--link)"
                  fillOpacity={d.disputed ? 0.35 : 1}
                  stroke={d.disputed ? "var(--flag)" : undefined}
                  strokeWidth={d.disputed ? 1.5 : 0}
                  strokeDasharray={d.disputed ? "4 3" : undefined}
                />
              ))}
              <LabelList dataKey="tipLabel" content={renderValue} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <button type="button" className="btn btn-quiet small no-print" aria-expanded={showTable} onClick={() => setShowTable((s) => !s)}>
        {showTable ? "Hide table" : "Show as table"}
      </button>
      {/* Always rendered: on paper the table replaces the chart, which cannot reflow to the page. */}
      {(
        <div className={`table-wrap chart-table${showTable ? "" : " print-only"}`}>
          <table>
            <caption className="visually-hidden">{chart.title}</caption>
            <thead>
              <tr>
                <th>Group</th>
                <th className="num">Value</th>
                <th>Study</th>
                <th>Tier</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.finding_id}>
                  <td>
                    {d.label}
                    {d.disputed && <span className="chip chip-flag disputed-tag">S&amp;I checking</span>}
                  </td>
                  <td className="num">{fmtValue(d.value, d.unit)}</td>
                  <td>
                    <span className="code">{d.study_code}</span> <span className="muted">{d.study_title}</span>
                  </td>
                  <td>
                    <TierBadge tier={d.tier} sample={`n=${n(d.base_n)}`} when={d.fieldwork_end?.slice(0, 4) ?? "n.d."} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </figure>
  );
}
