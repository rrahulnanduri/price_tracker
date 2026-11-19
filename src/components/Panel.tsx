import type { ReactNode } from "react";

interface PanelProps {
  enterDelayMs: number;
  label: string;
  className?: string;
  children: ReactNode;
}

/** One of the three columns; they stack into a single scrolling column on small screens. */
export function Panel({ enterDelayMs, label, className = "", children }: PanelProps) {
  return (
    <section
      aria-label={label}
      className={`w-full lg:w-1/3 lg:h-full min-h-0 p-5 sm:p-8 relative z-10 flex flex-col panel-enter ${className}`}
      style={{ animationDelay: `${enterDelayMs}ms` }}
    >
      {children}
    </section>
  );
}

export function PanelHeader({ title, status }: { title: string; status: ReactNode }) {
  return (
    <div className="mb-5 lg:mb-8 tracking-[0.2em] text-[11px] border-b border-ink/30 pb-4 flex justify-between gap-3">
      <h2>[ {title} ]</h2>
      <span className="opacity-60 text-right">{status}</span>
    </div>
  );
}
