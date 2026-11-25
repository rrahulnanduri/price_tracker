import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";
import type { Region, Watch } from "@/lib/api";
import { formatAge, formatMoney, formatPercent, percentChange } from "@/lib/format";

interface WatchlistProps {
  items: Watch[];
  regions: Region[];
  error: string | null;
  activeId: number | null;
  onOpen: (watch: Watch) => void;
  onRemove: (watch: Watch) => void;
}

export function Watchlist({ items, regions, error, activeId, onOpen, onRemove }: WatchlistProps) {
  const localeOf = (country: string) => regions.find((r) => r.code === country)?.locale;

  return (
    <div className="w-full mt-8 min-h-0 flex flex-col">
      <div className="mb-3 tracking-[0.2em] text-[11px] border-b border-ink/30 pb-3 flex justify-between">
        <h2>[ WATCHLIST ]</h2>
        <span className="opacity-60">{items.length} TRACKED</span>
      </div>

      {error && (
        <div role="alert" className="mb-2 text-[10px] tracking-wider text-red-900 normal-case">
          {error}
        </div>
      )}

      {items.length === 0 ? (
        <p className="text-[10px] leading-relaxed tracking-[0.15em] opacity-50">
          SEARCH A PRODUCT, THEN PRESS TRACK TO RE-CHECK ITS PRICE AUTOMATICALLY.
        </p>
      ) : (
        <ul className="flex flex-col gap-2 overflow-y-auto overflow-x-hidden custom-scrollbar pr-1 min-h-0 lg:max-h-[38vh]">
          <AnimatePresence initial={false}>
          {items.map((watch) => {
            const change =
              watch.latest_price !== null && watch.previous_price !== null
                ? percentChange(watch.previous_price, watch.latest_price)
                : null;
            return (
              <motion.li
                layout
                initial={{ opacity: 0, height: 0, y: -6 }}
                animate={{ opacity: 1, height: "auto", y: 0 }}
                exit={{ opacity: 0, height: 0, x: 24, transition: { duration: 0.22 } }}
                transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                key={watch.id}
                className={`border flex items-stretch transition-colors ${
                  watch.target_hit ? "border-ink bg-ink/15" : "border-ink/40"
                } ${activeId === watch.id ? "bg-ink/10" : ""}`}
              >
                <button
                  type="button"
                  onClick={() => onOpen(watch)}
                  className="flex-1 min-w-0 text-left p-2.5 hover:bg-ink/10 cursor-pointer"
                >
                  <div className="flex justify-between gap-2 text-[11px] tracking-widest font-semibold">
                    <span className="truncate">{watch.product}</span>
                    <span className="shrink-0">
                      {watch.latest_price !== null && watch.currency
                        ? formatMoney(watch.latest_price, watch.currency, localeOf(watch.country))
                        : "—"}
                    </span>
                  </div>
                  <div className="mt-1 flex justify-between gap-2 text-[10px] tracking-wider opacity-60">
                    <span className="truncate">
                      {watch.country}
                      {watch.latest_store ? ` · ${watch.latest_store}` : ""}
                      {watch.last_checked_at ? ` · ${formatAge(watch.last_checked_at)}` : " · NOT CHECKED YET"}
                    </span>
                    {change !== null && Math.abs(change) >= 0.05 && (
                      <span className="shrink-0">{formatPercent(change)}</span>
                    )}
                  </div>
                  {watch.target_price !== null && watch.currency && (
                    <div className="mt-1 text-[10px] tracking-wider">
                      {watch.target_hit ? (
                        <motion.span
                          className="font-bold inline-block"
                          animate={{ opacity: [1, 0.45, 1] }}
                          transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
                        >
                          ● TARGET HIT · {formatMoney(watch.target_price, watch.currency, localeOf(watch.country))}
                        </motion.span>
                      ) : (
                        <span className="opacity-60">
                          TARGET {formatMoney(watch.target_price, watch.currency, localeOf(watch.country))}
                        </span>
                      )}
                    </div>
                  )}
                  {watch.last_error && (
                    <div className="mt-1 text-[10px] tracking-wider text-red-900 normal-case truncate">
                      Last check failed: {watch.last_error}
                    </div>
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => onRemove(watch)}
                  aria-label={`Stop tracking ${watch.product}`}
                  className="px-2.5 border-l border-ink/30 opacity-60 hover:opacity-100 hover:bg-ink hover:text-paper cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" aria-hidden />
                </button>
              </motion.li>
            );
          })}
          </AnimatePresence>
        </ul>
      )}
    </div>
  );
}
