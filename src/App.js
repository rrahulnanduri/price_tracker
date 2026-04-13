import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useRef, useEffect } from "react";
import { LineChart, Line, YAxis, XAxis, Tooltip } from "recharts";
import { Search } from "lucide-react";
import { PriceLoadingAnimation } from "./components/PriceLoadingAnimation";
// Detect country from browser timezone
function detectCountry() {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (tz.startsWith("America/"))
        return "US";
    if (tz.startsWith("Europe/London"))
        return "GB";
    if (tz.startsWith("Asia/Kolkata") || tz.startsWith("Asia/Calcutta"))
        return "IN";
    if (tz.startsWith("Europe/Berlin") || tz.startsWith("Europe/Vienna"))
        return "DE";
    if (tz.startsWith("Europe/Paris"))
        return "FR";
    if (tz.startsWith("Australia/"))
        return "AU";
    if (tz.startsWith("America/Toronto") || tz.startsWith("America/Vancouver"))
        return "CA";
    if (tz.startsWith("Asia/Tokyo"))
        return "JP";
    if (tz.startsWith("Asia/Singapore"))
        return "SG";
    if (tz.startsWith("Asia/Dubai"))
        return "AE";
    return "US";
}
export default function App() {
    const [searchQuery, setSearchQuery] = useState("");
    const [hasSearched, setHasSearched] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    const [searchData, setSearchData] = useState(null);
    const chartContainerRef = useRef(null);
    const [chartDimensions, setChartDimensions] = useState({ width: 0, height: 0 });
    const country = detectCountry();
    useEffect(() => {
        const el = chartContainerRef.current;
        if (!el)
            return;
        const observer = new ResizeObserver((entries) => {
            for (const entry of entries) {
                const { width, height } = entry.contentRect;
                setChartDimensions({ width: Math.floor(width), height: Math.floor(height) });
            }
        });
        observer.observe(el);
        return () => observer.disconnect();
    }, []);
    const handleSearch = async (e) => {
        e.preventDefault();
        if (!searchQuery.trim())
            return;
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
            const data = await res.json();
            setSearchData(data);
            setHasSearched(true);
        }
        catch (err) {
            setError(err instanceof Error ? err.message : "Unknown error");
        }
        finally {
            setIsLoading(false);
        }
    };
    const results = searchData?.results ?? [];
    // Build chart data from results (price history mock with ±variance)
    const chartData = hasSearched
        ? ["3W AGO", "2W AGO", "1W AGO", "NOW"].map((date) => {
            const entry = { date };
            results.forEach((r) => {
                const variance = (Math.random() - 0.5) * r.price * 0.1;
                entry[r.store] = parseFloat((r.price + variance).toFixed(2));
            });
            return entry;
        })
        : [];
    const lineOpacities = [1, 0.85, 0.7, 0.55, 0.4, 0.3, 0.2];
    return (_jsxs("div", { className: "h-screen w-full bg-[#9B9987] text-[#46494C] font-sans uppercase text-xs flex overflow-hidden selection:bg-[#46494C] selection:text-[#9B9987]", children: [_jsxs("div", { className: "w-1/3 h-full border-r border-[#46494C] flex flex-col items-center justify-center p-8 relative z-10 panel-enter", style: { animationDelay: "0ms" }, children: [_jsx("div", { className: "absolute inset-0 bg-[#46494C]/5 backdrop-blur-3xl pointer-events-none" }), _jsxs("div", { className: "w-full max-w-[240px] relative z-20", children: [_jsx("div", { className: "mb-1 text-[#46494C] tracking-[0.2em] text-[10px] text-center opacity-70", children: "[ SYSTEM.SEARCH ]" }), _jsxs("div", { className: "mb-4 text-[#46494C] tracking-[0.15em] text-[9px] text-center opacity-40", children: ["REGION: ", country] }), _jsxs("form", { onSubmit: handleSearch, className: "relative w-full", children: [_jsxs("div", { className: "relative backdrop-blur-md bg-[#46494C]/10 border border-[#46494C] flex items-center p-3 transition-all focus-within:bg-[#46494C]/20", children: [_jsx(Search, { className: "w-4 h-4 text-[#46494C] shrink-0 mr-3" }), _jsx("input", { type: "text", value: searchQuery, onChange: (e) => setSearchQuery(e.target.value), placeholder: "PRODUCT NAME...", className: "flex-1 bg-transparent border-none outline-none text-[#46494C] placeholder:text-[#46494C]/50 uppercase tracking-widest text-xs" })] }), _jsx("button", { type: "submit", disabled: isLoading, className: "mt-4 w-full border border-[#46494C] bg-transparent hover:bg-[#46494C] hover:text-[#9B9987] disabled:opacity-40 text-[#46494C] py-2 tracking-[0.2em] transition-colors", children: isLoading ? "SCANNING..." : "EXECUTE" })] }), error && (_jsx("div", { className: "mt-4 text-[9px] tracking-widest text-red-800 border border-red-800/40 p-2 text-center opacity-80", children: error }))] })] }), _jsxs("div", { className: "w-1/3 h-full border-r border-[#46494C] flex flex-col p-8 relative z-10 panel-enter", style: { animationDelay: "200ms" }, children: [_jsx("div", { className: "absolute inset-0 bg-[#9B9987]/40 backdrop-blur-xl pointer-events-none" }), _jsxs("div", { className: "relative z-20 h-full flex flex-col", children: [_jsxs("div", { className: "mb-8 text-[#46494C] tracking-[0.2em] text-[10px] border-b border-[#46494C]/30 pb-4 flex justify-between", children: [_jsx("span", { children: "[ INDEX.RANKING ]" }), _jsx("span", { className: "opacity-50", children: isLoading ? "SCANNING..." : hasSearched ? `${results.length} FOUND` : "AWAITING INPUT" })] }), _jsx("div", { className: "flex-1 flex items-center justify-center overflow-hidden", children: isLoading ? (_jsx(PriceLoadingAnimation, {})) : hasSearched ? (_jsx("div", { className: "flex flex-col gap-3 w-full overflow-y-auto custom-scrollbar pr-1", children: results.map((r, index) => (_jsxs("a", { href: r.url, target: "_blank", rel: "noopener noreferrer", className: `p-4 border border-[#46494C] backdrop-blur-md transition-all hover:bg-[#46494C]/15 flex flex-col gap-1 animate-in fade-in slide-in-from-bottom-4 duration-500 ${index === 0 ? "bg-[#46494C]/20 shadow-[0_0_15px_rgba(70,73,76,0.2)]" : "bg-transparent"}`, style: { animationDelay: `${index * 80}ms` }, children: [_jsxs("div", { className: "flex justify-between items-center text-[9px] tracking-widest opacity-50", children: [_jsxs("span", { children: ["RANK 0", index + 1] }), index === 0 && _jsx("span", { className: "animate-pulse text-[#46494C]", children: "LOWEST \u2193" })] }), _jsxs("div", { className: "flex justify-between items-end gap-2", children: [_jsx("span", { className: "text-[11px] tracking-widest truncate", children: r.store }), _jsx("span", { className: "text-base font-bold shrink-0", children: r.price_text })] }), _jsx("div", { className: "text-[8px] tracking-wider opacity-40 truncate", children: r.title })] }, r.store))) })) : (_jsx("div", { className: "opacity-25 text-[10px] tracking-[0.3em]", children: "NO DATA" })) }), hasSearched && searchData && (_jsxs("div", { className: "mt-4 text-[8px] tracking-[0.2em] opacity-40 border-t border-[#46494C]/20 pt-3", children: [searchData.product, " \u00B7 ", searchData.region, " \u00B7 ", searchData.currency] }))] })] }), _jsxs("div", { className: "w-1/3 h-full p-8 relative z-10 flex flex-col panel-enter", style: { animationDelay: "400ms" }, children: [_jsx("div", { className: "absolute inset-0 bg-[#46494C]/5 backdrop-blur-md pointer-events-none" }), _jsxs("div", { className: "relative z-20 h-full flex flex-col", children: [_jsxs("div", { className: "mb-8 text-[#46494C] tracking-[0.2em] text-[10px] border-b border-[#46494C]/30 pb-4 flex justify-between", children: [_jsx("span", { children: "[ GRAPH.TRENDS ]" }), _jsx("span", { className: "opacity-50", children: "4-WEEK TIMEFRAME" })] }), _jsx("div", { ref: chartContainerRef, className: "flex-1 w-full relative", children: hasSearched && !isLoading && chartDimensions.width > 0 ? (_jsx("div", { className: "absolute inset-0", children: _jsxs(LineChart, { data: chartData, width: chartDimensions.width, height: chartDimensions.height, margin: { top: 20, right: 20, left: -20, bottom: 0 }, children: [_jsx(XAxis, { dataKey: "date", stroke: "#46494C", fontSize: 9, tickLine: false, axisLine: { stroke: "#46494C", strokeOpacity: 0.3 } }), _jsx(YAxis, { domain: ["dataMin - 5", "dataMax + 5"], stroke: "#46494C", fontSize: 9, tickLine: false, axisLine: { stroke: "#46494C", strokeOpacity: 0.3 }, tickFormatter: (v) => `${v}` }), _jsx(Tooltip, { contentStyle: { backgroundColor: "#9B9987", borderColor: "#46494C", color: "#46494C", textTransform: "uppercase", fontSize: "9px", letterSpacing: "0.1em", borderRadius: "0" }, itemStyle: { color: "#46494C" } }), results.map((r, idx) => (_jsx(Line, { type: "monotone", dataKey: r.store, stroke: "#46494C", strokeOpacity: lineOpacities[idx % lineOpacities.length], strokeWidth: 2, dot: { fill: "#9B9987", stroke: "#46494C", strokeWidth: 1, r: 3 }, activeDot: { r: 5, fill: "#46494C" }, animationDuration: 1500 }, r.store)))] }) })) : (_jsx("div", { className: "w-full h-full flex items-center justify-center border border-[#46494C]/20", children: _jsx("span", { className: "opacity-25 text-[10px] tracking-[0.3em]", children: "STANDBY" }) })) }), hasSearched && !isLoading && results.length > 0 && (_jsx("div", { className: "mt-6 flex flex-wrap gap-3 text-[8px] tracking-widest opacity-60", children: results.map((r, idx) => (_jsxs("div", { className: "flex items-center gap-1.5", children: [_jsx("div", { className: "w-3 h-px bg-[#46494C]", style: { opacity: lineOpacities[idx % lineOpacities.length] } }), _jsx("span", { children: r.store })] }, r.store))) }))] })] })] }));
}
