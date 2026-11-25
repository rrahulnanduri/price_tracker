const SOURCE_LABELS: Record<string, string> = {
  google: "GOOGLE SHOPPING",
  serpapi: "GOOGLE SHOPPING (SERPAPI)",
  kieskeurig: "KIESKEURIG",
  staticice: "STATICICE",
  demo: "DEMO",
};

export const sourceLabel = (name: string) => SOURCE_LABELS[name] ?? name.toUpperCase();
