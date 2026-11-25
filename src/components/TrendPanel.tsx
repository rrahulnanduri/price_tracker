import { useCallback, useMemo } from "react";
import { motion } from "motion/react";
import { LineChart, Line, ReferenceDot, YAxis, XAxis, Tooltip } from "recharts";
import type { HistoryPoint } from "@/lib/api";
import { historyStats, INK, PAPER, seriesStores, toChartRows } from "@/lib/chart";
import { formatMoney, formatPercent, formatPointLabel, percentChange } from "@/lib/format";
import { useElementSize } from "@/hooks/useElementSize";
import { AnimatedNumber } from "./AnimatedNumber";
import { PanelHeader } from "./Panel";

const AXIS_LINE = { stroke: INK, strokeOpacity: 0.3 };
const TOOLTIP_STYLE = {
  backgroundColor: PAPER,
  borderColor: INK,
  color: INK,
  textTransform: "uppercase",
  fontSize: "10px",
  letterSpacing: "0.1em",
  borderRadius: "0",
} as const;

interface TrendPanelProps {
  /** Observations oldest first; null when there is no search to chart. */
  points: HistoryPoint[] | null;
  currency: string;
  locale: string;
  colors: Record<string, string>;
}

export function TrendPanel({ points, currency, locale, colors }: TrendPanelProps) {
  const [chartRef, chart] = useElementSize<HTMLDivElement>();
  const stores = useMemo(() => seriesStores(points ?? []), [points]);
  const rows = useMemo(
    () => toChartRows(points ?? [], stores, (iso) => formatPointLabel(iso, locale)),
    [points, stores, locale],
  );
  const stats = useMemo(() => historyStats(points ?? []), [points]);

  const count = points?.length ?? 0;
  const hasChart = count > 0 && chart.width > 0 && chart.height > 0;
  const status = count === 0 ? "NO HISTORY" : `${count} CHECK${count === 1 ? "" : "S"} RECORDED`;
  const money = useCallback((value: number) => formatMoney(value, currency, locale), [currency, locale]);
  const percent = useCallback((value: number) => formatPercent(value), []);
  // The cheapest price ever charted, marked on its line.
  const lowestPoint = useMemo(() => {
    let best: { label: string; store: string; value: number } | null = null;
    for (const row of rows) {
      for (const store of stores) {
        const value = row[store];
        if (typeof value === "number" && (!best || value < best.value)) best = { label: row.label, store, value };
      }
    }
    return best;
  }, [rows, stores]);
  const chartKey = `${points?.[0]?.fetched_at ?? ""}|${count}`;

  return (
    <div className="h-full min-h-0 flex flex-col">
      <PanelHeader title="GRAPH.TRENDS" status={status} />

      {stats && (
        <dl className="mb-4 grid grid-cols-3 gap-2 text-[10px] tracking-[0.15em]">
          <div>
            <dt className="opacity-60">NOW</dt>
            <dd className="text-sm font-bold tabular-nums">
              <AnimatedNumber value={stats.latest} format={money} />
            </dd>
          </div>
          <div>
            <dt className="opacity-60">LOWEST SEEN</dt>
            <dd className="text-sm font-bold tabular-nums">
              <AnimatedNumber value={stats.lowest} format={money} />
            </dd>
          </div>
          <div>
            <dt className="opacity-60">SINCE FIRST CHECK</dt>
            <dd className="text-sm font-bold">
              {count > 1 ? (
                <AnimatedNumber value={percentChange(stats.first, stats.latest)} format={percent} />
              ) : (
                "—"
              )}
            </dd>
          </div>
        </dl>
      )}

      <div ref={chartRef} className="flex-1 w-full relative min-h-64 lg:min-h-0">
        {hasChart ? (
          <motion.div
            key={chartKey}
            className="absolute inset-0"
            initial={{ opacity: 0, scale: 0.985 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          >
            <LineChart
              data={rows}
              width={chart.width}
              height={chart.height}
              margin={{ top: 16, right: 16, left: 0, bottom: 0 }}
            >
              <XAxis dataKey="label" stroke={INK} fontSize={10} tickLine={false} axisLine={AXIS_LINE} minTickGap={24} />
              <YAxis
                domain={["auto", "auto"]}
                stroke={INK}
                fontSize={10}
                tickLine={false}
                axisLine={AXIS_LINE}
                width={56}
                tickFormatter={(v: number) => `${Math.round(v)}`}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                itemStyle={{ color: INK }}
                formatter={(value) => (typeof value === "number" ? money(value) : String(value ?? ""))}
              />
              {stores.map((store) => {
                const color = colors[store] ?? INK;
                return (
                  <Line
                    key={store}
                    type="monotone"
                    dataKey={store}
                    stroke={color}
                    strokeWidth={2.5}
                    connectNulls
                    dot={{ fill: PAPER, stroke: color, strokeWidth: 1.5, r: 3 }}
                    activeDot={{ r: 5, fill: color }}
                    animationDuration={1400}
                    animationEasing="ease-out"
                  />
                );
              })}
              {lowestPoint && (
                <ReferenceDot
                  x={lowestPoint.label}
                  y={lowestPoint.value}
                  r={6}
                  fill={PAPER}
                  stroke={colors[lowestPoint.store] ?? INK}
                  strokeWidth={2}
                  className="lowest-dot"
                  label={{ value: "LOWEST", position: "top", fontSize: 9, fill: INK, letterSpacing: "0.15em" }}
                />
              )}
            </LineChart>
          </motion.div>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center border border-ink/20">
            <span className="opacity-40 text-[11px] tracking-[0.3em]">STANDBY</span>
          </div>
        )}
      </div>

      {count === 1 && (
        <p className="mt-3 text-[10px] leading-relaxed tracking-[0.15em] opacity-60">
          FIRST CHECK RECORDED. A TREND APPEARS ONCE THIS PRODUCT HAS BEEN CHECKED AGAIN — TRACK IT TO
          HAVE THAT HAPPEN AUTOMATICALLY.
        </p>
      )}

      {stores.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-x-3 gap-y-1.5 text-[10px] tracking-widest">
          {stores.map((store) => {
            const color = colors[store] ?? INK;
            return (
              <li key={store} className="flex items-center gap-1.5">
                <span className="w-3 h-0.5 rounded-full" style={{ backgroundColor: color }} />
                <span style={{ color }}>{store}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
