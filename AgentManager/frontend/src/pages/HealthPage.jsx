import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import EmptyResults from "../components/EmptyResults";
import FilterBar, { FilterChips, SearchField } from "../components/FilterBar";
import PageHeader from "../components/PageHeader";
import { findWorkspaceTarget, workspaceUrl } from "../workspaceLinks";

export default function HealthPage({ health, architecture, setHealth, notify }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("all");
  const [status, setStatus] = useState("all");
  const [expanded, setExpanded] = useState(null);
  const [testingOpenAI, setTestingOpenAI] = useState(false);
  const results = useMemo(() => health?.results || [], [health]);
  const openai = health?.openai || {
    configured: false,
    status: "not_configured",
  };
  const kinds = ["all", ...new Set(results.map((item) => item.kind))];
  const filtered = useMemo(() => results.filter((item) => (!query || `${item.name} ${item.message}`.toLowerCase().includes(query.toLowerCase())) && (kind === "all" || item.kind === kind) && (status === "all" || item.status === status)), [results, query, kind, status]);
  const clear = () => { setQuery(""); setKind("all"); setStatus("all"); };
  async function refresh() { try { setHealth(await api("/api/health")); notify("Health probes refreshed."); } catch (error) { notify(error.message, true); } }
  async function testOpenAI() {
    if (!openai.configured || testingOpenAI) return;
    setTestingOpenAI(true);
    try {
      const provider = await api("/api/openai/test", {
        method: "POST",
        body: "{}",
      });
      setHealth((current) => ({ ...current, openai: provider }));
      notify(`OpenAI connected with ${provider.response_model || provider.model}.`);
    } catch (error) {
      try {
        const provider = await api("/api/openai/status");
        setHealth((current) => ({ ...current, openai: provider }));
      } catch {
        // Keep the existing health snapshot when status refresh also fails.
      }
      notify(error.message, true);
    } finally {
      setTestingOpenAI(false);
    }
  }

  function openInWorkspace(result) {
    const target = findWorkspaceTarget(result, architecture);
    if (!target) return;
    navigate(workspaceUrl({
      agentId: target.agentId,
      mode: "test",
      toolName: target.toolName,
      context: "full",
    }));
  }

  return (
    <>
      <PageHeader eyebrow="CONTINUOUS GUARD" title="System health" description="Start with overall health, then narrow to the components you need to investigate." actions={<button className="secondary-button" onClick={refresh}>Refresh probes ↻</button>} />
      <section className={`openai-provider-card ${openai.status}`}>
        <div className="openai-provider-mark">AI</div>
        <div className="openai-provider-copy">
          <span>OPENAI RESPONSES API</span>
          <strong>
            {openai.status === "connected"
              ? "Live reasoning is connected"
              : openai.status === "error"
                ? "OpenAI needs attention"
                : openai.configured
                  ? "API key loaded — connection not tested"
                  : "API key is not configured"}
          </strong>
          <small>
            {openai.last_error
              || (openai.configured
                ? "Run one small readiness request to verify the key, project, model, and billing path."
                : "Copy .env.example to .env, add OPENAI_API_KEY, and restart make dev.")}
          </small>
        </div>
        <div className="openai-provider-config">
          <span><small>Model</small><strong>{openai.response_model || openai.model || "—"}</strong></span>
          <span><small>Reasoning</small><strong>{openai.reasoning_effort || "provider default"}</strong></span>
          <span><small>Project header</small><strong>{openai.project_configured ? "configured" : "automatic"}</strong></span>
        </div>
        <div className="openai-provider-action">
          <span className={`openai-provider-state ${openai.status}`}><i />{openai.status.replaceAll("_", " ")}</span>
          <button className="primary-button" onClick={testOpenAI} disabled={!openai.configured || testingOpenAI}>
            {testingOpenAI ? "Testing…" : "Test connection"}
          </button>
        </div>
      </section>
      <div className="health-summary">
        <div className="health-score"><span>{health ? `${health.healthy}/${health.total}` : "—"}</span><small>healthy components</small></div>
        <div className="health-copy"><strong>{health?.status === "healthy" ? "All monitored components are operational." : "Some components need attention."}</strong><p>Filter by type or status to isolate issues, then expand a row for probe details.</p></div>
      </div>
      <FilterBar resultCount={filtered.length} hasFilters={Boolean(query || kind !== "all" || status !== "all")} onClear={clear}>
        <SearchField value={query} onChange={setQuery} placeholder="Search components or probe messages" />
        <FilterChips value={kind} onChange={setKind} label="Component type" options={kinds} />
        <FilterChips value={status} onChange={setStatus} label="Health status" options={["all", "healthy", "degraded", "offline"]} />
      </FilterBar>
      <div className="health-table progressive">
        {filtered.length ? filtered.map((result) => {
          const rowId = `${result.kind}-${result.id}`;
          const target = findWorkspaceTarget(result, architecture);
          return (
            <div className={`health-row ${expanded === rowId ? "open" : ""}`} key={rowId}>
              <span className="health-kind">{result.kind}</span>
              <button className="health-main" onClick={() => setExpanded(expanded === rowId ? null : rowId)}>
                <span className="health-name">{result.name}</span>
                <span className={`health-state ${result.status}`}><i />{result.status}</span>
                <span className="health-latency">{result.latency_ms} ms</span>
                <b>{expanded === rowId ? "⌃" : "⌄"}</b>
              </button>
              {expanded === rowId && (
                <div className="health-detail">
                  <div><p>{result.message}</p><span>Last checked {new Date(result.checked_at).toLocaleString()}</span></div>
                  {result.status !== "healthy" && target && (
                    <button className="investigate-button" onClick={() => openInWorkspace(result)}>
                      Open in workspace <b>→</b>
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        }) : <EmptyResults onClear={clear} />}
      </div>
    </>
  );
}
