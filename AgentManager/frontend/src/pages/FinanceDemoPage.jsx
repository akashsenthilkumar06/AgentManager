import { useState } from "react";
import { api } from "../api";
import PageHeader from "../components/PageHeader";

function money(value) {
  return `$${Number(value || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function FinanceDemoPage({ notify }) {
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  async function runDemo() {
    setRunning(true);
    try {
      const next = await api("/api/demos/finance-correction", { method: "POST", body: "{}" });
      setResult(next);
      notify(next.data_source === "supabase" ? "Supabase finance demo completed." : "Local demo data completed; add Supabase variables to connect your project.");
    } catch (error) { notify(error.message, true); } finally { setRunning(false); }
  }
  return <>
    <PageHeader eyebrow="SOURCE-BACKED DEMO" title="Finance correction" description="Show an employee agent making a measurable mistake, then show the Manager independently checking the finance source and correcting it." actions={<button className="primary-button" onClick={runDemo} disabled={running}>{running ? "Checking finance data…" : "Run finance demo"}</button>} />
    {!result ? <section className="finance-empty"><span>◈</span><h2>Ready for the manager review</h2><p>The run intentionally omits one overdue invoice when two or more are present. The Manager compares that answer with the same finance data source and returns the corrected total.</p><button className="primary-button" onClick={runDemo} disabled={running}>{running ? "Running…" : "Run demo"}</button></section> : <div className="finance-demo-grid">
      <section className="finance-source-card"><p className="eyebrow">1 · FINANCE SOURCE</p><h2>{result.data_source === "supabase" ? "Supabase connected" : "Local demo fallback"}</h2><p>Read {result.rows_reviewed} rows from <code>{result.table}</code>. The source is queried server-side; no database secret reaches this page.</p><small>Data source: {result.data_source}</small></section>
      <section className="finance-analysis-card failed"><p className="eyebrow">2 · EMPLOYEE ANSWER</p><h2>Incomplete analysis</h2><div className="finance-number">{money(result.employee_analysis.overdue_total)}</div><p>Reported overdue invoices: {result.employee_analysis.invoice_ids.join(", ")}</p><small>{result.employee_analysis.recommendation}</small></section>
      <section className="finance-analysis-card corrected"><p className="eyebrow">3 · MANAGER CORRECTION</p><h2>{result.manager_review.status === "correction_required" ? "Failure detected" : "Answer verified"}</h2><div className="finance-number">{money(result.corrected_analysis.overdue_total)}</div><p>Correct overdue invoices: {result.corrected_analysis.invoice_ids.join(", ")}</p><small>{result.manager_review.reason}</small>{result.manager_review.missed_invoice_ids.length > 0 && <div className="finance-missed">Missed: {result.manager_review.missed_invoice_ids.join(", ")}</div>}</section>
    </div>}
  </>;
}
