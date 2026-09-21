import type { ReactNode } from "react";
import type { AnalyzeResponse } from "../../api";
import { humanize, uniqueStrings } from "../../lib/format";
import { Card, OriginTag, type Origin } from "../common/Card";

function Block({ title, origin, items: rawItems, empty }: { title: string; origin: Origin; items: string[]; empty: string }) {
  // The API can return the same sentence for several resources; show each distinct one once.
  const items = uniqueStrings(rawItems);
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        <OriginTag origin={origin} />
      </div>
      {items.length === 0 ? (
        <p className="mt-1 text-sm text-slate-600">{empty}</p>
      ) : (
        <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-slate-800">
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      )}
    </div>
  );
}

function Section({ children }: { children: ReactNode }) {
  return <div className="space-y-5">{children}</div>;
}

/** "Why did ResQAI produce this result?" -- the backend's explanation, grouped by where each part came from. */
export function ExplanationCard({ result }: { result: AnalyzeResponse }) {
  const { explanation } = result;

  // A display filter over what the API already returned: fields the report worded
  // as possible/uncertain, so "what is uncertain" is visible in one place.
  const uncertain = Object.entries(result.extracted_information).flatMap(([, fields]) =>
    Object.entries(fields)
      .filter(([, f]) => f.certainty === "possible" || f.certainty === "uncertain")
      .map(([name, f]) => `${humanize(name)} (${f.certainty})`),
  );

  return (
    <Card id="explanation" title="Why ResQAI produced this result" description="Each part is labelled by where it came from.">
      <Section>
        <Block title="What the report said" origin="report" items={explanation.report_facts} empty="No report text recorded." />
        <Block title="Why these risks were flagged" origin="rules" items={explanation.risk_reasons} empty="No risk indicators were flagged." />
        <Block title="What the model did" origin="model" items={explanation.ml_reasons} empty="No model explanation was returned." />
        <Block title="Why these resources" origin="demo" items={explanation.resource_reasons} empty="No resources were matched." />
        <Block
          title="What is uncertain"
          origin="report"
          items={uncertain}
          empty="Every extracted detail was stated with confirmed wording."
        />
      </Section>
    </Card>
  );
}
