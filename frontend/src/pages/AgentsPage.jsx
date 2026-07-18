import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import EmptyResults from "../components/EmptyResults";
import FilterBar, { FilterChips, SearchField, ViewToggle } from "../components/FilterBar";
import PageHeader from "../components/PageHeader";

function AgentCard({ agent, onOpen, view, conversations }) {
  return <article className={`agent-card selectable ${view === "list" ? "list-view" : ""}`} role="button" tabIndex="0" onClick={onOpen} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onOpen(); } }}>
    <div className="agent-card-head"><span className="agent-avatar">{agent.name.charAt(0)}</span><div><h2>{agent.name}</h2><p>{agent.owner}</p></div><span className={`connection-badge ${agent.status}`}><i />{agent.status}</span></div>
    <p className="agent-description">{agent.description}</p>
    <div className="agent-at-a-glance"><span><b>{agent.mcp_tools.length}</b> tools</span><span><b>{conversations}</b> chats</span><span><b>{agent.features.length}</b> capabilities</span></div>
    {agent.imported && <div className="imported-agent-tag"><span>▱</span> Connected local directory</div>}
    <div className="agent-card-action"><span>Enter agent workspace</span><b>→</b></div>
  </article>;
}

function ImportAgentModal({ onClose, onImported, notify }) {
  const [path, setPath] = useState("");
  const [name, setName] = useState("");
  const [command, setCommand] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [start, setStart] = useState(false);
  const [importing, setImporting] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (!path.trim() || importing) return;
    setImporting(true);
    try {
      const result = await api("/api/managed-agents/import", {
        method: "POST",
        body: JSON.stringify({
          path,
          name: name || null,
          run_command: command || null,
          mcp_endpoint: endpoint || null,
          start_after_import: start,
        }),
      });
      notify(result.already_imported ? "That directory is already managed." : `Imported ${result.agent.name} and indexed ${result.profile.indexed_files} files.`);
      onImported(result.agent);
    } catch (error) {
      notify(error.message, true);
    } finally {
      setImporting(false);
    }
  }

  return <div className="agent-import-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="agent-import-modal" role="dialog" aria-modal="true" aria-labelledby="import-agent-title">
      <header><div><p className="eyebrow">CONNECT LOCAL AGENT</p><h2 id="import-agent-title">Import an agent directory</h2><p>The backend indexes supported source files, creates a managed workspace, detects launch commands, and makes the project available to the Manager for scoped context.</p></div><button onClick={onClose} aria-label="Close import dialog">×</button></header>
      <form onSubmit={submit}>
        <label className="import-path-field"><span>Agent directory <b>required</b></span><input autoFocus value={path} onChange={(event) => setPath(event.target.value)} placeholder="/Users/you/projects/my-agent" spellCheck="false" /><small>This path is resolved on the machine running the backend.</small></label>
        <div className="agent-import-grid">
          <label><span>Display name</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Detected from folder name" /></label>
          <label><span>MCP endpoint</span><input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="Optional · http://127.0.0.1:8100/mcp" spellCheck="false" /></label>
        </div>
        <label><span>Run command</span><input value={command} onChange={(event) => setCommand(event.target.value)} placeholder="Optional · make dev or python app.py" spellCheck="false" /><small>Leave blank to use the first command detected from package.json, Makefile, or Python entrypoints.</small></label>
        <label className="import-start-toggle"><input type="checkbox" checked={start} onChange={(event) => setStart(event.target.checked)} /><span><strong>Start after import</strong><small>Run the selected command directly without a shell. You can also start it later from the agent workspace.</small></span></label>
        <div className="agent-import-safety"><span>Read scope</span><p>Source files are available for Manager context. Secret files, environment files, dependency folders, build output, and Git internals remain excluded.</p></div>
        <footer><button type="button" className="quiet-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={importing || !path.trim()}>{importing ? "Indexing directory…" : "Add managed agent"} <span>→</span></button></footer>
      </form>
    </section>
  </div>;
}

export default function AgentsPage({ agents, conversations, onRefresh, notify }) {
  const navigate = useNavigate();
  const [discovering, setDiscovering] = useState(false);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [view, setView] = useState("grid");
  const [importOpen, setImportOpen] = useState(false);
  const filtered = useMemo(() => agents.filter((agent) => { const haystack = `${agent.name} ${agent.owner} ${agent.description} ${agent.features.join(" ")} ${agent.mcp_tools.map((tool) => tool.name).join(" ")}`.toLowerCase(); return (!query || haystack.includes(query.toLowerCase())) && (status === "all" || agent.status === status); }), [agents, query, status]);
  const clear = () => { setQuery(""); setStatus("all"); };
  async function discoverAll() { setDiscovering(true); try { const result = await api("/api/managed-agents/discover", { method: "POST", body: "{}" }); await onRefresh(); notify(`Updated ${result.tool_count} tools across ${result.agents.length} agents.`); } catch (error) { notify(error.message, true); } finally { setDiscovering(false); } }
  async function imported(agent) { setImportOpen(false); await onRefresh(); navigate(`/agents/${agent.id}`); }
  return <><PageHeader eyebrow="YOUR AGENT TEAM" title="Managed agents" description="Each agent has a focused workspace for its conversations, tools, connected source, runtime, and activity." actions={<div className="agent-page-actions"><button className="quiet-button" onClick={discoverAll} disabled={discovering}>{discovering ? "Syncing…" : "Sync capabilities"}</button><button className="primary-button" onClick={() => setImportOpen(true)}>＋ Add agent</button></div>} />
    <FilterBar resultCount={filtered.length} hasFilters={Boolean(query || status !== "all")} onClear={clear}><SearchField value={query} onChange={setQuery} placeholder="Search agents, tools, or capabilities" /><FilterChips value={status} onChange={setStatus} options={[{ id: "all", label: "All", count: agents.length }, { id: "healthy", label: "Healthy", count: agents.filter((agent) => agent.status === "healthy").length }, { id: "degraded", label: "Needs attention", count: agents.filter((agent) => agent.status === "degraded").length }]} /><ViewToggle value={view} onChange={setView} options={[["grid", "▦", "Grid view"], ["list", "☷", "List view"]]} /></FilterBar>
    {filtered.length ? <div className={`agent-grid animated-grid ${view === "list" ? "list" : ""}`}>{filtered.map((agent, index) => <div className="stagger-item" style={{ "--stagger": index }} key={agent.id}><AgentCard agent={agent} conversations={conversations.filter((item) => item.agent_id === agent.id).length} onOpen={() => navigate(`/agents/${agent.id}`)} view={view} /></div>)}</div> : <EmptyResults onClear={clear} />}
    {importOpen && <ImportAgentModal onClose={() => setImportOpen(false)} onImported={imported} notify={notify} />}
  </>;
}
