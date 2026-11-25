import { AnimatePresence, motion } from "motion/react";
import { Check, X } from "lucide-react";
import { progressFraction, type SearchProgress as Progress } from "@/hooks/usePriceSearch";
import { sourceLabel } from "@/lib/sources";

const STAGE_LABEL = {
  fetching: "ASKING SOURCES",
  matching: "MATCHING PRODUCTS",
  ai_review: "AI CHECKING MATCHES",
} as const;

const EASE = [0.16, 1, 0.3, 1] as const;

/** The loader: real progress per source, then placeholder cards shaped like the results. */
export function SearchProgress({ progress }: { progress: Progress }) {
  const fraction = progressFraction(progress);
  const sources = progress.sources ?? [];
  const answered = sources.filter((s) => s.status !== "pending").length;

  return (
    <div className="w-full self-start" role="status" aria-live="polite">
      <div className="flex justify-between items-baseline text-[10px] tracking-[0.25em] mb-2">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={progress.stage}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.25 }}
          >
            [ {STAGE_LABEL[progress.stage]} ]
          </motion.span>
        </AnimatePresence>
        <span className="opacity-60 tabular-nums">{Math.round(fraction * 100)}%</span>
      </div>

      <div className="relative h-1 w-full overflow-hidden bg-ink/15" aria-hidden>
        <motion.div
          className="absolute inset-y-0 left-0 bg-ink"
          initial={{ width: "0%" }}
          animate={{ width: `${fraction * 100}%` }}
          transition={{ duration: 0.6, ease: EASE }}
        />
        <div className="progress-sheen absolute inset-0" />
      </div>

      <ul className="mt-4 flex flex-col gap-1.5 text-[10px] tracking-[0.18em]">
        <AnimatePresence initial={false}>
          {sources.map((source, index) => (
            <motion.li
              key={source.name}
              layout
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.35, delay: index * 0.06, ease: EASE }}
              className="flex items-center justify-between gap-3"
            >
              <span className="flex items-center gap-2">
                <SourceIcon status={source.status} />
                {sourceLabel(source.name)}
              </span>
              <span className="opacity-60 text-right truncate" title={source.error ?? undefined}>
                {source.status === "pending" && "CHECKING…"}
                {source.status === "done" && `${source.offers} LISTING${source.offers === 1 ? "" : "S"}`}
                {source.status === "failed" && "UNAVAILABLE"}
              </span>
            </motion.li>
          ))}
        </AnimatePresence>
        {sources.length === 0 && <li className="opacity-60">CONNECTING…</li>}
      </ul>
      {sources.length > 1 && (
        <div className="sr-only">
          {answered} of {sources.length} sources answered
        </div>
      )}

      <ul className="mt-6 flex flex-col gap-3" aria-hidden>
        {[0, 1, 2].map((i) => (
          <motion.li
            key={i}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1 - i * 0.25, y: 0 }}
            transition={{ duration: 0.5, delay: 0.15 + i * 0.1, ease: EASE }}
            className="skeleton-card border border-ink/25 p-4 flex flex-col gap-2.5"
          >
            <div className="flex justify-between">
              <span className="skeleton h-2 w-14" />
              <span className="skeleton h-2 w-10" />
            </div>
            <div className="flex justify-between items-end">
              <span className="skeleton h-3 w-28" />
              <span className="skeleton h-4 w-16" />
            </div>
            <span className="skeleton h-2 w-3/4" />
          </motion.li>
        ))}
      </ul>
    </div>
  );
}

function SourceIcon({ status }: { status: "pending" | "done" | "failed" }) {
  return (
    <span className="relative w-3 h-3 inline-flex items-center justify-center" aria-hidden>
      <AnimatePresence mode="wait" initial={false}>
        {status === "pending" ? (
          <motion.span
            key="pending"
            className="w-2.5 h-2.5 border border-ink border-t-transparent rounded-full"
            animate={{ rotate: 360 }}
            exit={{ opacity: 0, scale: 0.5 }}
            transition={{ rotate: { repeat: Infinity, duration: 0.8, ease: "linear" } }}
          />
        ) : (
          <motion.span
            key={status}
            initial={{ opacity: 0, scale: 0.4 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ type: "spring", stiffness: 500, damping: 22 }}
          >
            {status === "done" ? <Check className="w-3 h-3" strokeWidth={3} /> : <X className="w-3 h-3" strokeWidth={3} />}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}
