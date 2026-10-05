import type { CSSProperties } from "react";

const paths = {
  upload: "M12 16V4m-5 5 5-5 5 5M4 16v4h16v-4",
  report: "M5 3h14v18H5zM8 7h8M8 11h8M8 15h5",
  clock: "M12 8v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  help: "M9 9a3 3 0 1 1 5 2c-2 1-2 2-2 3m0 3h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  check: "m5 12 4 4L19 6",
  "arrow-right": "M4 12h16m-6-6 6 6-6 6",
  "arrow-down": "M12 4v16m-6-6 6 6 6-6",
  table: "M3 4h18v16H3zM3 9h18M9 9v11M15 9v11",
  chart: "M4 20V10m8 10V4m8 16v-7",
  columns: "M3 4h18v16H3zM9 4v16M15 4v16",
  duplicate: "M8 8h12v12H8zM4 16V4h12",
  x: "m6 6 12 12M6 18 18 6",
  file: "M14 3H5v18h14V8zM14 3v5h5M8 12h8M8 16h5",
  spinner: "M21 12a9 9 0 1 1-9-9",
  alert: "m12 3 10 18H2zM12 9v5m0 3h.01",
} as const;

export function Icon({ name, className = "", style }: { name: keyof typeof paths; className?: string; style?: CSSProperties }) {
  return <svg className={`icon ${className}`} style={style} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
