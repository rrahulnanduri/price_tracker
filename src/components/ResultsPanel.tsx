import { useCallback, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { RefreshCw } from "lucide-react";
import type { Offer, SearchResponse, SourceReport } from "@/lib/api";
import { INK } from "@/lib/chart";
import { formatAge, formatMoney } from "@/lib/format";
import { sourceLabel } from "@/lib/sources";
import type { SearchProgress as Progress } from "@/hooks/usePriceSearch";
import { AnimatedNumber } from "./AnimatedNumber";
import { PanelHeader } from "./Panel";
import { SearchProgress } from "./SearchProgress";

interface ResultsPanelProps {
  data: SearchResponse | null;
  isLoading: boolean;
  progress: Progress;
  colors: Record<string, string>;
  onRefresh: () => void;
  /** Tracking controls, shown under the results. */
  children?: ReactNode;
}

const INITIAL_VISIBLE = 8;
const EASE = [0.16, 1, 0.3, 1] as const;

function shippingNote(offer: Offer, currency: string, locale: string): string | null {
  if (offer.shipping_cost === null) return null;
  if (offer.shipping_cost === 0) return "FREE SHIPPING";
  return `INCL. ${formatMoney(offer.shipping_cost, currency, locale)} SHIPPING`;
}

function SourcesLine({ sources }: { sources: SourceReport[] }) {
  if (sources.length === 0) return null;
  return (
    <span>
      SOURCES:{" "}
      {sources.map((source, index) => (
        <span key={source.name} title={source.error ?? `${source.offers} listings`}>
          {index > 0 && " · "}
          {sourceLabel(source.name)} {source.ok ? `✓ ${source.offers}` : "✗ UNAVAILABLE"}
        </span>
      ))}
    </span>
  );
}

export function ResultsPanel({ data, isLoading, progress, colors, onRefresh, children }: ResultsPanelProps) {
  const results = data?.results ?? [];
  // Which search the "show all" choice belongs to, so a new search starts collapsed again.
  const [expandedFor, setExpandedFor] = useState<string | null>(null);
  const searchKey = data ? `${data.product}|${data.country}|${data.fetched_at}` : "";
  const expanded = expandedFor === searchKey;
  const visible = expanded ? results : results.slice(0, INITIAL_VISIBLE);
  const hidden = results.length - visible.length;
  const multiSource = (data?.sources.length ?? 0) > 1;
  const money = useCallback(
    (value: number) => (data ? formatMoney(value, data.currency, data.locale) : String(value)),
    [data],
  );
  const status = isLoading
    ? "SCANNING..."
    : data
      ? `${results.length} STORE${results.length === 1 ? "" : "S"}`
      : "AWAITING INPUT";
  const view = isLoading ? "loading" : data ? `results-${searchKey}` : "empty";

  return (
    <div className="h-full min-h-0 flex flex-col">
      <PanelHeader title="INDEX.RANKING" status={status} />

      <div className="relative flex-1 min-h-0 flex items-center justify-center">
        {/* popLayout: the new view appears at once while the old one fades out over it. */}
        <AnimatePresence mode="popLayout" initial={false}>
          {isLoading ? (
            <motion.div
              key={view}
              className="w-full h-full flex"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, filter: "blur(4px)" }}
              transition={{ duration: 0.25 }}
            >
              <SearchProgress progress={progress} />
            </motion.div>
          ) : data ? (
            <motion.ol
              key={view}
              className="flex flex-col gap-3 w-full max-h-full overflow-y-auto custom-scrollbar pr-1"
              initial={{ opacity: 1 }}
              exit={{ opacity: 0, y: -8, transition: { duration: 0.2 } }}
            >
              <AnimatePresence initial={true}>
                {visible.map((offer, index) => {
                  const shipping = shippingNote(offer, data.currency, data.locale);
                  // Cards revealed by "show all" come in together; the first eight stagger.
                  const delay = index < INITIAL_VISIBLE ? index * 0.06 : (index - INITIAL_VISIBLE) * 0.03;
                  return (
                    <motion.li
                      key={offer.store}
                      layout="position"
                      initial={{ opacity: 0, y: 18, scale: 0.98 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -10, transition: { duration: 0.18 } }}
                      transition={{ duration: 0.5, delay, ease: EASE }}
                    >
                      <motion.a
                        href={offer.url || undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        whileHover={{ y: -2 }}
                        whileTap={{ scale: 0.985 }}
                        transition={{ type: "spring", stiffness: 420, damping: 30 }}
                        className={`p-4 border border-ink/40 backdrop-blur-md transition-[background-color,box-shadow] duration-300 hover:bg-ink/15 hover:shadow-[0_6px_20px_rgba(70,73,76,0.18)] flex flex-col gap-1 ${
                          index === 0 ? "bg-ink/10 shadow-[0_0_15px_rgba(70,73,76,0.15)]" : ""
                        } ${offer.in_stock === false ? "opacity-60" : ""}`}
                      >
                        <div className="flex justify-between items-center text-[10px] tracking-widest opacity-60">
                          <span>RANK {String(index + 1).padStart(2, "0")}</span>
                          <span className="flex gap-3">
                            {offer.in_stock === false && <span>OUT OF STOCK</span>}
                            {offer.condition !== "new" && <span>{offer.condition}</span>}
                            {index === 0 && offer.in_stock !== false && (
                              <motion.span
                                className="font-semibold"
                                initial={{ opacity: 0, x: 6 }}
                                animate={{ opacity: [0, 1, 0.55, 1], x: 0 }}
                                transition={{ duration: 1.4, delay: 0.5 }}
                              >
                                LOWEST ↓
                              </motion.span>
                            )}
                          </span>
                        </div>
                        <div className="flex justify-between items-end gap-2">
                          {/* Store name coloured to match its graph line */}
                          <span
                            className="text-xs tracking-widest truncate font-semibold"
                            style={{ color: colors[offer.store] ?? INK }}
                          >
                            {offer.store}
                          </span>
                          <AnimatedNumber
                            value={offer.total}
                            format={money}
                            className="text-base font-bold shrink-0 tabular-nums"
                            title={`Listed as ${offer.price_text}`}
                          />
                        </div>
                        <div
                          className="text-[10px] tracking-wider opacity-60 truncate normal-case"
                          title={offer.title}
                        >
                          {offer.title}
                        </div>
                        <div className="flex justify-between gap-2 text-[10px] tracking-wider opacity-60">
                          <span>{shipping ?? "SHIPPING NOT STATED"}</span>
                          <span title="How closely this listing matches your search">
                            {multiSource && offer.source && `VIA ${sourceLabel(offer.source)} · `}
                            {offer.extracted_by === "ai" && "AI-READ · "}
                            MATCH {Math.round(offer.relevance * 100)}%
                          </span>
                        </div>
                      </motion.a>
                    </motion.li>
                  );
                })}
              </AnimatePresence>
              {results.length > INITIAL_VISIBLE && (
                <motion.li layout="position" transition={{ duration: 0.4, ease: EASE }}>
                  <motion.button
                    type="button"
                    onClick={() => setExpandedFor(expanded ? null : searchKey)}
                    whileTap={{ scale: 0.98 }}
                    className="w-full border border-ink/50 py-2 tracking-[0.2em] text-[10px] hover:bg-ink hover:text-paper transition-colors cursor-pointer"
                  >
                    {expanded ? "SHOW FEWER" : `SHOW ALL ${results.length} STORES (+${hidden})`}
                  </motion.button>
                </motion.li>
              )}
            </motion.ol>
          ) : (
            <motion.div
              key={view}
              className="opacity-40 text-[11px] tracking-[0.3em] py-10"
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.4 }}
              exit={{ opacity: 0 }}
            >
              NO DATA
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {data && !isLoading && (
          <motion.div
            key={searchKey}
            className="mt-4 border-t border-ink/20 pt-3"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.45, delay: 0.25, ease: EASE }}
          >
            <div className="flex justify-between items-center gap-3 text-[10px] tracking-[0.15em] opacity-70">
              <span className="min-w-0">
                {data.product} · {data.region} · {data.currency}
                <br />
                {data.rejected > 0 ? `${data.rejected} OF ${data.considered} LISTINGS FILTERED OUT · ` : ""}
                CHECKED {formatAge(data.fetched_at)}
                <br />
                <SourcesLine sources={data.sources} />
                {data.provider === "demo" && (
                  <strong
                    className="ml-2"
                    title="Prices are made up for testing. Links open each store's real search for this product."
                  >
                    · DEMO DATA: PRICES MADE UP, LINKS GO TO STORE SEARCH
                  </strong>
                )}
                {(data.ai_extracted || data.ai_changed !== null) && (
                  <>
                    <br />
                    <span title="An AI model helped with this search; prices are always taken from the page text">
                      {data.ai_extracted ? "READ BY AI (LAYOUT NOT RECOGNISED)" : "AI-CHECKED MATCHES"}
                      {data.ai_changed ? ` · ${data.ai_changed} CORRECTED` : ""}
                    </span>
                  </>
                )}
              </span>
              <motion.button
                type="button"
                onClick={onRefresh}
                aria-label="Check prices again now"
                whileHover={{ rotate: 90 }}
                whileTap={{ scale: 0.9, rotate: 180 }}
                transition={{ type: "spring", stiffness: 300, damping: 18 }}
                className="shrink-0 border border-ink/50 p-2 hover:bg-ink hover:text-paper transition-colors cursor-pointer"
              >
                <RefreshCw className="w-3.5 h-3.5" aria-hidden />
              </motion.button>
            </div>
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
