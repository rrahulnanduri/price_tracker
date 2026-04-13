import { useState, useEffect } from "react"
import { Field, FieldLabel } from "@/components/ui/field"
import { Progress } from "@/components/ui/progress"

interface LoadingState {
  progress: number
  status: string
}

export function PriceLoadingAnimation() {
  const [loading, setLoading] = useState<LoadingState>({
    progress: 0,
    status: "INITIALIZING SCAN...",
  })

  useEffect(() => {
    const stages = [
      { progress: 20, status: "[ SCANNING WEBSITES ]" },
      { progress: 40, status: "[ EXTRACTING PRICES ]" },
      { progress: 60, status: "[ ANALYZING DATA ]" },
      { progress: 80, status: "[ SORTING RESULTS ]" },
      { progress: 100, status: "[ COMPLETE ]" },
    ]

    let currentStage = 0
    const interval = setInterval(() => {
      if (currentStage < stages.length) {
        setLoading(stages[currentStage])
        currentStage++
      } else {
        clearInterval(interval)
      }
    }, 800)

    return () => clearInterval(interval)
  }, [])

  return (
    <div className="w-full max-w-sm space-y-6 px-8">
      <div className="text-center">
        <div className="text-xs tracking-[0.3em] uppercase text-[#46494C]/60 mb-4">
          [ SYSTEM.LOADING ]
        </div>
        <div className="text-2xl font-bold tracking-widest uppercase text-[#46494C]">
          Searching...
        </div>
      </div>

      <Field className="w-full">
        <FieldLabel htmlFor="price-progress">
          <span>{loading.status}</span>
          <span className="ml-auto">{loading.progress}%</span>
        </FieldLabel>
        <Progress
          value={loading.progress}
          id="price-progress"
          className="h-2 bg-[#46494C]/20"
        />
      </Field>

      {/* Animated dots */}
      <div className="flex justify-center gap-2">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="w-2 h-2 rounded-full bg-[#46494C] animate-pulse"
            style={{
              animationDelay: `${i * 0.2}s`,
              opacity: 0.6 + i * 0.15,
            }}
          />
        ))}
      </div>
    </div>
  )
}
