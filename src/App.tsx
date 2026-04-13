import { useState, useRef, useEffect, useMemo } from "react";
import { LineChart, Line, YAxis, XAxis, Tooltip } from "recharts";
import { Search } from "lucide-react";
import { PriceLoadingAnimation } from "./components/PriceLoadingAnimation";

interface PriceResult {
  store: string;
  title: string;
  price: number;
  price_text: string;
  url: string;
}

interface SearchResponse {
  product: string;
  region: string;
  currency: string;
  results: PriceResult[];
}

// Detect country from browser timezone
function detectCountry(): string {
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (tz.startsWith("America/")) return "US";
  if (tz.startsWith("Europe/London")) return "GB";
  if (tz.startsWith("Asia/Kolkata") || tz.startsWith("Asia/Calcutta")) return "IN";
  if (tz.startsWith("Europe/Berlin") || tz.startsWith("Europe/Vienna")) return "DE";
  if (tz.startsWith("Europe/Paris")) return "FR";
  if (tz.startsWith("Australia/")) return "AU";
  if (tz.startsWith("America/Toronto") || tz.startsWith("America/Vancouver")) return "CA";
  if (tz.startsWith("Asia/Tokyo")) return "JP";
  if (tz.startsWith("Asia/Singapore")) return "SG";
  if (tz.startsWith("Asia/Dubai")) return "AE";
  return "US";
}

// Generate a palette of distinct, vibrant colors
function generateResultColors(count: number): string[] {
  const colors: string[] = [];
  const goldenAngle = 137.508;
  for (let i = 0; i < count; i++) {
    const hue = (i * goldenAngle + Math.random() * 30) % 360;
    const sat = 55 + Math.random() * 25;
    const lit = 35 + Math.random() * 15;
    colors.push(`hsl(${Math.round(hue)}, ${Math.round(sat)}%, ${Math.round(lit)}%)`);
  }
  return colors;
}

