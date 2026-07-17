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
    <div className="agent-card-action"><span>Enter agent workspace</span><b>→</b></div>
  </article>;
}

export default function AgentsPage({ agents, conversations, onRefresh, notify }) {
  const navigate = useNavigate();
  const [discovering, setDiscovering] = useState(false);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [view, setView] = useState("grid");
  const filtered = useMemo(() => agents.filter((agent) => { const haystack = `${agent.name} ${agent.owner} ${agent.description} ${agent.features.join(" ")} ${agent.mcp_tools.map((tool) => tool.name).join(" ")}`.toLowerCase(); return (!query || haystack.includes(query.toLowerCase())) && (status === "all" || agent.status === status); }), [agents, query, status]);
  const clear = () => { setQuery(""); setStatus("all"); };
  async function discoverAll() { setDiscovering(true); try { const result = await api("/api/managed-agents/discover", { method: "POST", body: "{}" }); await onRefresh(); notify(`Updated ${result.tool_count} tools across ${result.agents.length} agents.`); } catch (error) { notify(error.message, true); } finally { setDiscovering(false); } }
  return <><PageHeader eyebrow="YOUR AGENT TEAM" title="Managed agents" description="Each agent has a focused workspace for its conversations, tools, context, and activity." actions={<button className="primary-button" onClick={discoverAll} disabled={discovering}>{discovering ? "Syncing…" : "Sync capabilities"}</button>} />
    <FilterBar resultCount={filtered.length} hasFilters={Boolean(query || status !== "all")} onClear={clear}><SearchField value={query} onChange={setQuery} placeholder="Search agents, tools, or capabilities" /><FilterChips value={status} onChange={setStatus} options={[{ id: "all", label: "All", count: agents.length }, { id: "healthy", label: "Healthy", count: agents.filter((agent) => agent.status === "healthy").length }, { id: "degraded", label: "Needs attention", count: agents.filter((agent) => agent.status === "degraded").length }]} /><ViewToggle value={view} onChange={setView} options={[["grid", "▦", "Grid view"], ["list", "☷", "List view"]]} /></FilterBar>
    {filtered.length ? <div className={`agent-grid animated-grid ${view === "list" ? "list" : ""}`}>{filtered.map((agent, index) => <div className="stagger-item" style={{ "--stagger": index }} key={agent.id}><AgentCard agent={agent} conversations={conversations.filter((item) => item.agent_id === agent.id).length} onOpen={() => navigate(`/agents/${agent.id}`)} view={view} /></div>)}</div> : <EmptyResults onClear={clear} />}
  </>;
}
