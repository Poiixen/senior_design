import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/home.tsx"),
  route("reports", "routes/reports.tsx"),
  route("reports/:analysisId", "routes/report.tsx"),
  route("documentation", "routes/documentation.tsx"),
] satisfies RouteConfig;
