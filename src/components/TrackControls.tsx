import { useState, type FormEvent } from "react";
import type { Watch } from "@/lib/api";
import { formatMoney, parseTarget } from "@/lib/format";

interface TrackControlsProps {
  watch: Watch | undefined;
  currency: string;
  locale: string;
  refreshHours: number;
  onTrack: (target: number | null) => void;
  onSetTarget: (watch: Watch, target: number | null) => void;
  onUntrack: (watch: Watch) => void;
}

/** Add the current search to the watchlist, with an optional price to be alerted at. */
export function TrackControls({
  watch, currency, locale, refreshHours, onTrack, onSetTarget, onUntrack,
}: TrackControlsProps) {
  const [draft, setDraft] = useState("");
  const [invalid, setInvalid] = useState(false);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const target = parseTarget(draft);
    if (draft.trim() && target === null) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    if (watch) onSetTarget(watch, target);
    else onTrack(target);
    setDraft("");
  };

  const cadence = refreshHours > 0 ? `RE-CHECKED EVERY ${refreshHours} H` : "AUTO RE-CHECK IS OFF";

  return (
    <form onSubmit={handleSubmit} className="mt-3 border border-ink/40 p-3 text-[10px] tracking-[0.15em]">
      <div className="flex justify-between gap-2 mb-2">
        <span className="font-semibold">{watch ? "● TRACKING" : "TRACK THIS PRODUCT"}</span>
        <span className="opacity-60 text-right">
          {watch
            ? watch.target_price !== null
              ? `ALERT AT ${formatMoney(watch.target_price, currency, locale)}`
              : "NO ALERT PRICE"
            : cadence}
        </span>
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          inputMode="decimal"
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            setInvalid(false);
          }}
          placeholder={`ALERT PRICE (${currency}, OPTIONAL)`}
          aria-label={`Alert price in ${currency}`}
          aria-invalid={invalid}
          className={`flex-1 min-w-0 bg-ink/10 border px-2 py-1.5 outline-none placeholder:text-ink/50 tracking-[0.12em] ${
            invalid ? "border-red-900" : "border-ink/50 focus-visible:border-ink"
          }`}
        />
        <button
          type="submit"
          className="border border-ink px-3 hover:bg-ink hover:text-paper transition-colors cursor-pointer tracking-[0.15em]"
        >
          {watch ? "SAVE" : "TRACK"}
        </button>
        {watch && (
          <button
            type="button"
            onClick={() => onUntrack(watch)}
            className="border border-ink/50 px-3 opacity-70 hover:opacity-100 hover:bg-ink hover:text-paper transition-colors cursor-pointer tracking-[0.15em]"
          >
            STOP
          </button>
        )}
      </div>
      {invalid && (
        <div role="alert" className="mt-2 text-red-900 normal-case tracking-wider">
          Enter a price above zero, or leave it empty.
        </div>
      )}
    </form>
  );
}
