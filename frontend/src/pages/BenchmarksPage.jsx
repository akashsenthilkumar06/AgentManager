import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import PageHeader from "../components/PageHeader";

function formatMetric(metric, value) {
  return metric.unit === "milliseconds" ? `${value} ms` : `${value}%`;
}

function MetricChart({ metric }) {
  const maximum = metric.unit === "milliseconds"
    ? Math.max(1, metric.baseline, metric.managed)
    : 100;
  const baselineWidth = Math.max(2, (metric.baseline / maximum) * 100);
  const managedWidth = Math.max(2, (metric.managed / maximum) * 100);
  const delta = metric.managed - metric.baseline;
  const improved = metric.higher_is_better ? delta > 0 : delta < 0;
  const declined = metric.higher_is_better ? delta < 0 : delta > 0;
  return <article className="benchmark-metric-card">
    <div className="benchmark-metric-heading"><div><span>{metric.label}</span><small>{metric.higher_is_better ? "Higher is better" : "Lower is better"}</small></div><b className={improved ? "improved" : declined ? "declined" : ""}>{delta === 0 ? "No change" : `${delta > 0 ? "+" : ""}${delta.toFixed(1)}${metric.unit === "milliseconds" ? " ms" : " pts"}`}</b></div>
    <div className="benchmark-bars">
      <div><span>Without Manager</span><div><i style={{ width: `${baselineWidth}%` }} /></div><strong>{formatMetric(metric, metric.baseline)}</strong></div>
      <div className="managed"><span>With Manager</span><div><i style={{ width: `${managedWidth}%` }} /></div><strong>{formatMetric(metric, metric.managed)}</strong></div>
    </div>
  </article>;
}

export default function BenchmarksPage({ agents, notify }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedAgent = searchParams.get("agent");
  const [agentId, setAgentId] = useState(requestedAgent || agents[0]?.id || "");
  const [runs, setRuns] = useState([]);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    api("/api/benchmarks")
      .then(setRuns)
      .catch((error) => notify(error.message, true));
  }, [notify]);

  const agentRuns = useMemo(() => runs.filter((run) => run.agent_id === agentId), [runs, agentId]);
  const run = agentRuns[0] || null;
  const score = run?.metrics.find((metric) => metric.id === "overall_score");
  const scoreDelta = score ? score.managed - score.baseline : 0;

  async function runBenchmark() {
    if (!agentId || running) return;
    setRunning(true);
    try {
      const next = await api("/api/benchmarks", {
        method: "POST",
        body: JSON.stringify({ agent_id: agentId }),
      });
      setRuns((items) => [next, ...items.filter((item) => item.id !== next.id)]);
      notify(`Benchmark completed for ${next.agent_name}.`);
    } catch (error) {
      notify(error.message, true);
    } finally {
      setRunning(false);
    }
  }

  return <>
    <PageHeader eyebrow="FLEET EVALUATION" title="Agent benchmarks" description="Run the same executable capability scenarios against the original agent configuration and its current Manager-enhanced state." actions={<button className="primary-button" onClick={runBenchmark} disabled={running || !agentId}>{running ? "Running paired probes…" : "Run benchmark"}</button>} />
    <section className="benchmark-control-strip">
      <label><span>Agent under test</span><select value={agentId} onChange={(event) => { setAgentId(event.target.value); setSearchParams({ agent: event.target.value }); }}>{agents.map((agent) => <option value={agent.id} key={agent.id}>{agent.name}</option>)}</select></label>
      <div><span>Method</span><strong>Paired real-tool probes</strong><small>No LLM scoring · identical inputs</small></div>
      <div><span>Previous runs</span><strong>{agentRuns.length}</strong><small>{run ? `Latest ${new Date(run.created_at).toLocaleString()}` : "No benchmark yet"}</small></div>
    </section>

    {run ? <div className="benchmark-results">
      <section className="benchmark-score-hero">
        <div><p className="eyebrow">LATEST COMPARISON</p><h2>{run.agent_name}</h2><p>{run.summary}</p><div className="benchmark-evidence-tags">{run.evidence.map((item) => <span key={item}>✓ {item}</span>)}</div></div>
        <div className="benchmark-score-pair">
          <article><span>Without Manager</span><strong>{score?.baseline || 0}</strong><small>original configuration</small></article>
          <b>→</b>
          <article className="managed"><span>With Manager</span><strong>{score?.managed || 0}</strong><small>{scoreDelta === 0 ? "measured parity" : `${scoreDelta > 0 ? "+" : ""}${scoreDelta.toFixed(1)} point change`}</small></article>
        </div>
      </section>

      <section className="benchmark-chart-section">
        <div className="benchmark-section-heading"><div><p className="eyebrow">METRIC BREAKDOWN</p><h2>Side-by-side performance</h2></div><small>Bars use observed executions, not estimated model quality.</small></div>
        <div className="benchmark-metric-grid">{run.metrics.filter((metric) => metric.id !== "overall_score").map((metric) => <MetricChart metric={metric} key={metric.id} />)}</div>
      </section>

      <section className="benchmark-scenarios">
        <div className="benchmark-section-heading"><div><p className="eyebrow">SCENARIO EVIDENCE</p><h2>What actually ran</h2></div><small>{run.scenarios.length} identical scenario{run.scenarios.length === 1 ? "" : "s"}</small></div>
        {run.scenarios.length ? <div className="benchmark-scenario-table">
          <div className="benchmark-scenario-head"><span>Capability scenario</span><span>Without Manager</span><span>With Manager</span></div>
          {run.scenarios.map((scenario) => <article key={scenario.id}><div><strong>{scenario.required_tool}</strong><small>{scenario.objective}</small><code>{JSON.stringify(scenario.probe_input)}</code></div>{["baseline", "managed"].map((side) => { const result = scenario[side]; return <div className={`benchmark-side-result ${result.status}`} key={side}><span><i />{result.status}</span><strong>{result.tool_name}</strong><small>{result.status === "passed" ? `${result.latency_ms} ms · ${result.output_keys.length} output fields` : result.error}</small></div>; })}</article>)}
        </div> : <div className="benchmark-empty"><span>◎</span><h2>No executable tools yet</h2><p>Connect an MCP endpoint or attach a registered tool, then rerun the benchmark.</p></div>}
      </section>
    </div> : <section className="benchmark-empty large"><span>◎</span><h2>Measure the Manager’s real effect</h2><p>Select an agent and run a paired benchmark. The comparison stays honest: if the Manager has not improved this scenario set, the graph will show parity.</p><button className="primary-button" onClick={runBenchmark} disabled={running}>{running ? "Running…" : "Run first benchmark"}</button></section>}
  </>;
}
