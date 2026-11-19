import type { HistoryPoint } from "./api";

export const INK = "#46494C";
export const PAPER = "#9B9987";

const MIN_HUE_GAP = 28;
const MAX_SERIES = 6;

function hash(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) >>> 0;
  return h;
}

/**
 * One colour per store, derived from its name so a store keeps its colour
 * between searches. Hues that land too close to one already taken are nudged.
 */
export function assignColors(stores: string[]): Record<string, string> {
  const taken: number[] = [];
  const colors: Record<string, string> = {};
  for (const store of stores) {
    let hue = hash(store) % 360;
    for (let tries = 0; tries < 12; tries++) {
      const clash = taken.some((t) => Math.min(Math.abs(t - hue), 360 - Math.abs(t - hue)) < MIN_HUE_GAP);
      if (!clash) break;
      hue = (hue + MIN_HUE_GAP + 9) % 360;
    }
    taken.push(hue);
    colors[store] = `hsl(${hue}, 62%, 34%)`;
  }
  return colors;
}

export type ChartRow = { label: string; fetched_at: string } & Record<string, string | number>;

/** Stores worth a line: those in the latest observation, cheapest first, capped. */
export function seriesStores(points: HistoryPoint[]): string[] {
  const latest = points[points.length - 1];
  if (!latest) return [];
  return Object.entries(latest.stores)
    .sort(([, a], [, b]) => a - b)
    .slice(0, MAX_SERIES)
    .map(([store]) => store);
}

export function toChartRows(
  points: HistoryPoint[],
  stores: string[],
  label: (iso: string) => string,
): ChartRow[] {
  return points.map((point) => {
    const row: ChartRow = { label: label(point.fetched_at), fetched_at: point.fetched_at };
    for (const store of stores) {
      if (store in point.stores) row[store] = point.stores[store];
    }
    return row;
  });
}

export interface HistoryStats {
  lowest: number;
  highest: number;
  first: number;
  latest: number;
}

/** Stats over the cheapest price at each observation. */
export function historyStats(points: HistoryPoint[]): HistoryStats | null {
  if (points.length === 0) return null;
  const lows = points.map((p) => p.lowest);
  return {
    lowest: Math.min(...lows),
    highest: Math.max(...lows),
    first: lows[0],
    latest: lows[lows.length - 1],
  };
}
