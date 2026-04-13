# Graph Report - .  (2026-04-13)

## Corpus Check
- Corpus is ~16,907 words - fits in a single context window. You may not need a graph.

## Summary
- 220 nodes · 235 edges · 33 communities detected
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 9 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `useFormField()` - 4 edges
2. `scrape_google_shopping()` - 3 edges
3. `scrape_prices()` - 2 edges
4. `track_prices()` - 2 edges
5. `SearchRequest` - 2 edges
6. `parse_price()` - 2 edges
7. `search_prices()` - 2 edges
8. `useSidebar()` - 2 edges
9. `SidebarMenuButton()` - 2 edges
10. `FormControl()` - 2 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Communities

### Community 0 - "Base UI Components"
Cohesion: 0.06
Nodes (0): 

### Community 1 - "Input & Sidebar Controls"
Cohesion: 0.1
Nodes (2): SidebarMenuButton(), useSidebar()

### Community 2 - "Button & Widget Set"
Cohesion: 0.14
Nodes (2): CarouselNext(), useCarousel()

### Community 3 - "Core App & Scraping Logic"
Cohesion: 0.17
Nodes (9): App(), detectCountry(), scrape_prices(), track_prices(), BaseModel, parse_price(), scrape_google_shopping(), search_prices() (+1 more)

### Community 4 - "Command & Dialog"
Cohesion: 0.18
Nodes (0): 

### Community 5 - "Dropdown Menu"
Cohesion: 0.18
Nodes (0): 

### Community 6 - "Menubar"
Cohesion: 0.22
Nodes (0): 

### Community 7 - "Price Loading Animation"
Cohesion: 0.25
Nodes (0): 

### Community 8 - "Form & Label"
Cohesion: 0.36
Nodes (4): FormControl(), FormDescription(), FormMessage(), useFormField()

### Community 9 - "Alert Dialog"
Cohesion: 0.29
Nodes (0): 

### Community 10 - "Breadcrumb Navigation"
Cohesion: 0.29
Nodes (0): 

### Community 11 - "Select"
Cohesion: 0.29
Nodes (0): 

### Community 12 - "Sheet Panel"
Cohesion: 0.33
Nodes (0): 

### Community 13 - "Navigation Menu"
Cohesion: 0.33
Nodes (0): 

### Community 14 - "Drawer"
Cohesion: 0.33
Nodes (0): 

### Community 15 - "Table"
Cohesion: 0.4
Nodes (0): 

### Community 16 - "Context Menu"
Cohesion: 0.4
Nodes (0): 

### Community 17 - "Card"
Cohesion: 0.5
Nodes (0): 

### Community 18 - "OTP Input"
Cohesion: 0.67
Nodes (0): 

### Community 19 - "Accordion"
Cohesion: 0.5
Nodes (0): 

### Community 20 - "Tabs"
Cohesion: 0.67
Nodes (0): 

### Community 21 - "Slider"
Cohesion: 0.67
Nodes (0): 

### Community 22 - "Scroll Area"
Cohesion: 0.67
Nodes (0): 

### Community 23 - "Collapsible"
Cohesion: 0.67
Nodes (0): 

### Community 24 - "Filter Panel"
Cohesion: 1.0
Nodes (0): 

### Community 25 - "Toast Notifications"
Cohesion: 2.0
Nodes (0): 

### Community 26 - "Image Fallback"
Cohesion: 1.0
Nodes (0): 

### Community 27 - "Tailwind Config"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "Vite Config"
Cohesion: 1.0
Nodes (0): 

### Community 29 - "PostCSS Config"
Cohesion: 1.0
Nodes (0): 

### Community 30 - "Price Card"
Cohesion: 1.0
Nodes (0): 

### Community 31 - "Aspect Ratio"
Cohesion: 1.0
Nodes (0): 

### Community 32 - "Type Declarations"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **Thin community `Filter Panel`** (2 nodes): `FilterPanel.tsx`, `FilterPanel()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Toast Notifications`** (2 nodes): `sonner.tsx`, `Toaster()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Image Fallback`** (2 nodes): `ImageWithFallback.tsx`, `ImageWithFallback()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Tailwind Config`** (1 nodes): `tailwind.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Vite Config`** (1 nodes): `vite.config.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `PostCSS Config`** (1 nodes): `postcss.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Price Card`** (1 nodes): `PriceCard.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Aspect Ratio`** (1 nodes): `aspect-ratio.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Type Declarations`** (1 nodes): `types.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Are the 3 inferred relationships involving `useFormField()` (e.g. with `FormControl()` and `FormDescription()`) actually correct?**
  _`useFormField()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `scrape_google_shopping()` (e.g. with `parse_price()` and `search_prices()`) actually correct?**
  _`scrape_google_shopping()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `Base UI Components` be split into smaller, more focused modules?**
  _Cohesion score 0.06 - nodes in this community are weakly interconnected._
- **Should `Input & Sidebar Controls` be split into smaller, more focused modules?**
  _Cohesion score 0.1 - nodes in this community are weakly interconnected._
- **Should `Button & Widget Set` be split into smaller, more focused modules?**
  _Cohesion score 0.14 - nodes in this community are weakly interconnected._