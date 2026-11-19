import { TrendingDown, TrendingUp, ExternalLink } from "lucide-react";
import { LineChart, Line, ResponsiveContainer, YAxis } from "recharts";

interface PriceData {
  id: string;
  website: string;
  currentPrice: number;
  priceHistory: { date: string; price: number }[];
  trend: "up" | "down";
  trendPercent: number;
}

interface PriceCardProps {
  data: PriceData;
  isLowest: boolean;
}

export function PriceCard({ data, isLowest }: PriceCardProps) {
  const TrendIcon = data.trend === "down" ? TrendingDown : TrendingUp;
  const trendColor = data.trend === "down" ? "text-green-400" : "text-red-400";
  const trendBg = data.trend === "down" ? "bg-green-500/10" : "bg-red-500/10";
  const trendBorder = data.trend === "down" ? "border-green-500/20" : "border-red-500/20";

  return (
    <div
      className={`group relative backdrop-blur-xl bg-[var(--glass-bg)] border rounded-2xl p-6 transition-all duration-300 hover:bg-[var(--glass-bg)]/60 hover:border-[var(--glass-border)]/30 ${
        isLowest ? "border-primary/40 shadow-lg shadow-primary/10" : "border-[var(--glass-border)]"
      }`}
    >
      {/* Glow Effect on Hover */}
      <div className="absolute inset-0 rounded-2xl bg-gradient-to-r from-primary/0 via-primary/5 to-purple-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

      {/* Lowest Price Badge */}
      {isLowest && (
        <div className="absolute -top-3 left-6 px-3 py-1 bg-primary rounded-full text-xs text-white backdrop-blur-xl">
          Lowest Price
        </div>
      )}

      <div className="relative grid grid-cols-1 lg:grid-cols-[1fr_auto_auto] gap-6 items-center">
        {/* Website & Price */}
        <div className="flex items-center gap-6">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h3 className="text-xl text-white">{data.website}</h3>
              <a
                href="#"
                className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-primary"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
            </div>
            <div className="flex items-baseline gap-3">
              <div className="text-3xl text-white">${data.currentPrice.toFixed(2)}</div>
              <div className={`flex items-center gap-1 px-2 py-1 ${trendBg} border ${trendBorder} rounded-lg text-sm ${trendColor}`}>
                <TrendIcon className="w-3.5 h-3.5" />
                <span>{data.trendPercent}%</span>
              </div>
            </div>
          </div>
        </div>

        {/* Trend Chart */}
        <div className="w-full lg:w-48 h-16">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.priceHistory}>
              <YAxis domain={["dataMin - 20", "dataMax + 20"]} hide />
              <Line
                type="monotone"
                dataKey="price"
                stroke={data.trend === "down" ? "#4ade80" : "#f87171"}
                strokeWidth={2}
                dot={false}
                animationDuration={1000}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Action Button */}
        <div>
          <button className="px-6 py-2.5 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 rounded-lg text-white transition-all backdrop-blur-sm">
            View Deal
          </button>
        </div>
      </div>
    </div>
  );
}
