import { useState } from "react";
import { LineChart, Line, ResponsiveContainer, YAxis, XAxis, Tooltip } from "recharts";
import { Search } from "lucide-react";

interface PriceData {
  id: string;
  website: string;
  currentPrice: number;
}

const websitesData: PriceData[] = [
  { id: "1", website: "TECHMART", currentPrice: 899.99 },
  { id: "2", website: "ELECTROWORLD", currentPrice: 925.00 },
  { id: "3", website: "GADGETHUB", currentPrice: 949.99 },
  { id: "4", website: "PRICEZONE", currentPrice: 959.00 },
  { id: "5", website: "BUYNOW", currentPrice: 975.50 },
].sort((a, b) => a.currentPrice - b.currentPrice);

const chartData = [
  { date: "JAN", TECHMART: 1029, ELECTROWORLD: 1005, GADGETHUB: 930, PRICEZONE: 1012, BUYNOW: 1014 },
  { date: "FEB", TECHMART: 989, ELECTROWORLD: 995, GADGETHUB: 920, PRICEZONE: 985, BUYNOW: 998 },
  { date: "MAR", TECHMART: 920, ELECTROWORLD: 945, GADGETHUB: 935, PRICEZONE: 970, BUYNOW: 988 },
  { date: "APR", TECHMART: 899.99, ELECTROWORLD: 925, GADGETHUB: 949.99, PRICEZONE: 959, BUYNOW: 975.5 },
];

