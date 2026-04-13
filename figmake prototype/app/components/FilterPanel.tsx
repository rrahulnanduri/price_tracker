import { motion } from "motion/react";

interface FilterCategory {
  id: string;
  label: string;
}

interface FilterPanelProps {
  categories: FilterCategory[];
  activeFilters: string[];
  onFilterChange: (filters: string[]) => void;
}

export function FilterPanel({ categories, activeFilters, onFilterChange }: FilterPanelProps) {
  const toggleFilter = (id: string) => {
    if (activeFilters.includes(id)) {
      onFilterChange(activeFilters.filter((f) => f !== id));
    } else {
      onFilterChange([...activeFilters, id]);
    }
  };

  return (
    <div className="backdrop-blur-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-2xl p-6">
      <div className="mb-4 text-sm text-muted-foreground">Filter by category</div>
      <div className="flex flex-wrap gap-2">
        {categories.map((category) => {
          const isActive = activeFilters.includes(category.id);
          return (
            <motion.button
              key={category.id}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => toggleFilter(category.id)}
              className={`px-4 py-2 rounded-lg border transition-all ${
                isActive
                  ? "bg-primary/20 border-primary/40 text-primary"
                  : "bg-white/5 border-white/10 text-muted-foreground hover:bg-white/10 hover:border-white/20"
              }`}
            >
              {category.label}
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
