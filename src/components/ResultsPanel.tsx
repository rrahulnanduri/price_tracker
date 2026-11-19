import type { ReactNode } from "react";
import { RefreshCw } from "lucide-react";
import type { Offer, SearchResponse } from "@/lib/api";
import { INK } from "@/lib/chart";
import { formatAge, formatMoney } from "@/lib/format";
import { PanelHeader } from "./Panel";
import { PriceLoadingAnimation } from "./PriceLoadingAnimation";

interface ResultsPanelProps {
  data: SearchResponse | null;
  isLoading: boolean;
  colors: Record<string, string>;
  onRefresh: () => void;
  /** Tracking controls, shown under the results. */
  children?: ReactNode;
}

function shippingNote(offer: Offer, currency: string, locale: string): string | null {
  if (offer.shipping_cost === null) return null;
  if (offer.shipping_cost === 0) return "FREE SHIPPING";
  return `INCL. ${formatMoney(offer.shipping_cost, currency, locale)} SHIPPING`;
}

export function ResultsPanel({ data, isLoading, colors, onRefresh, children }: ResultsPanelProps) {
  const results = data?.results ?? [];
  const status = isLoading ? "SCANNING..." : data ? `${results.length} FOUND` : "AWAITING INPUT";

  return (
    <div className="h-full min-h-0 flex flex-col">
      <PanelHeader title="INDEX.RANKING" status={status} />

      <div className="flex-1 min-h-0 flex items-center justify-center">
        {isLoading ? (
          <PriceLoadingAnimation />
        ) : data ? (
          <ol className="flex flex-col gap-3 w-full max-h-full overflow-y-auto custom-scrollbar pr-1">
            {results.map((offer, index) => {
              const shipping = shippingNote(offer, data.currency, data.locale);
              return (
                <li key={offer.store}>
                  <a
                    href={offer.url || undefined}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`p-4 border border-ink/40 backdrop-blur-md transition-colors hover:bg-ink/15 flex flex-col gap-1 animate-in fade-in slide-in-from-bottom-4 duration-500 fill-mode-both ${
                      index === 0 ? "bg-ink/10 shadow-[0_0_15px_rgba(70,73,76,0.15)]" : ""
                    } ${offer.in_stock === false ? "opacity-60" : ""}`}
                    style={{ animationDelay: `${index * 80}ms` }}
                  >
                    <div className="flex justify-between items-center text-[10px] tracking-widest opacity-60">
                      <span>RANK {String(index + 1).padStart(2, "0")}</span>
                      <span className="flex gap-3">
                        {offer.in_stock === false && <span>OUT OF STOCK</span>}
                        {offer.condition !== "new" && <span>{offer.condition}</span>}
                        {index === 0 && offer.in_stock !== false && (
                          <span className="animate-pulse font-semibold">LOWEST ↓</span>
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
                      <span className="text-base font-bold shrink-0" title={`Listed as ${offer.price_text}`}>
                        {formatMoney(offer.total, data.currency, data.locale)}
                      </span>
                    </div>
                    <div className="text-[10px] tracking-wider opacity-60 truncate normal-case" title={offer.title}>
                      {offer.title}
                    </div>
                    <div className="flex justify-between gap-2 text-[10px] tracking-wider opacity-60">
                      <span>{shipping ?? "SHIPPING NOT STATED"}</span>
                      <span title="How closely this listing matches your search">
                        MATCH {Math.round(offer.relevance * 100)}%
                      </span>
                    </div>
                  </a>
                </li>
              );
            })}
          </ol>
        ) : (
          <div className="opacity-40 text-[11px] tracking-[0.3em] py-10">NO DATA</div>
        )}
      </div>

      {data && !isLoading && (
        <div className="mt-4 border-t border-ink/20 pt-3">
          <div className="flex justify-between items-center gap-3 text-[10px] tracking-[0.15em] opacity-70">
            <span className="min-w-0">
              {data.product} · {data.region} · {data.currency}
              <br />
              {data.rejected > 0
                ? `${data.rejected} OF ${data.considered} LISTINGS FILTERED OUT · `
                : ""}
              CHECKED {formatAge(data.fetched_at)}
              {data.provider === "demo" && <strong className="ml-2">· DEMO DATA</strong>}
            </span>
            <button
              type="button"
              onClick={onRefresh}
              aria-label="Check prices again now"
              className="shrink-0 border border-ink/50 p-2 hover:bg-ink hover:text-paper transition-colors cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" aria-hidden />
            </button>
          </div>
          {children}
        </div>
      )}
    </div>
  );
}
