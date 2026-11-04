import { redirect } from "react-router";
import type { Route } from "./+types/legacy-sample";

export function loader({ request }: Route.LoaderArgs) {
  return redirect(`/example-report${new URL(request.url).search}`);
}
