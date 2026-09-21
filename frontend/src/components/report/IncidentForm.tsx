import { useId, useState, type FormEvent } from "react";
import { Clock, Loader2, Send } from "lucide-react";
import { EXAMPLE_SCENARIOS } from "../../lib/examples";
import {
  MAX_REPORT_LENGTH, toAnalyzeRequest, validateReportForm, type FormErrors, type ReportFormValues,
} from "../../lib/reportForm";
import type { AnalyzeRequest } from "../../api";

interface IncidentFormProps {
  values: ReportFormValues;
  onChange: (values: ReportFormValues) => void;
  onSubmit: (request: AnalyzeRequest) => void;
  loading: boolean;
  /** Field errors returned by the backend (a 422), shown next to the same fields. */
  serverFieldErrors?: Record<string, string>;
}

const INPUT_CLASS =
  "mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-500 focus:border-teal-700 disabled:bg-slate-100";

function FieldError({ id, message }: { id: string; message?: string }) {
  return message ? (
    <p id={id} role="alert" className="mt-1 text-sm font-medium text-red-800">{message}</p>
  ) : null;
}

/** Local datetime in the format <input type="datetime-local"> expects. */
function nowForDatetimeLocal(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

export function IncidentForm({ values, onChange, onSubmit, loading, serverFieldErrors = {} }: IncidentFormProps) {
  const uid = useId();
  const [clientErrors, setClientErrors] = useState<FormErrors>({});
  const set = (patch: Partial<ReportFormValues>) => onChange({ ...values, ...patch });

  const error = (field: keyof ReportFormValues, apiField: string): string | undefined =>
    clientErrors[field] ?? serverFieldErrors[apiField];

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (loading) return;
    const errors = validateReportForm(values);
    setClientErrors(errors);
    if (Object.keys(errors).length > 0) return;
    onSubmit(toAnalyzeRequest(values));
  }

  const ids = { text: `${uid}-text`, lat: `${uid}-lat`, lon: `${uid}-lon`, ts: `${uid}-ts`, rid: `${uid}-rid` };
  const length = values.rawText.length;

  return (
    <form onSubmit={handleSubmit} noValidate aria-busy={loading} className="space-y-5">
      <div>
        <label htmlFor={ids.text} className="block text-sm font-semibold text-slate-900">Emergency report</label>
        <textarea
          id={ids.text}
          value={values.rawText}
          onChange={(e) => set({ rawText: e.target.value })}
          rows={6}
          disabled={loading}
          aria-invalid={Boolean(error("rawText", "raw_text"))}
          aria-describedby={`${ids.text}-help ${ids.text}-err`}
          placeholder="Describe what was reported, e.g. “Two vehicles collided at an intersection during heavy rain. Four people appear injured. One person may be unconscious.”"
          className={`${INPUT_CLASS} resize-y leading-relaxed`}
        />
        <div className="mt-1 flex flex-wrap items-start justify-between gap-2">
          <p id={`${ids.text}-help`} className="text-xs text-slate-600">
            Free text. ResQAI only uses what the report says; missing details stay missing.
          </p>
          <p className={`text-xs tabular-nums ${length > MAX_REPORT_LENGTH ? "font-semibold text-red-800" : "text-slate-600"}`}>
            {length} / {MAX_REPORT_LENGTH}
          </p>
        </div>
        <FieldError id={`${ids.text}-err`} message={error("rawText", "raw_text")} />
      </div>

      <fieldset className="rounded-md border border-slate-200 p-3 sm:p-4">
        <legend className="px-1 text-sm font-semibold text-slate-900">
          Location <span className="font-normal text-slate-600">(optional)</span>
        </legend>
        <p className="text-xs text-slate-600">
          Without coordinates the analysis still runs, but matched resources cannot be ranked by distance.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor={ids.lat} className="block text-sm font-medium text-slate-800">Latitude</label>
            <input
              id={ids.lat} inputMode="decimal" autoComplete="off" value={values.latitude} disabled={loading}
              onChange={(e) => set({ latitude: e.target.value })} placeholder="e.g. 39.10"
              aria-invalid={Boolean(error("latitude", "latitude"))} aria-describedby={`${ids.lat}-err`}
              className={INPUT_CLASS}
            />
            <FieldError id={`${ids.lat}-err`} message={error("latitude", "latitude")} />
          </div>
          <div>
            <label htmlFor={ids.lon} className="block text-sm font-medium text-slate-800">Longitude</label>
            <input
              id={ids.lon} inputMode="decimal" autoComplete="off" value={values.longitude} disabled={loading}
              onChange={(e) => set({ longitude: e.target.value })} placeholder="e.g. -94.58"
              aria-invalid={Boolean(error("longitude", "longitude"))} aria-describedby={`${ids.lon}-err`}
              className={INPUT_CLASS}
            />
            <FieldError id={`${ids.lon}-err`} message={error("longitude", "longitude")} />
          </div>
        </div>
      </fieldset>

      <details className="rounded-md border border-slate-200 px-3 py-2 sm:px-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-900">
          Additional details <span className="font-normal text-slate-600">(optional)</span>
        </summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor={ids.ts} className="block text-sm font-medium text-slate-800">Report time</label>
            <div className="flex gap-2">
              <input
                id={ids.ts} type="datetime-local" value={values.timestamp} disabled={loading}
                onChange={(e) => set({ timestamp: e.target.value })}
                aria-invalid={Boolean(error("timestamp", "timestamp"))} aria-describedby={`${ids.ts}-help ${ids.ts}-err`}
                className={INPUT_CLASS}
              />
              <button
                type="button" disabled={loading} onClick={() => set({ timestamp: nowForDatetimeLocal() })}
                className="mt-1 inline-flex shrink-0 items-center gap-1 rounded-md border border-slate-300 bg-white px-2.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
              >
                <Clock aria-hidden className="size-3.5" /> Use now
              </button>
            </div>
            <p id={`${ids.ts}-help`} className="mt-1 text-xs text-slate-600">
              Only sent if you set it; time-of-day details are never assumed.
            </p>
            <FieldError id={`${ids.ts}-err`} message={error("timestamp", "timestamp")} />
          </div>
          <div>
            <label htmlFor={ids.rid} className="block text-sm font-medium text-slate-800">Report ID</label>
            <input
              id={ids.rid} value={values.reportId} disabled={loading} autoComplete="off"
              onChange={(e) => set({ reportId: e.target.value })} placeholder="Generated if left empty"
              aria-invalid={Boolean(error("reportId", "report_id"))} aria-describedby={`${ids.rid}-err`}
              className={INPUT_CLASS}
            />
            <FieldError id={`${ids.rid}-err`} message={error("reportId", "report_id")} />
          </div>
        </div>
      </details>

      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Example scenarios (demo text)</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {EXAMPLE_SCENARIOS.map((scenario) => (
            <button
              key={scenario.id} type="button" disabled={loading}
              onClick={() => { set({ rawText: scenario.text }); setClientErrors({}); }}
              className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
            >
              {scenario.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit" disabled={loading}
          className="inline-flex items-center gap-2 rounded-md bg-teal-700 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-70"
        >
          {loading ? <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> : <Send aria-hidden className="size-4" />}
          {loading ? "Analyzing…" : "Analyze Incident"}
        </button>
        <span role="status" className="text-sm text-slate-700">{loading ? "Analyzing incident…" : ""}</span>
      </div>
    </form>
  );
}