export default function App() {
  const [searchQuery, setSearchQuery] = useState("");
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      setHasSearched(true);
    }
  };

  const lineOpacities = [1, 0.8, 0.6, 0.4, 0.2];

  return (
    <div className="min-h-screen w-full bg-[#9B9987] text-[#46494C] font-sans uppercase text-xs flex overflow-hidden selection:bg-[#46494C] selection:text-[#9B9987]">
      {/* LEFT 1/3 - SEARCH */}
      <div className="w-1/3 h-full min-h-screen border-r border-[#46494C] flex flex-col items-center justify-center p-8 relative z-10">
        <div className="absolute inset-0 bg-[#46494C]/5 backdrop-blur-3xl pointer-events-none" />
        <div className="w-full max-w-[240px] relative z-20">
          <div className="mb-4 text-[#46494C] tracking-[0.2em] text-[10px] text-center opacity-70">
            [ SYSTEM.SEARCH ]
          </div>
          <form onSubmit={handleSearch} className="relative w-full">
            <div className="relative backdrop-blur-md bg-[#46494C]/10 border border-[#46494C] flex items-center p-3 transition-all focus-within:bg-[#46494C]/20">
              <Search className="w-4 h-4 text-[#46494C] shrink-0 mr-3" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="MODEL OR NAME..."
                className="flex-1 bg-transparent border-none outline-none text-[#46494C] placeholder:text-[#46494C]/50 uppercase tracking-widest text-xs"
              />
            </div>
            <button
              type="submit"
              className="mt-4 w-full border border-[#46494C] bg-transparent hover:bg-[#46494C] hover:text-[#9B9987] text-[#46494C] py-2 tracking-[0.2em] transition-colors"
            >
              EXECUTE
            </button>
          </form>
        </div>
      </div>

      {/* MIDDLE 1/3 - RANKED LIST */}
      <div className="w-1/3 h-full min-h-screen border-r border-[#46494C] flex flex-col p-8 relative z-10">
        <div className="absolute inset-0 bg-[#9B9987]/40 backdrop-blur-xl pointer-events-none" />
        <div className="relative z-20 h-full flex flex-col">
          <div className="mb-8 text-[#46494C] tracking-[0.2em] text-[10px] border-b border-[#46494C]/30 pb-4">
            [ INDEX.RANKING ] // {hasSearched ? "RESULTS FOUND" : "AWAITING INPUT"}
          </div>
          
          <div className="flex-1 flex flex-col gap-4 overflow-y-auto pr-2 custom-scrollbar">
            {hasSearched ? (
              websitesData.map((data, index) => (
                <div
                  key={data.id}
                  className={`p-4 border border-[#46494C] backdrop-blur-md transition-all hover:bg-[#46494C]/10 flex flex-col gap-2 ${
                    index === 0 ? "bg-[#46494C]/20 shadow-[0_0_15px_rgba(70,73,76,0.2)]" : "bg-transparent"
                  }`}
                >
                  <div className="flex justify-between items-center text-[10px] tracking-widest opacity-60">
                    <span>RANK 0{index + 1}</span>
                    {index === 0 && <span className="animate-pulse">LOWEST</span>}
                  </div>
                  <div className="flex justify-between items-end">
                    <span className="text-sm tracking-widest">{data.website}</span>
                    <span className="text-lg font-bold">${data.currentPrice.toFixed(2)}</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="flex-1 flex items-center justify-center opacity-30 text-[10px] tracking-[0.3em]">
                NO DATA
              </div>
            )}
          </div>
        </div>
      </div>

      {/* RIGHT 1/3 - TREND GRAPH */}
      <div className="w-1/3 h-full min-h-screen p-8 relative z-10 flex flex-col">
        <div className="absolute inset-0 bg-[#46494C]/5 backdrop-blur-md pointer-events-none" />
        <div className="relative z-20 h-full flex flex-col">
          <div className="mb-8 text-[#46494C] tracking-[0.2em] text-[10px] border-b border-[#46494C]/30 pb-4 flex justify-between">
            <span>[ GRAPH.TRENDS ]</span>
            <span>3-MONTH TIMEFRAME</span>
          </div>

          <div className="flex-1 min-h-[300px] w-full relative">
            {hasSearched ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 20, right: 20, left: -20, bottom: 0 }}>
                  <XAxis 
                    dataKey="date" 
                    stroke="#46494C" 
                    fontSize={10} 
                    tickLine={false}
                    axisLine={{ stroke: '#46494C', strokeOpacity: 0.3 }}
                  />
                  <YAxis 
                    domain={["dataMin - 20", "dataMax + 20"]} 
                    stroke="#46494C" 
                    fontSize={10}
                    tickLine={false}
                    axisLine={{ stroke: '#46494C', strokeOpacity: 0.3 }}
                    tickFormatter={(val) => `$${val}`}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#9B9987', 
                      borderColor: '#46494C',
                      color: '#46494C',
                      textTransform: 'uppercase',
                      fontSize: '10px',
                      letterSpacing: '0.1em',
                      borderRadius: '0'
                    }}
                    itemStyle={{ color: '#46494C' }}
                  />
                  {websitesData.map((site, idx) => (
                    <Line
                      key={site.id}
                      type="monotone"
                      dataKey={site.website}
                      stroke="#46494C"
                      strokeOpacity={lineOpacities[idx % lineOpacities.length]}
                      strokeWidth={2}
                      dot={{ fill: '#9B9987', stroke: '#46494C', strokeWidth: 1, r: 3 }}
                      activeDot={{ r: 5, fill: '#46494C' }}
                      animationDuration={1500}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="w-full h-full flex items-center justify-center border border-[#46494C]/20 relative overflow-hidden">
                <div className="absolute inset-0 bg-[linear-gradient(45deg,transparent_25%,rgba(70,73,76,0.05)_50%,transparent_75%)] bg-[length:200%_200%] pointer-events-none" />
                <span className="opacity-30 text-[10px] tracking-[0.3em]">STANDBY</span>
              </div>
            )}
          </div>
          
          {hasSearched && (
            <div className="mt-8 flex flex-wrap gap-4 text-[9px] tracking-widest opacity-70">
              {websitesData.map((site, idx) => (
                <div key={site.id} className="flex items-center gap-2">
                  <div 
                    className="w-3 h-0.5 bg-[#46494C]" 
                    style={{ opacity: lineOpacities[idx % lineOpacities.length] }}
                  />
                  <span>{site.website}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
