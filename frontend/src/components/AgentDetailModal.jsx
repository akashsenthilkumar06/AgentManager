import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";

const TABS = [["overview", "Overview"], ["tools", "Tools"], ["mcp", "MCP details"]];

function Overview({ agent }) {
  return <div className="agent-modal-overview"><div className="modal-stat-grid"><div><span>Health</span><strong className="status-value"><i />{agent.status}</strong></div><div><span>Available tools</span><strong>{agent.mcp_tools.length}</strong></div><div><span>Features</span><strong>{agent.features.length}</strong></div><div><span>Resources</span><strong>{agent.mcp_resources.length}</strong></div></div><section className="modal-section"><h3>What this agent does</h3><p>{agent.description}</p></section><section className="modal-section"><h3>Supported capabilities</h3><div className="feature-list spacious">{agent.features.length ? agent.features.map((feature) => <span key={feature}>{feature}</span>) : <small>No features have been declared.</small>}</div></section><section className="modal-section compact-info"><div><span>Owned by</span><strong>{agent.owner}</strong></div><div><span>Agent ID</span><code>{agent.id}</code></div></section></div>;
}

function Tools({ agent }) {
  return <div className="modal-tool-list">{agent.mcp_tools.length ? agent.mcp_tools.map((tool, index) => <article className="modal-tool-card" key={tool.name}><span className="tool-number">{String(index + 1).padStart(2, "0")}</span><div><h3>{tool.name}</h3><p>{tool.description || "No tool description provided."}</p><details><summary>Input contract</summary><pre><code>{JSON.stringify(tool.input_schema, null, 2)}</code></pre></details></div></article>) : <div className="modal-empty"><span>⌁</span><h3>No tools discovered</h3><p>Refresh capabilities to ask this agent's MCP server for its current tool list.</p></div>}</div>;
}

function MCPDetails({ agent }) {
  return <div className="mcp-detail-layout"><section className="modal-section"><h3>Connection</h3><div className="connection-detail"><span>MCP endpoint</span><code>{agent.mcp_endpoint || "Not configured"}</code></div><div className="connection-detail"><span>Server name</span><code>{agent.mcp_server_name || "Not discovered"}</code></div><div className="connection-detail"><span>Last discovered</span><strong>{agent.last_discovered_at ? new Date(agent.last_discovered_at).toLocaleString() : "Never"}</strong></div></section><div className="mcp-collection-grid"><section className="modal-section"><div className="modal-section-title"><h3>Prompts</h3><span>{agent.mcp_prompts.length}</span></div>{agent.mcp_prompts.length ? agent.mcp_prompts.map((prompt) => <div className="mcp-item" key={prompt}>✦ <code>{prompt}</code></div>) : <p className="inline-empty">No prompts advertised.</p>}</section><section className="modal-section"><div className="modal-section-title"><h3>Resources</h3><span>{agent.mcp_resources.length}</span></div>{agent.mcp_resources.length ? agent.mcp_resources.map((resource) => <div className="mcp-item" key={resource}>▱ <code>{resource}</code></div>) : <p className="inline-empty">No resources advertised.</p>}</section></div></div>;
}

export default function AgentDetailModal({ agent, onClose }) {
  const [tab, setTab] = useState("overview");
  const [closing, setClosing] = useState(false);
  const requestClose = useCallback(() => { setClosing(true); window.setTimeout(onClose, 190); }, [onClose]);
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event) => { if (event.key === "Escape") requestClose(); };
    document.addEventListener("keydown", onKey);
    return () => { document.body.style.overflow = previous; document.removeEventListener("keydown", onKey); };
  }, [requestClose]);
  return createPortal(<div className={`modal-backdrop ${closing ? "closing" : ""}`} onMouseDown={(event) => { if (event.target === event.currentTarget) requestClose(); }}><section className="agent-modal" role="dialog" aria-modal="true" aria-labelledby="agent-modal-title"><header className="agent-modal-header"><span className="agent-modal-avatar">A</span><div><p className="eyebrow">MANAGED AGENT</p><h2 id="agent-modal-title">{agent.name}</h2><span>{agent.owner}</span></div><span className={`connection-badge ${agent.status}`}><i />{agent.status}</span><button className="modal-close" onClick={requestClose} aria-label="Close agent details">×</button></header><nav className="agent-modal-tabs" aria-label="Agent detail sections">{TABS.map(([id, label]) => <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>{label}{id === "tools" && <span>{agent.mcp_tools.length}</span>}</button>)}</nav><div className="agent-modal-body" key={tab}>{tab === "overview" && <Overview agent={agent} />}{tab === "tools" && <Tools agent={agent} />}{tab === "mcp" && <MCPDetails agent={agent} />}</div><footer className="agent-modal-footer"><span>Capabilities are read directly from this agent's MCP server.</span><button onClick={requestClose}>Done</button></footer></section></div>, document.body);
}
