import { useEffect, useRef, useState } from "react";
import { Form, Link, redirect, useNavigation } from "react-router";
import type { Route } from "./+types/home";
import { Icon } from "~/components/icon";
import { analyzeDataset, DEFAULT_PARSING_OPTIONS } from "~/lib/api";

export function meta() {
  return [{ title: "Upload a dataset | Team Science" }, { name: "description", content: "Explore missing values, duplicate rows, and outliers in your CSV dataset." }];
}

export async function clientAction({ request }: Route.ClientActionArgs) {
  const data = await request.formData();
  const file = data.get("file");
  if (!(file instanceof File) || !file.name.toLowerCase().endsWith(".csv") || file.size === 0) {
    return { error: "Choose a non-empty CSV file before starting analysis." };
  }
  try {
    const report = await analyzeDataset(file, {
      delimiter: String(data.get("delimiter") ?? DEFAULT_PARSING_OPTIONS.delimiter),
      has_header: data.get("has_header") !== "false",
      missing_values: [...new Set(String(data.get("missing_values") ?? "").split(",").map(marker => marker.trim()).filter(Boolean))],
    }, request.signal);
    return redirect(`/reports/${report.analysis_id}?uploaded=1`);
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    return { error: error instanceof Error ? error.message : "Unable to analyze this dataset. Please try again." };
  }
}

function fileSize(bytes: number) {
  return bytes < 1024 ? `${bytes} bytes` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function Home({ actionData }: Route.ComponentProps) {
  const navigation = useNavigation();
  const busy = navigation.state !== "idle";
  const submitting = useRef(false);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  useEffect(() => { if (!busy) submitting.current = false; }, [busy]);

  return <>
    <header className="page-heading"><p className="eyebrow">DATASET INGESTION</p><h1>Upload a dataset</h1><p className="muted">Select a CSV file and configure how the validator should interpret its contents.</p></header>
    <div className="upload-layout">
      <Form method="post" encType="multipart/form-data" className="panel upload-form" aria-busy={busy} onSubmit={event => {
        if (busy || submitting.current || !file || fileError) { event.preventDefault(); return; }
        submitting.current = true;
      }}>
        <fieldset disabled={busy}>
          <legend><span className="step-number">1</span>Select your file</legend>
          <label className={`file-picker ${file && !fileError ? "has-file" : ""} ${fileError ? "has-error" : ""}`}>
            <input name="file" type="file" accept=".csv,text/csv" aria-label="Choose a CSV file" aria-describedby="file-help file-feedback" required onChange={event => {
              const selected = event.currentTarget.files?.[0] ?? null;
              setFile(selected);
              const error = selected && !selected.name.toLowerCase().endsWith(".csv") ? "Choose a file with the .csv extension." : selected?.size === 0 ? "This file is empty. Choose a CSV with data to analyze." : "";
              setFileError(error);
              event.currentTarget.setCustomValidity(error);
            }} />
            <Icon name={file && !fileError ? "check" : "upload"} className="file-picker-icon" />
            <strong>{file ? file.name : "Choose a CSV file"}</strong>
            <span id="file-help">{file ? `${fileSize(file.size)} · Click to choose a different file` : "Browse files from your device (.csv)"}</span>
          </label>
          <div id="file-feedback" aria-live="polite">{fileError && <p className="field-error">{fileError}</p>}</div>
          <div className="options-heading"><span className="step-number">2</span><h2>Parsing options</h2></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="delimiter">Delimiter</label><select id="delimiter" name="delimiter" defaultValue={DEFAULT_PARSING_OPTIONS.delimiter}><option value=",">Comma ( , )</option><option value=";">Semicolon ( ; )</option><option value={"\t"}>Tab</option><option value="|">Pipe ( | )</option></select></div>
            <div className="field"><label htmlFor="has-header">Header row</label><select id="has-header" name="has_header" defaultValue={String(DEFAULT_PARSING_OPTIONS.has_header)}><option value="true">Yes — first row contains headers</option><option value="false">No — every row contains data</option></select></div>
            <div className="field field-wide"><label htmlFor="missing-values">Missing-value markers <span className="optional">(optional)</span></label><input id="missing-values" name="missing_values" type="text" placeholder="e.g. not recorded, missing" aria-describedby="markers-help" /><p className="field-hint" id="markers-help">Separate additional markers with commas. Empty cells and standard markers such as ?, NA, N/A, and NULL are already recognized.</p></div>
          </div>
        </fieldset>
        {actionData?.error && !busy && <div className="notice notice-error" role="alert"><Icon name="alert" /><div><strong>Unable to analyze this dataset</strong><p>{actionData.error}</p><p>Your file and options are still selected. You can adjust them and try again.</p></div></div>}
        {busy && <div className="notice notice-progress" role="status"><Icon name="spinner" className="spin" /><div><strong>Uploading and analyzing</strong><p>Checking {file?.name}. Your report will open when it is ready.</p></div></div>}
        <div className="form-footer"><span className={file && !fileError ? "ready-text" : "muted"}>{busy ? "Analysis in progress" : file && !fileError ? "Ready to analyze" : "Select a CSV file to enable analysis"}</span><button className="button button-primary" type="submit" disabled={!file || !!fileError || busy}>{busy ? "Analyzing dataset" : "Analyze dataset"}<Icon name={busy ? "spinner" : "arrow-right"} className={busy ? "spin" : ""} /></button></div>
      </Form>
      <aside className="upload-guide" aria-label="About dataset analysis">
        <div className="guide-card"><span className="guide-icon"><Icon name="report" /></span><h2>A clearer picture of your data</h2><p>One report brings your dataset’s shape and quality checks together.</p><ul><li><Icon name="check" />Missing values by column</li><li><Icon name="check" />Duplicate row totals</li><li><Icon name="check" />Numeric outliers to review</li><li><Icon name="check" />Structural warnings</li></ul></div>
        <div className="guide-note"><strong>New here?</strong><p>Explore a sample report to see how findings are organized.</p><Link to="/reports/sample">View sample report <Icon name="arrow-right" /></Link></div>
        <p className="privacy-note"><Icon name="file" />Only dataset metadata and findings are saved. Raw CSV rows are not stored.</p>
      </aside>
    </div>
  </>;
}
