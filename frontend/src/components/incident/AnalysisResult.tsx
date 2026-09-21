import type { AnalyzeResponse } from "../../api";
import { WarningPanel } from "../common/WarningPanel";
import { DecisionSummary } from "../decision/DecisionSummary";
import { DisagreementAlert } from "../ml/DisagreementAlert";
import { MlPredictionCard } from "../ml/MlPredictionCard";
import { ResourceResults } from "../resources/ResourceResults";
import { RiskIndicatorList } from "../risk/RiskIndicatorList";
import { AnalysisHeader } from "./AnalysisHeader";
import { EvidencePanel } from "./EvidencePanel";
import { ExplanationCard } from "./ExplanationCard";
import { ExtractedInformation } from "./ExtractedInformation";
import { IncidentSummary } from "./IncidentSummary";

/**
 * Composition only. Order follows the visual hierarchy: incident and
 * priority, disagreement (if any), risk and decision, the model, resources,
 * then the supporting evidence and explanation. Every value shown was
 * produced by the backend.
 */
export function AnalysisResult({ result }: { result: AnalyzeResponse }) {
  return (
    <div className="space-y-5" data-testid="analysis-result">
      <AnalysisHeader result={result} />
      <DisagreementAlert result={result} />

      <div className="grid gap-5 lg:grid-cols-2">
        <RiskIndicatorList indicators={result.risk_indicators} />
        <DecisionSummary decision={result.decision} />
      </div>

      <MlPredictionCard result={result} />
      <ResourceResults section={result.resources} />

      <div className="grid gap-5 lg:grid-cols-2">
        <ExtractedInformation data={result.extracted_information} />
        <div className="space-y-5">
          <EvidencePanel evidence={result.evidence} />
          <IncidentSummary result={result} />
        </div>
      </div>

      <ExplanationCard result={result} />
      <WarningPanel warnings={result.warnings} alreadyShown={result.ml_prediction.warnings} />

      <p className="rounded-md bg-slate-100 p-3 text-xs text-slate-700">{result.disclaimer}</p>
    </div>
  );
}
