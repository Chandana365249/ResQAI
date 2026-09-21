import type { ReactNode } from "react";
import type { AnalyzeResponse } from "../../api";
import { formatCoordinate, formatTimestamp, humanize } from "../../lib/format";
import { Card } from "../common/Card";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-2 py-1.5 text-sm sm:grid-cols-[10rem_1fr]">
      <dt className="text-slate-600">{label}</dt>
      <dd className="min-w-0 font-medium text-slate-900">{children}</dd>
    </div>
  );
}

const NOT_PROVIDED = <span className="font-normal text-slate-600">Not provided</span>;

export function IncidentSummary({ result }: { result: AnalyzeResponse }) {
  const { report, incident, resources } = result;
  const { location } = resources;
  const timestamp = formatTimestamp(report.timestamp);

  return (
    <Card id="incident-summary" title="Report details" origin="report">
      <dl className="divide-y divide-slate-100">
        <Row label="Incident type">
          {humanize(incident.incident_type)}
          {incident.incident_subtype ? <span className="font-normal text-slate-700"> — {incident.incident_subtype}</span> : null}
        </Row>
        <Row label="Extraction confidence">
          {humanize(incident.overall_extraction_confidence)}
          <span className="block text-xs font-normal text-slate-600">
            A coarse rule-based category, not a calibrated probability.
          </span>
        </Row>
        <Row label="Report ID"><span className="font-mono text-xs">{report.report_id}</span></Row>
        <Row label="Source">{report.source ?? NOT_PROVIDED}</Row>
        <Row label="Report time">{timestamp ?? NOT_PROVIDED}</Row>
        <Row label="Location">
          {location.available ? (
            <span className="tabular-nums">
              {formatCoordinate(location.latitude)}, {formatCoordinate(location.longitude)}
            </span>
          ) : (
            <span className="font-normal text-slate-700">
              Not provided — proximity ranking unavailable.
            </span>
          )}
        </Row>
      </dl>
    </Card>
  );
}
