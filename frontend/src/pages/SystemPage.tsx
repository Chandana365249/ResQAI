import { ModelInfoCards } from "../components/status/ModelInfoCards";
import { SystemStatusCard } from "../components/status/SystemStatusCard";

export function SystemPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">System and models</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-700">
          Live status of the ResQAI backend and the two severity models it can route between.
        </p>
      </div>
      <SystemStatusCard />
      <ModelInfoCards />
    </div>
  );
}
