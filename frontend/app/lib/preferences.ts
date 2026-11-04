import type { ReportSummary } from "./api";

export const PREFERENCES_KEY = "team-science.preferences.v1";
export const REPORT_SORT_OPTIONS = {
  newest: "Newest first", oldest: "Oldest first", "most-issues": "Most issues",
  "fewest-issues": "Fewest issues", "most-rows": "Most rows", "fewest-rows": "Fewest rows",
} as const;
export type ReportSort = keyof typeof REPORT_SORT_OPTIONS;
export const ACCENT_OPTIONS = {
  violet: { label: "Violet", color: "#6853e8" },
  blue: { label: "Blue", color: "#2563eb" },
  teal: { label: "Teal", color: "#0f766e" },
  rose: { label: "Rose", color: "#be185d" },
  amber: { label: "Amber", color: "#a15c08" },
} as const;
export type AccentColor = keyof typeof ACCENT_OPTIONS;
export const PALETTE_OPTIONS = {
  neutral: { label: "Neutral", colors: ["#181818", "#242424", "#2e2e2e"] },
  forest: { label: "Forest", colors: ["#151e19", "#1e2a23", "#26342c"] },
  slate: { label: "Slate", colors: ["#171c26", "#222a36", "#2c3543"] },
  plum: { label: "Plum", colors: ["#201923", "#2c2330", "#382d3d"] },
  sand: { label: "Sand", colors: ["#211d18", "#2d2721", "#393128"] },
} as const;
export type WorkspacePalette = keyof typeof PALETTE_OPTIONS;
export interface Preferences {
  theme: "system" | "light" | "dark";
  palette: WorkspacePalette;
  accent: AccentColor;
  density: "comfortable" | "compact";
  motion: "system" | "reduce" | "full";
  reportSort: ReportSort;
  sidebarCollapsed: boolean;
}
export const DEFAULT_PREFERENCES: Preferences = { theme: "system", palette: "neutral", accent: "violet", density: "comfortable", motion: "system", reportSort: "newest", sidebarCollapsed: false };
export function validatePreferences(input: unknown): Preferences {
  const value = input && typeof input === "object" ? input as Record<string, unknown> : {};
  return {
    theme: value.theme === "light" || value.theme === "dark" ? value.theme : "system",
    palette: typeof value.palette === "string" && Object.hasOwn(PALETTE_OPTIONS, value.palette) ? value.palette as WorkspacePalette : "neutral",
    accent: typeof value.accent === "string" && Object.hasOwn(ACCENT_OPTIONS, value.accent) ? value.accent as AccentColor : "violet",
    density: value.density === "compact" ? "compact" : "comfortable",
    motion: value.motion === "reduce" || value.motion === "full" ? value.motion : "system",
    reportSort: typeof value.reportSort === "string" && Object.hasOwn(REPORT_SORT_OPTIONS, value.reportSort) ? value.reportSort as ReportSort : "newest",
    sidebarCollapsed: value.sidebarCollapsed === true,
  };
}
export interface PreferenceStorage { getItem(key: string): string | null; setItem(key: string, value: string): void }
export function readPreferences(storage: PreferenceStorage): Preferences {
  try { return validatePreferences(JSON.parse(storage.getItem(PREFERENCES_KEY) ?? "null")); }
  catch { return { ...DEFAULT_PREFERENCES }; }
}
export function writePreferences(storage: PreferenceStorage, value: Preferences) {
  try { storage.setItem(PREFERENCES_KEY, JSON.stringify(validatePreferences(value))); } catch { /* Private browsing may disable storage. Keep the in-memory preference. */ }
}
export function resolveAppearance(preferences: Preferences, dark: boolean, reduced: boolean) {
  return { theme: preferences.theme === "system" ? dark ? "dark" : "light" : preferences.theme,
    motion: preferences.motion === "system" ? reduced ? "reduce" : "full" : preferences.motion };
}
export function sortReports(reports: ReportSummary[], sort: ReportSort) {
  const timestamp = (report: ReportSummary) => Date.parse(report.completed_at ?? report.started_at) || 0;
  const count = (value: number | undefined) => typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
  return [...reports].sort((a, b) => {
    if (sort === "newest" || sort === "oldest") return (sort === "oldest" ? 1 : -1) * (timestamp(a) - timestamp(b) || a.analysis_id - b.analysis_id);
    const left = count(sort.includes("issues") ? a.summary?.issues_detected : a.dataset?.rows);
    const right = count(sort.includes("issues") ? b.summary?.issues_detected : b.dataset?.rows);
    if (left === null || right === null) return left === right ? b.analysis_id - a.analysis_id : left === null ? 1 : -1;
    return (sort.startsWith("most") ? -1 : 1) * (left - right) || b.analysis_id - a.analysis_id;
  });
}

// Runs before styles paint. Kept self-contained so the server can inline it safely.
export function initializeAppearance() {
  try {
    const value = JSON.parse(localStorage.getItem("team-science.preferences.v1") ?? "null") ?? {};
    const root = document.documentElement;
    root.dataset.theme = value.theme === "light" || value.theme === "dark" ? value.theme : matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    root.dataset.accent = ["violet", "blue", "teal", "rose", "amber"].includes(value.accent) ? value.accent : "violet";
    root.dataset.palette = ["neutral", "forest", "slate", "plum", "sand"].includes(value.palette) ? value.palette : "neutral";
    root.dataset.density = value.density === "compact" ? "compact" : "comfortable";
    root.dataset.motion = value.motion === "reduce" || value.motion === "full" ? value.motion : matchMedia("(prefers-reduced-motion: reduce)").matches ? "reduce" : "full";
  } catch { /* CSS follows system preferences when storage is unavailable. */ }
}
