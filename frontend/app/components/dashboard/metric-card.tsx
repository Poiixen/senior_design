import type { ComponentProps, ReactNode } from "react";
import { Icon } from "~/components/icon";

export function MetricCard({ label, value, detail, icon, tone = "purple" }: {
  label: string; value: ReactNode; detail: string;
  icon: ComponentProps<typeof Icon>["name"]; tone?: "purple" | "green" | "amber" | "blue";
}) {
  return <article className="dashboard-metric">
    <span className={`dashboard-icon tone-${tone}`}><Icon name={icon} /></span>
    <h3>{label}</h3><p className="dashboard-metric-value">{value}</p><p className="muted">{detail}</p>
  </article>;
}
