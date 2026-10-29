import { ReportContent } from "./report";
import { sampleReport } from "~/lib/sample-report";

export function meta() { return [{ title: "Example report | Team Science" }]; }
export default function ExampleReport() {
  return <ReportContent report={sampleReport} isSample />;
}
