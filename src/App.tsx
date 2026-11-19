import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { IntroLoader, INTRO_DURATION_MS, useIntro } from "./components/IntroLoader";
import { Panel } from "./components/Panel";
import { ResultsPanel } from "./components/ResultsPanel";
import { SearchPanel } from "./components/SearchPanel";
import { TrackControls } from "./components/TrackControls";
import { Watchlist } from "./components/Watchlist";
import { usePriceSearch } from "./hooks/usePriceSearch";
import { useRemote } from "./hooks/useRemote";
import { findWatch, useWatchlist } from "./hooks/useWatchlist";
import { getHistory, getMeta, type Watch } from "./lib/api";
import { assignColors } from "./lib/chart";
import { DEFAULT_COUNTRY, detectCountry, loadSavedCountry, pickSupported, saveCountry } from "./lib/region";

// The charting library is most of the bundle; load it after the search UI is up.
const TrendPanel = lazy(() =>
  import("./components/TrendPanel").then((module) => ({ default: module.TrendPanel })),
);

const PANEL_STAGGER_MS = 200;

export default function App() {
  const intro = useIntro();
  const meta = useRemote("meta", getMeta);
  const regions = useMemo(() => meta?.regions ?? [], [meta]);

  const [query, setQuery] = useState("");
  const [chosenCountry, setChosenCountry] = useState(() => loadSavedCountry() ?? detectCountry());
  // Until the backend says what it supports, trust the guess; then fall back if it is not offered.
  const country = useMemo(
    () =>
      regions.length === 0
        ? chosenCountry
        : pickSupported([chosenCountry], regions.map((r) => r.code), meta?.default_region ?? DEFAULT_COUNTRY),
    [chosenCountry, regions, meta],
  );

  const { data, isLoading, error, search: runSearch, clear } = usePriceSearch();
  const resultsRef = useRef<HTMLDivElement>(null);

  const search = useCallback(
    (product: string, region: string, refresh = false) => {
      // On a phone the panels are stacked, so bring the results into view.
      if (product.trim() && window.matchMedia("(max-width: 1023px)").matches) {
        resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      return runSearch(product, region, refresh);
    },
    [runSearch],
  );
  const watchlist = useWatchlist();
  const { reload: reloadWatchlist } = watchlist;

  // Every finished search may have updated a tracked product's latest price.
  useEffect(() => {
    if (data) void reloadWatchlist();
  }, [data, reloadWatchlist]);

  const points = useRemote(
    data ? `${data.product}|${data.country}|${data.fetched_at}` : null,
    (signal) => getHistory(data!.product, data!.country, signal),
  );

  const colors = useMemo(() => {
    const stores = new Set<string>(data?.results.map((r) => r.store));
    points?.forEach((p) => Object.keys(p.stores).forEach((s) => stores.add(s)));
    return assignColors([...stores].sort());
  }, [data, points]);

  const watch = data ? findWatch(watchlist.items, data.product, data.country) : undefined;

  const changeCountry = useCallback(
    (next: string) => {
      setChosenCountry(next);
      saveCountry(next);
      clear(); // results for another region would be misleading under the new one
    },
    [clear],
  );

  const openWatch = useCallback(
    (item: Watch) => {
      setQuery(item.product);
      setChosenCountry(item.country);
      saveCountry(item.country);
      void search(item.product, item.country);
    },
    [search],
  );

  // Panels wait for the intro overlay, then enter left to right.
  const enterDelay = (index: number) =>
    (intro.visible ? INTRO_DURATION_MS : 0) + index * PANEL_STAGGER_MS;

  return (
    <>
      {intro.visible && <IntroLoader fading={intro.fading} />}

      <main className="min-h-screen lg:h-screen w-full bg-paper text-ink font-sans uppercase text-xs flex flex-col lg:flex-row lg:overflow-hidden selection:bg-ink selection:text-paper relative">
        {/* Vertical dividers spanning the middle third of the page height (desktop only) */}
        <div className="panel-divider hidden lg:block" style={{ left: "33.33%" }} />
        <div className="panel-divider hidden lg:block" style={{ left: "66.66%" }} />

        <Panel label="Search and watchlist" enterDelayMs={enterDelay(0)} className="lg:justify-center">
          <div className="w-full max-w-sm mx-auto flex flex-col min-h-0">
            <SearchPanel
              query={query}
              onQueryChange={setQuery}
              country={country}
              regions={regions}
              onCountryChange={changeCountry}
              isLoading={isLoading}
              error={error}
              onSearch={() => void search(query, country)}
            />
            <Watchlist
              items={watchlist.items}
              regions={regions}
              error={watchlist.error}
              activeId={watch?.id ?? null}
              onOpen={openWatch}
              onRemove={(item) => void watchlist.untrack(item.id)}
            />
          </div>
        </Panel>

        <Panel label="Ranked prices" enterDelayMs={enterDelay(1)}>
          <div ref={resultsRef} className="h-full min-h-0 scroll-mt-4">
          <ResultsPanel
            data={data}
            isLoading={isLoading}
            colors={colors}
            onRefresh={() => data && void search(data.product, data.country, true)}
          >
            {data && (
              <TrackControls
                key={`${data.product}|${data.country}`}
                watch={watch}
                currency={data.currency}
                locale={data.locale}
                refreshHours={meta?.refresh_hours ?? 0}
                onTrack={(target) => void watchlist.track(data.product, data.country, target)}
                onSetTarget={(item, target) => void watchlist.setTarget(item.id, target)}
                onUntrack={(item) => void watchlist.untrack(item.id)}
              />
            )}
          </ResultsPanel>
          </div>
        </Panel>

        <Panel label="Price history" enterDelayMs={enterDelay(2)}>
          <Suspense fallback={null}>
            <TrendPanel
              points={data ? points : null}
              currency={data?.currency ?? "USD"}
              locale={data?.locale ?? "en-US"}
              colors={colors}
            />
          </Suspense>
        </Panel>
      </main>
    </>
  );
}
