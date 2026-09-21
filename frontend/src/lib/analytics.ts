/**
 * Session analytics: pure aggregation over the records this browser has
 * actually stored. Every number is computed from those records -- nothing
 * is hard-coded, sampled or estimated.
 */

import type { PredictionSource, Priority } from "../api";
import type { SessionRecord } from "./sessionHistory";

export interface Count<K extends string = string> {
  key: K;
  count: number;
}

export interface SessionSummary {
  total: number;
  predictionAvailable: number;
  predictionUnavailable: number;
  disagreements: number;
  /** null when there are no records (avoid a misleading 0%). */
  disagreementRate: number | null;
  predictionSources: Count<PredictionSource>[];
  predictedSeverities: Count[];
  priorities: Count<Priority>[];
  riskIndicators: Count[];
  mostFrequentRiskIndicator: Count | null;
}

function tally<K extends string>(keys: K[]): Count<K>[] {
  const counts = new Map<K, number>();
  for (const key of keys) counts.set(key, (counts.get(key) ?? 0) + 1);
  // most frequent first; ties broken alphabetically so output is deterministic
  return Array.from(counts, ([key, count]) => ({ key, count })).sort(
    (a, b) => b.count - a.count || a.key.localeCompare(b.key),
  );
}

export function summarizeSession(records: SessionRecord[]): SessionSummary {
  const total = records.length;
  const predictionAvailable = records.filter((r) => r.predictionAvailable).length;
  const disagreements = records.filter((r) => r.modelRuleDisagreement).length;
  const riskIndicators = tally(records.flatMap((r) => r.riskIndicators));

  return {
    total,
    predictionAvailable,
    predictionUnavailable: total - predictionAvailable,
    disagreements,
    disagreementRate: total === 0 ? null : disagreements / total,
    predictionSources: tally(records.map((r) => r.predictionSource)),
    predictedSeverities: tally(
      records.flatMap((r) => (r.predictionAvailable && r.predictedSeverity ? [r.predictedSeverity] : [])),
    ),
    priorities: tally(records.map((r) => r.priority)),
    riskIndicators,
    mostFrequentRiskIndicator: riskIndicators[0] ?? null,
  };
}
