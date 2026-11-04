import { useEffect, useRef, useState } from "react";
import { Form, Link, redirect, useNavigation } from "react-router";
import type { Route } from "./+types/upload";
import { Icon } from "~/components/icon";
import { analyzeDataset, ApiError, DEFAULT_PARSING_OPTIONS, getCurrentUser } from "~/lib/api";

export function meta() { return [{ title: "Upload a dataset | Team Science" }]; }
export async function clientLoader() {
  try { return { user: await getCurrentUser() }; }
  catch (error) { if (error instanceof ApiError && error.status === 401) throw redirect("/login?next=/upload"); throw error; }
}
const SUPPORTED = [".csv", ".tsv", ".xlsx", ".json"] as const;
const extensionOf = (name: string) => `.${name.toLowerCase().split(".").pop() ?? ""}`;
const isSupported = (name: string) => SUPPORTED.includes(extensionOf(name) as typeof SUPPORTED[number]);
const formatLabel = (name: string) => ({ ".csv": "CSV", ".tsv": "TSV", ".xlsx": "Excel", ".json": "JSON" } as Record<string, string>)[extensionOf(name)] ?? "Unknown";

export async function clientAction({ request }: Route.ClientActionArgs) {
  const data = await request.formData();
  const file = data.get("file");
  if (!(file instanceof File) || !isSupported(file.name)) return { error: "Choose a CSV, TSV, XLSX, or JSON dataset." };
  if (file.size === 0) return { error: "Choose a non-empty dataset before starting analysis." };
  const extension = extensionOf(file.name);
  try {
    const report = await analyzeDataset(file, {
      delimiter: extension === ".tsv" ? "\t" : String(data.get("delimiter") ?? DEFAULT_PARSING_OPTIONS.delimiter),
      has_header: data.get("has_header") !== "false",
      missing_values: [...new Set(String(data.get("missing_values") ?? "").split(",").map(marker => marker.trim()).filter(Boolean))],
    }, request.signal);
    return redirect(`/reports/${report.analysis_id}?uploaded=1`);
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    return { error: error instanceof Error ? error.message : "Unable to analyze this dataset. Please try again." };
  }
}

function fileSize(bytes: number) { return bytes < 1024 ? `${bytes} bytes` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`; }

export default function Upload({ actionData }: Route.ComponentProps) {
  const navigation = useNavigation();
  const busy = navigation.state !== "idle";
  const submitting = useRef(false);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const extension = file ? extensionOf(file.name) : "";
  const showDelimiter = extension === ".csv";
  const showDelimitedOptions = extension === ".csv" || extension === ".tsv";
  useEffect(() => { if (!busy) submitting.current = false; }, [busy]);
  return <>
    <header className="page-heading"><p className="eyebrow">DATASET INGESTION</p><h1>Upload a dataset</h1><p className="muted">Select a CSV, TSV, Excel, or JSON file and configure the applicable parsing options.</p></header>
    <div className="upload-layout">
      <Form method="post" encType="multipart/form-data" className="panel upload-form" aria-busy={busy} onSubmit={event => { if (busy || submitting.current || !file || fileError) { event.preventDefault(); return; } submitting.current = true; }}>
        <fieldset disabled={busy}>
          <legend><span className="step-number">1</span>Select your file</legend>
          <label className={`file-picker ${file && !fileError ? "has-file" : ""} ${fileError ? "has-error" : ""}`}>
            <input name="file" type="file" accept=".csv,.tsv,.xlsx,.json,text/csv,text/tab-separated-values,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" aria-label="Choose a dataset" aria-describedby="file-help file-feedback" required onChange={event => {
              const selected = event.currentTarget.files?.[0] ?? null; setFile(selected);
              const error = selected && !isSupported(selected.name) ? "Choose a CSV, TSV, XLSX, or JSON file." : selected?.size === 0 ? "This file is empty. Choose a dataset with data to analyze." : "";
              setFileError(error); event.currentTarget.setCustomValidity(error);
            }} />
            <Icon name={file && !fileError ? "check" : "upload"} className="file-picker-icon" />
            <strong>{file ? file.name : "Choose a dataset"}</strong>
            <span id="file-help">{file ? `${formatLabel(file.name)} · ${fileSize(file.size)} · Click to choose a different file` : "Supported formats: CSV, TSV, XLSX, JSON"}</span>
          </label>
          <div id="file-feedback" aria-live="polite">{fileError && <p className="field-error">{fileError}</p>}</div>
          <div className="options-heading"><span className="step-number">2</span><h2>Parsing options</h2></div>
          <div className="form-grid">
            {showDelimiter && <div className="field"><label htmlFor="delimiter">Delimiter</label><select id="delimiter" name="delimiter" defaultValue={DEFAULT_PARSING_OPTIONS.delimiter}><option value=",">Comma ( , )</option><option value=";">Semicolon ( ; )</option><option value={"\t"}>Tab</option><option value="|">Pipe ( | )</option></select></div>}
            {showDelimitedOptions && <div className="field"><label htmlFor="has-header">Header row</label><select id="has-header" name="has_header" defaultValue={String(DEFAULT_PARSING_OPTIONS.has_header)}><option value="true">Yes — first row contains headers</option><option value="false">No — every row contains data</option></select></div>}
            {showDelimitedOptions && <div className="field field-wide"><label htmlFor="missing-values">Missing-value markers <span className="optional">(optional)</span></label><input id="missing-values" name="missing_values" type="text" placeholder="e.g. not recorded, missing" aria-describedby="markers-help" /><p className="field-hint" id="markers-help">Separate additional markers with commas. Empty cells and standard markers such as ?, NA, N/A, and NULL are already recognized.</p></div>}
            {file && !showDelimitedOptions && <p className="field-hint field-wide">{formatLabel(file.name)} files use their built-in tabular structure and need no parsing options.</p>}
          </div>
        </fieldset>
        {actionData?.error && !busy && <div className="notice notice-error" role="alert"><Icon name="alert" /><div><strong>Unable to analyze this dataset</strong><p>{actionData.error}</p><p>Your file and options are still selected. You can adjust them and try again.</p></div></div>}
        {busy && <div className="notice notice-progress" role="status"><Icon name="spinner" className="spin" /><div><strong>Uploading and analyzing</strong><p>Checking {file?.name}. Your report will open when it is ready.</p></div></div>}
        <div className="form-footer"><span className={file && !fileError ? "ready-text" : "muted"}>{busy ? "Analysis in progress" : file && !fileError ? "Ready to analyze" : "Select a dataset to enable analysis"}</span><button className="button button-primary" type="submit" disabled={!file || !!fileError || busy}>{busy ? "Analyzing dataset" : "Analyze dataset"}<Icon name={busy ? "spinner" : "arrow-right"} className={busy ? "spin" : ""} /></button></div>
      </Form>
      <aside className="upload-guide" aria-label="About dataset analysis"><div className="guide-card"><span className="guide-icon"><Icon name="report" /></span><h2>A clearer picture of your data</h2><p>One report brings your dataset’s shape and quality checks together.</p><ul><li><Icon name="check" />Missing values by column</li><li><Icon name="check" />Duplicate row totals</li><li><Icon name="check" />Numeric outliers to review</li><li><Icon name="check" />Structural warnings</li></ul></div><div className="guide-note"><strong>New here?</strong><p>Explore a sample report to see how findings are organized.</p><Link to="/reports/sample">View sample report <Icon name="arrow-right" /></Link></div><p className="privacy-note"><Icon name="file" />Only dataset metadata and findings are saved. Raw dataset rows are not stored.</p></aside>
    </div>
  </>;
}
