import { useMemo, useState } from "react";
import EmptyResults from "../components/EmptyResults";
import FilterBar, { FilterChips, SearchField } from "../components/FilterBar";
import PageHeader from "../components/PageHeader";

const SECTIONS = [["agents", "Agents"], ["tools", "Tools"], ["endpoints", "Endpoints"], ["data_sources", "Data sources"]];

function EntityRow({ item, symbol, meta, expanded, onToggle }) { return <div className={`entity-row expandable ${expanded ? "open" : ""}`}><span className="entity-symbol">{symbol}</span><button className="entity-main" onClick={onToggle}><span className="entity-copy"><strong>{item.name}{item.generated && <span className="generated-tag">GENERATED</span>}</strong><small>{item.description}</small></span><span className="entity-meta"><i className="healthy-dot" />{meta} {expanded ? "⌃" : "⌄"}</span></button>{expanded && <div className="entity-details"><div><span>Owner</span><strong>{item.owner}</strong></div>{item.path && <div><span>Path</span><code>{item.path}</code></div>}{item.endpoint_ids && <div><span>Dependencies</span><strong>{item.endpoint_ids.length} endpoints</strong></div>}{item.mcp_endpoint && <div><span>MCP endpoint</span><code>{item.mcp_endpoint}</code></div>}</div>}</div>; }

export default function ArchitecturePage({ architecture, summary }) {
  const [section, setSection] = useState("agents");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [expanded, setExpanded] = useState(null);
  const records = useMemo(() => architecture[section] || [], [architecture, section]);
  const filtered = useMemo(() => records.filter((item) => { const text = `${item.name} ${item.description} ${item.owner} ${(item.tags || []).join(" ")}`.toLowerCase(); return (!query || text.includes(query.toLowerCase())) && (status === "all" || item.status === status); }), [records, query, status]);
  const clear = () => { setQuery(""); setStatus("all"); };
  const symbol = section === "agents" ? "A" : section === "tools" ? "⌁" : section === "endpoints" ? "API" : "DB";
  const meta = (item) => section === "agents" ? `${item.mcp_tools.length} MCP tools` : section === "tools" ? item.version : section === "endpoints" ? item.method : item.kind;
  return <><PageHeader eyebrow="LIVE SYSTEM MAP" title="Architecture" description="Choose one layer of the ecosystem, then filter and inspect only what matters." /><div className="architecture-summary">{SECTIONS.map(([id, label]) => <button key={id} className={section === id ? "active" : ""} onClick={() => { setSection(id); setExpanded(null); }}><span>{label}</span><strong>{summary.counts[id === "data_sources" ? "data_sources" : id]}</strong></button>)}</div><FilterBar resultCount={filtered.length} hasFilters={Boolean(query || status !== "all")} onClear={clear}><SearchField value={query} onChange={setQuery} placeholder={`Search ${SECTIONS.find(([id]) => id === section)[1].toLowerCase()}`} /><FilterChips value={status} onChange={setStatus} options={["all", "healthy", "degraded", "offline"]} /></FilterBar><div className="panel architecture-list"><div className="panel-heading"><h3>{SECTIONS.find(([id]) => id === section)[1]}</h3><span className="count-badge">{filtered.length}</span></div>{filtered.length ? filtered.map((item) => <EntityRow key={item.id} item={item} symbol={section === "endpoints" ? item.method : symbol} meta={meta(item)} expanded={expanded === item.id} onToggle={() => setExpanded(expanded === item.id ? null : item.id)} />) : <EmptyResults onClear={clear} />}</div></>;
}
