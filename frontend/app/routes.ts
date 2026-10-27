import { type RouteConfig, index, layout, route } from "@react-router/dev/routes";

export default [
  layout("routes/public.tsx", [
    index("routes/home.tsx"),
    route("example-report", "routes/example-report.tsx"),
    route("reports/sample", "routes/legacy-sample.tsx"),
    route("documentation", "routes/documentation.tsx"),
    route("login", "routes/login.tsx"),
    route("register", "routes/register.tsx"),
  ]),
  layout("routes/workspace.tsx", [
    route("dashboard", "routes/dashboard.tsx"),
    route("settings", "routes/settings.tsx"),
    route("upload", "routes/upload.tsx"),
    route("reports", "routes/reports.tsx"),
    route("reports/:analysisId", "routes/report.tsx"),
  ]),
] satisfies RouteConfig;
