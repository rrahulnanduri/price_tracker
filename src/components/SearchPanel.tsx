import type { FormEvent } from "react";
import { Search } from "lucide-react";
import type { Region } from "@/lib/api";

interface SearchPanelProps {
  query: string;
  onQueryChange: (query: string) => void;
  country: string;
  regions: Region[];
  onCountryChange: (country: string) => void;
  isLoading: boolean;
  error: string | null;
  onSearch: () => void;
}

export function SearchPanel({
  query, onQueryChange, country, regions, onCountryChange, isLoading, error, onSearch,
}: SearchPanelProps) {
  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    onSearch();
  };

  return (
    <div className="w-full">
      <h1 className="mb-4 tracking-[0.2em] text-[11px] text-center opacity-70">[ SYSTEM.SEARCH ]</h1>

      <form onSubmit={handleSubmit} className="w-full">
        <div className="backdrop-blur-md bg-ink/10 border border-ink flex items-center p-3 transition-colors focus-within:bg-ink/20">
          <Search className="w-4 h-4 shrink-0 mr-3" aria-hidden />
          <input
            type="search"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="PRODUCT NAME..."
            aria-label="Product name"
            maxLength={200}
            enterKeyHint="search"
            className="flex-1 min-w-0 bg-transparent border-none outline-none placeholder:text-ink/50 uppercase tracking-widest text-xs"
          />
        </div>

        <label className="mt-3 flex items-center justify-between gap-3 text-[10px] tracking-[0.15em]">
          <span className="opacity-60">REGION</span>
          <select
            value={country}
            onChange={(e) => onCountryChange(e.target.value)}
            aria-label="Shopping region"
            className="flex-1 min-w-0 bg-ink/10 border border-ink/50 px-2 py-1.5 uppercase tracking-[0.12em] text-[10px] outline-none focus-visible:border-ink cursor-pointer"
          >
            {regions.length === 0 && <option value={country}>{country}</option>}
            {regions.map((r) => (
              <option key={r.code} value={r.code}>
                {r.label} · {r.currency}
              </option>
            ))}
          </select>
        </label>

        <button
          type="submit"
          disabled={isLoading || !query.trim()}
          className="mt-4 w-full border border-ink bg-transparent hover:bg-ink hover:text-paper disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-ink py-2.5 tracking-[0.2em] transition-colors cursor-pointer disabled:cursor-not-allowed"
        >
          {isLoading ? "SCANNING..." : "EXECUTE"}
        </button>
      </form>

      {error && (
        <div
          role="alert"
          className="mt-4 text-[10px] leading-relaxed tracking-widest text-red-900 border border-red-900/50 bg-red-900/5 p-2.5 text-center normal-case"
        >
          {error}
        </div>
      )}
    </div>
  );
}
