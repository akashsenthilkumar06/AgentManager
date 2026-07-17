import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import PageHeader from "../components/PageHeader";

const TABS = [["overview", "Overview"], ["conversations", "Conversations"], ["tools", "Tool workspaces"]];

export default function AgentWorkspacePage({ agents, notify }) {
  const { agentId } = useParams();
  const navigate = useNavigate();
  const agent = agents.find((item) => item.id === agentId);
  const [tab, setTab] = useState("overview");
  const [conversations, setConversations] = useState([]);
  const [selectedTool, setSelectedTool] = useState(null);
  useEffect(() => {
    if (!agentId) return;
    api(`/api/conversations?agent_id=${encodeURIComponent(agentId)}`).then(setConversations).catch((error) => notify(error.message, true));
  }, [agentId, notify]);
  const toolActivity = useMemo(() => {
    const activity = {};
    conversations.forEach((conversation) => conversation.messages.forEach((message) => message.tool_calls.forEach((call) => {
      activity[call.tool_name] = [...(activity[call.tool_name] || []), { ...call, conversation }];
    })));
    return activity;
  }, [conversations]);
  if (!agent) return <div className="not-found"><h1>Agent not found</h1><Link to="/agents">Return to managed agents</Link></div>;
  const activeTool = agent.mcp_tools.find((tool) => tool.name === selectedTool);
  return <><PageHeader eyebrow="MANAGED AGENT / WORKSPACE" title={agent.name} description={agent.description} actions={<button className="primary-button" onClick={() => navigate(`/?agent=${agent.id}`)}>Edit in workspace</button>} />
    <div className="agent-workspace-hero"><span className="agent-hero-avatar">{agent.name.charAt(0)}</span><div><span className={`connection-badge ${agent.status}`}><i />{agent.status}</span><strong>{agent.owner}</strong><small>{agent.mcp_server_name || "MCP server"} · synced {agent.last_discovered_at ? new Date(agent.last_discovered_at).toLocaleDateString() : "on startup"}</small></div><div className="agent-hero-stats"><span><b>{agent.mcp_tools.length}</b> tools</span><span><b>{conversations.length}</b> conversations</span><span><b>{agent.features.length}</b> capabilities</span></div></div>
    <nav className="workspace-tabs" aria-label="Agent workspace sections">{TABS.map(([id, label]) => <button key={id} className={tab === id ? "active" : ""} onClick={() => { setTab(id); setSelectedTool(null); }}>{label}</button>)}</nav>
    <div className="agent-workspace-content" key={`${tab}-${selectedTool || ""}`}>
      {tab === "overview" && <div className="agent-overview-grid"><section className="soft-panel"><p className="eyebrow">WHAT IT KNOWS</p><h2>Agent context</h2><p>{agent.description}</p><div className="capability-cloud">{agent.features.map((feature) => <span key={feature}>{feature}</span>)}</div></section><section className="soft-panel"><p className="eyebrow">CONFIGURE IT</p><h2>Edit this agent</h2><p>Change its instructions, identity, tool access, response behavior, memory, and verification policy.</p><button className="secondary-button inline" onClick={() => navigate(`/?agent=${agent.id}`)}>Open agent editor →</button></section></div>}
      {tab === "conversations" && <section className="soft-panel workspace-history"><div className="panel-heading"><div><h2>Conversation history</h2><p>Every test chat stays scoped to this agent.</p></div><button className="secondary-button" onClick={() => navigate(`/?agent=${agent.id}&mode=test`)}>New test</button></div>{conversations.length ? conversations.map((conversation) => <button className="agent-history-row" key={conversation.id} onClick={() => navigate(`/?agent=${agent.id}&mode=test&conversation=${conversation.id}`)}><span>◌</span><div><strong>{conversation.title}</strong><small>{conversation.messages.length} messages · {new Date(conversation.updated_at).toLocaleString()}</small></div><b>→</b></button>) : <div className="workspace-empty">No conversations yet. Open Test agent to start one.</div>}</section>}
      {tab === "tools" && <div className="tool-workspace-layout"><aside className="tool-workspace-list"><span>Agent tools</span>{agent.mcp_tools.map((tool) => <button key={tool.name} className={selectedTool === tool.name ? "active" : ""} onClick={() => setSelectedTool(tool.name)}><i>⌁</i><span><strong>{tool.name}</strong><small>{(toolActivity[tool.name] || []).length} runs</small></span><b>›</b></button>)}</aside><section className="tool-workspace-detail">{activeTool ? <><div className="tool-detail-heading"><span className="soft-orb">⌁</span><div><p className="eyebrow">TOOL WORKSPACE</p><h2>{activeTool.name}</h2><p>{activeTool.description}</p></div><button className="primary-button" onClick={() => navigate(`/?agent=${agent.id}&mode=test&tool=${activeTool.name}&context=full`)}>Test this tool</button></div><div className="tool-detail-grid"><section><span>Input contract</span><pre><code>{JSON.stringify(activeTool.input_schema, null, 2)}</code></pre></section><section><span>Run history</span>{(toolActivity[activeTool.name] || []).length ? toolActivity[activeTool.name].map((activity) => <div className="tool-run" key={activity.id}><i className={activity.status} /> <div><strong>{activity.status} · {activity.duration_ms} ms</strong><small>{activity.conversation.title}</small></div><time>{new Date(activity.conversation.updated_at).toLocaleDateString()}</time></div>) : <div className="tool-empty">This tool has not been used in a conversation yet.</div>}</section></div></> : <div className="select-tool-empty"><span>⌁</span><h2>Select a tool workspace</h2><p>Inspect its contract, test it in context, and review every previous run.</p></div>}</section></div>}
    </div>
  </>;
}
