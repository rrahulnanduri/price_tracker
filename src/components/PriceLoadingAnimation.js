import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect } from "react";
import { Field, FieldLabel } from "@/components/ui/field";
import { Progress } from "@/components/ui/progress";
export function PriceLoadingAnimation() {
    const [loading, setLoading] = useState({
        progress: 0,
        status: "INITIALIZING SCAN...",
    });
    useEffect(() => {
        const stages = [
            { progress: 20, status: "[ SCANNING WEBSITES ]" },
            { progress: 40, status: "[ EXTRACTING PRICES ]" },
            { progress: 60, status: "[ ANALYZING DATA ]" },
            { progress: 80, status: "[ SORTING RESULTS ]" },
            { progress: 100, status: "[ COMPLETE ]" },
        ];
        let currentStage = 0;
        const interval = setInterval(() => {
            if (currentStage < stages.length) {
                setLoading(stages[currentStage]);
                currentStage++;
            }
            else {
                clearInterval(interval);
            }
        }, 800);
        return () => clearInterval(interval);
    }, []);
    return (_jsxs("div", { className: "w-full max-w-sm space-y-6 px-8", children: [_jsxs("div", { className: "text-center", children: [_jsx("div", { className: "text-xs tracking-[0.3em] uppercase text-[#46494C]/60 mb-4", children: "[ SYSTEM.LOADING ]" }), _jsx("div", { className: "text-2xl font-bold tracking-widest uppercase text-[#46494C]", children: "Searching..." })] }), _jsxs(Field, { className: "w-full", children: [_jsxs(FieldLabel, { htmlFor: "price-progress", children: [_jsx("span", { children: loading.status }), _jsxs("span", { className: "ml-auto", children: [loading.progress, "%"] })] }), _jsx(Progress, { value: loading.progress, id: "price-progress", className: "h-2 bg-[#46494C]/20" })] }), _jsx("div", { className: "flex justify-center gap-2", children: [0, 1, 2].map((i) => (_jsx("div", { className: "w-2 h-2 rounded-full bg-[#46494C] animate-pulse", style: {
                        animationDelay: `${i * 0.2}s`,
                        opacity: 0.6 + i * 0.15,
                    } }, i))) })] }));
}