export default function App() {
  const [searchQuery, setSearchQuery] = useState("");
  const [hasSearched, setHasSearched] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchData, setSearchData] = useState<SearchResponse | null>(null);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const [chartDimensions, setChartDimensions] = useState({ width: 0, height: 0 });
  const country = detectCountry();

  // Intro loader state
  const [introVisible, setIntroVisible] = useState(true);
  const [introFading, setIntroFading] = useState(false);

  // Dismiss intro after 2s
  useEffect(() => {
    const fadeTimer = setTimeout(() => setIntroFading(true), 1800);
    const removeTimer = setTimeout(() => setIntroVisible(false), 2400);
    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(removeTimer);
    };
  }, []);

  // Chart container measurement
  useEffect(() => {
    const el = chartContainerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          setChartDimensions({ width: Math.floor(width), height: Math.floor(height) });
        }
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsLoading(true);
    setError(null);
    setHasSearched(false);
    setSearchData(null);

    try {
      const res = await fetch("http://localhost:8000/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product: searchQuery, country }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Search failed");
      }

      const data: SearchResponse = await res.json();
      setSearchData(data);
      setHasSearched(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  };

  const results = searchData?.results ?? [];

  // Generate randomized colors every time results change
  const resultColors = useMemo(
    () => generateResultColors(results.length),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [results.length, hasSearched]
  );

  // Build chart data from results (price history mock with ±variance)
  const chartData = useMemo(() => {
    if (!hasSearched || results.length === 0) return [];
    return ["3W AGO", "2W AGO", "1W AGO", "NOW"].map((date) => {
      const entry: Record<string, string | number> = { date };
      results.forEach((r) => {
        const variance = (Math.random() - 0.5) * r.price * 0.1;
        entry[r.store] = parseFloat((r.price + variance).toFixed(2));
      });
      return entry;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasSearched, results.length]);

  return (
    <>
      {/* ===== INTRO LOADER OVERLAY ===== */}
      {introVisible && (
        <div className={`intro-screen ${introFading ? "fade-out" : ""}`}>
          <div className="loader" />
          <div
            style={{
              fontSize: "10px",
              letterSpacing: "0.3em",
              color: "#46494C",
              opacity: 0.6,
              textTransform: "uppercase",
              fontFamily: "inherit",
            }}
          >
            INITIALIZING
          </div>
        </div>
      )}

      {/* ===== MAIN APP ===== */}
      <div className="h-screen w-full bg-[#9B9987] text-[#46494C] font-sans uppercase text-xs flex overflow-hidden selection:bg-[#46494C] selection:text-[#9B9987] relative">

        {/* VERTICAL DIVIDERS — middle 1/3 of page height */}
        <div className="panel-divider" style={{ left: "33.33%" }} />
        <div className="panel-divider" style={{ left: "66.66%" }} />

        {/* LEFT — SEARCH */}
        <div
          className="w-1/3 h-full flex flex-col items-center justify-center p-8 relative z-10 panel-enter"
          style={{ animationDelay: introVisible ? "2400ms" : "0ms" }}
        >
          <div className="w-full max-w-[240px] relative z-20">
            <div className="mb-1 text-[#46494C] tracking-[0.2em] text-[10px] text-center opacity-70">
              [ SYSTEM.SEARCH ]
            </div>
            <div className="mb-4 text-[#46494C] tracking-[0.15em] text-[9px] text-center opacity-40">
              REGION: {country}
            </div>
            <form onSubmit={handleSearch} className="relative w-full">
              <div className="relative backdrop-blur-md bg-[#46494C]/10 border border-[#46494C] flex items-center p-3 transition-all focus-within:bg-[#46494C]/20">
                <Search className="w-4 h-4 text-[#46494C] shrink-0 mr-3" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="PRODUCT NAME..."
                  className="flex-1 bg-transparent border-none outline-none text-[#46494C] placeholder:text-[#46494C]/50 uppercase tracking-widest text-xs"
                />
              </div>
              <button
                type="submit"
                disabled={isLoading}
                className="mt-4 w-full border border-[#46494C] bg-transparent hover:bg-[#46494C] hover:text-[#9B9987] disabled:opacity-40 text-[#46494C] py-2 tracking-[0.2em] transition-colors"
              >
                {isLoading ? "SCANNING..." : "EXECUTE"}
              </button>
            </form>

            {error && (
              <div className="mt-4 text-[9px] tracking-widest text-red-800 border border-red-800/40 p-2 text-center opacity-80">
                {error}
              </div>
            )}
          </div>
        </div>

        {/* MIDDLE — RANKED RESULTS */}
        <div
          className="w-1/3 h-full flex flex-col p-8 relative z-10 panel-enter"
          style={{ animationDelay: introVisible ? "2600ms" : "200ms" }}
        >
          <div className="relative z-20 h-full flex flex-col">
            <div className="mb-8 text-[#46494C] tracking-[0.2em] text-[10px] border-b border-[#46494C]/30 pb-4 flex justify-between">
              <span>[ INDEX.RANKING ]</span>
              <span className="opacity-50">
                {isLoading ? "SCANNING..." : hasSearched ? `${results.length} FOUND` : "AWAITING INPUT"}
              </span>
            </div>

            <div className="flex-1 flex items-center justify-center overflow-hidden">
              {isLoading ? (
                <PriceLoadingAnimation />
              ) : hasSearched ? (
                <div className="flex flex-col gap-3 w-full overflow-y-auto custom-scrollbar pr-1">
                  {results.map((r, index) => (
                    <a
                      key={r.store}
                      href={r.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`p-4 border border-[#46494C]/40 backdrop-blur-md transition-all hover:bg-[#46494C]/15 flex flex-col gap-1 animate-in fade-in slide-in-from-bottom-4 duration-500 ${
                        index === 0 ? "bg-[#46494C]/10 shadow-[0_0_15px_rgba(70,73,76,0.15)]" : "bg-transparent"
                      }`}
                      style={{ animationDelay: `${index * 80}ms` }}
                    >
                      <div className="flex justify-between items-center text-[9px] tracking-widest opacity-50">
                        <span>RANK 0{index + 1}</span>
                        {index === 0 && <span className="animate-pulse text-[#46494C]">LOWEST ↓</span>}
                      </div>
                      <div className="flex justify-between items-end gap-2">
                        {/* Store name colored to match its graph line */}
                        <span
                          className="text-[11px] tracking-widest truncate font-semibold"
                          style={{ color: resultColors[index] ?? "#46494C" }}
                        >
                          {r.store}
                        </span>
                        <span className="text-base font-bold shrink-0">{r.price_text}</span>
                      </div>
                      <div className="text-[8px] tracking-wider opacity-40 truncate">{r.title}</div>
                    </a>
                  ))}
                </div>
              ) : (
                <div className="opacity-25 text-[10px] tracking-[0.3em]">NO DATA</div>
              )}
            </div>

            {hasSearched && searchData && (
              <div className="mt-4 text-[8px] tracking-[0.2em] opacity-40 border-t border-[#46494C]/20 pt-3">
                {searchData.product} · {searchData.region} · {searchData.currency}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT — TREND GRAPH */}
        <div
          className="w-1/3 h-full p-8 relative z-10 flex flex-col panel-enter"
          style={{ animationDelay: introVisible ? "2800ms" : "400ms" }}
        >
          <div className="relative z-20 h-full flex flex-col">
            <div className="mb-8 text-[#46494C] tracking-[0.2em] text-[10px] border-b border-[#46494C]/30 pb-4 flex justify-between">
              <span>[ GRAPH.TRENDS ]</span>
              <span className="opacity-50">4-WEEK TIMEFRAME</span>
            </div>

            <div ref={chartContainerRef} className="flex-1 w-full relative">
              {hasSearched && !isLoading && chartDimensions.width > 0 && chartDimensions.height > 0 ? (
                <div className="absolute inset-0">
                  <LineChart
                    data={chartData}
                    width={chartDimensions.width}
                    height={chartDimensions.height}
                    margin={{ top: 20, right: 20, left: -20, bottom: 0 }}
                  >
                    <XAxis dataKey="date" stroke="#46494C" fontSize={9} tickLine={false} axisLine={{ stroke: "#46494C", strokeOpacity: 0.3 }} />
                    <YAxis domain={["dataMin - 5", "dataMax + 5"]} stroke="#46494C" fontSize={9} tickLine={false} axisLine={{ stroke: "#46494C", strokeOpacity: 0.3 }} tickFormatter={(v) => `${v}`} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#9B9987", borderColor: "#46494C", color: "#46494C", textTransform: "uppercase", fontSize: "9px", letterSpacing: "0.1em", borderRadius: "0" }}
                      itemStyle={{ color: "#46494C" }}
                    />
                    {results.map((r, idx) => (
                      <Line
                        key={r.store}
                        type="monotone"
                        dataKey={r.store}
                        stroke={resultColors[idx] ?? "#46494C"}
                        strokeWidth={2.5}
                        dot={{ fill: "#9B9987", stroke: resultColors[idx] ?? "#46494C", strokeWidth: 1.5, r: 3 }}
                        activeDot={{ r: 5, fill: resultColors[idx] ?? "#46494C" }}
                        animationDuration={1500}
                      />
                    ))}
                  </LineChart>
                </div>
              ) : (
                <div className="w-full h-full flex items-center justify-center border border-[#46494C]/20">
                  <span className="opacity-25 text-[10px] tracking-[0.3em]">STANDBY</span>
                </div>
              )}
            </div>

            {hasSearched && !isLoading && results.length > 0 && (
              <div className="mt-6 flex flex-wrap gap-3 text-[8px] tracking-widest opacity-80">
                {results.map((r, idx) => (
                  <div key={r.store} className="flex items-center gap-1.5">
                    <div className="w-3 h-0.5 rounded-full" style={{ backgroundColor: resultColors[idx] ?? "#46494C" }} />
                    <span style={{ color: resultColors[idx] ?? "#46494C" }}>{r.store}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
