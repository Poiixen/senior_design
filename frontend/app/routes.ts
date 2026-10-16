import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/home.tsx"),
  route("reports", "routes/reports.tsx"),
  route("reports/:analysisId", "routes/report.tsx"),
  route("documentation", "routes/documentation.tsx"),
  route("login", "routes/login.tsx"),
  route("register", "routes/register.tsx"),
] satisfies RouteConfig;
