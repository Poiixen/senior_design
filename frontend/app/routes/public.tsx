import { Outlet } from "react-router";
import { AppShell } from "~/components/app-shell";

export default function PublicLayout() {
  return <AppShell><Outlet /></AppShell>;
}
