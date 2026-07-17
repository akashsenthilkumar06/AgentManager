import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import PageHeader from "../components/PageHeader";

const TABS = [
  ["overview", "Overview"],
  ["conversations", "Conversations"],
  ["tools", "Tool workspaces"],
];

function updatePayload(agent, endpoint) {
  return {
    name: agent.name,
    description: agent.description,
    owner: agent.owner,
    mcp_endpoint: endpoint.trim() || null,
    instructions: agent.instructions,
    features: agent.features,
    response_style: agent.response_style,
    tool_policy: agent.tool_policy,
    enabled_tools: agent.enabled_tools,
    verification_mode: agent.verification_mode,
    memory_enabled: agent.memory_enabled,
  };
}

function MCPConnectionEditor({
  agent,
  onRefresh,
  notify,
}) {
  const [endpoint, setEndpoint] = useState(agent.mcp_endpoint || "");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState(null);
  const displayAgent = result?.agent || agent;

  async function save(showNotice = true) {
    const updated = await api(`/api/managed-agents/${agent.id}`, {
      method: "PATCH",
      body: JSON.stringify(updatePayload(agent, endpoint)),
    });
    setEndpoint(updated.mcp_endpoint || "");
    await onRefresh();
    if (showNotice) notify("MCP endpoint saved.");
    return updated;
  }

  async function saveEndpoint() {
    if (saving || testing) return;
    setSaving(true);
    setResult(null);
    try {
      await save();
    } catch (error) {
      setResult({ status: "failed", message: error.message });
      notify(error.message, true);
    } finally {
      setSaving(false);
    }
  }

  async function testConnection() {
    if (testing || saving) return;
    setTesting(true);
    setResult(null);
    try {
      await save(false);
      const discovered = await api(
        `/api/managed-agents/${agent.id}/discover`,
        { method: "POST", body: "{}" },
      );
      setEndpoint(discovered.mcp_endpoint || "");
      setResult({
        status: "passed",
        agent: discovered,
        message: `Connected to ${discovered.mcp_server_name}.`,
      });
      await onRefresh();
      notify(`Discovered ${discovered.mcp_tools.length} live MCP tools.`);
    } catch (error) {
      setResult({ status: "failed", message: error.message });
      notify(error.message, true);
    } finally {
      setTesting(false);
    }
  }

  return (
    <section className="mcp-connection-editor">
      <div className="mcp-editor-heading">
        <div>
          <p className="eyebrow">LIVE AGENT CONNECTION</p>
          <h2>MCP endpoint</h2>
          <p>Point this managed agent at a `demo://`, `http://`, or `https://` MCP server.</p>
        </div>
        <span className={`connection-badge ${displayAgent.status}`}><i />{displayAgent.status}</span>
      </div>

      <div className="mcp-endpoint-control">
        <label>
          <span>Endpoint URL</span>
          <input
            value={endpoint}
            onChange={(event) => setEndpoint(event.target.value)}
            placeholder="http://127.0.0.1:8100/mcp"
            spellCheck="false"
          />
        </label>
        <div>
          <button className="quiet-button" onClick={saveEndpoint} disabled={saving || testing}>
            {saving ? "Saving…" : "Save endpoint"}
          </button>
          <button className="primary-button" onClick={testConnection} disabled={saving || testing || !endpoint.trim()}>
            {testing ? "Connecting…" : "Test & discover"} <span>↗</span>
          </button>
        </div>
      </div>
      <p className="mcp-live-note"><i />HTTP(S) endpoints use Live MCP conversation mode when `OPENAI_API_KEY` is configured. Every fallback is labeled in the conversation.</p>

      <div className={`mcp-discovery-result ${result?.status || ""}`}>
        <div className="mcp-discovery-summary">
          <span>{result?.status === "failed" ? "!" : "⌁"}</span>
          <div>
            <strong>{result?.message || displayAgent.mcp_server_name || "Not discovered yet"}</strong>
            <small>{displayAgent.last_discovered_at ? `Last checked ${new Date(displayAgent.last_discovered_at).toLocaleString()}` : "Test the endpoint to load its advertised tools."}</small>
          </div>
          <b>{displayAgent.mcp_tools.length} tool{displayAgent.mcp_tools.length === 1 ? "" : "s"}</b>
        </div>
        {result?.status !== "failed" && displayAgent.mcp_tools.length > 0 && (
          <div className="mcp-discovered-tools">
            {displayAgent.mcp_tools.map((tool) => (
              <article key={tool.name}>
                <span>⌁</span>
                <div><strong>{tool.name}</strong><small>{tool.description || "No description advertised."}</small></div>
                <code>{Object.keys(tool.input_schema?.properties || {}).length} inputs</code>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

export default function AgentWorkspacePage({
  agents,
  onRefresh,
  notify,
}) {
  const { agentId } = useParams();
  const navigate = useNavigate();
  const agent = agents.find((item) => item.id === agentId);
  const [tab, setTab] = useState("overview");
  const [conversations, setConversations] = useState([]);
  const [selectedTool, setSelectedTool] = useState(null);

  useEffect(() => {
    if (!agentId) return;
    api(`/api/conversations?agent_id=${encodeURIComponent(agentId)}`)
      .then(setConversations)
      .catch((error) => notify(error.message, true));
  }, [agentId, notify]);

  const toolActivity = useMemo(() => {
    const activity = {};
    conversations.forEach((conversation) => {
      conversation.messages.forEach((message) => {
        message.tool_calls.forEach((call) => {
          activity[call.tool_name] = [
            ...(activity[call.tool_name] || []),
            { ...call, conversation },
          ];
        });
      });
    });
    return activity;
  }, [conversations]);

  if (!agent) {
    return (
      <div className="not-found">
        <h1>Agent not found</h1>
        <Link to="/agents">Return to managed agents</Link>
      </div>
    );
  }

  const activeTool = agent.mcp_tools.find(
    (tool) => tool.name === selectedTool,
  );

  return (
    <>
      <PageHeader
        eyebrow="MANAGED AGENT / WORKSPACE"
        title={agent.name}
        description={agent.description}
        actions={<button className="primary-button" onClick={() => navigate(`/workspace?agent=${agent.id}`)}>Edit in workspace</button>}
      />
      <div className="agent-workspace-hero">
        <span className="agent-hero-avatar">{agent.name.charAt(0)}</span>
        <div>
          <span className={`connection-badge ${agent.status}`}><i />{agent.status}</span>
          <strong>{agent.owner}</strong>
          <small>{agent.mcp_server_name || "MCP server"} · synced {agent.last_discovered_at ? new Date(agent.last_discovered_at).toLocaleDateString() : "on startup"}</small>
        </div>
        <div className="agent-hero-stats">
          <span><b>{agent.mcp_tools.length}</b> tools</span>
          <span><b>{conversations.length}</b> conversations</span>
          <span><b>{agent.features.length}</b> capabilities</span>
        </div>
      </div>
      <nav className="workspace-tabs" aria-label="Agent workspace sections">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            className={tab === id ? "active" : ""}
            onClick={() => {
              setTab(id);
              setSelectedTool(null);
            }}
          >
            {label}
          </button>
        ))}
      </nav>
      <div className="agent-workspace-content" key={`${tab}-${selectedTool || ""}`}>
        {tab === "overview" && (
          <>
            <div className="agent-overview-grid">
              <section className="soft-panel">
                <p className="eyebrow">WHAT IT KNOWS</p>
                <h2>Agent context</h2>
                <p>{agent.description}</p>
                <div className="capability-cloud">{agent.features.map((feature) => <span key={feature}>{feature}</span>)}</div>
              </section>
              <section className="soft-panel">
                <p className="eyebrow">CONFIGURE IT</p>
                <h2>Edit this agent</h2>
                <p>Use the Manager to change instructions and behavior with a reviewable, validated diff.</p>
                <button className="secondary-button inline" onClick={() => navigate(`/workspace?agent=${agent.id}`)}>Open agent editor →</button>
              </section>
            </div>
            <MCPConnectionEditor
              key={agent.id}
              agent={agent}
              onRefresh={onRefresh}
              notify={notify}
            />
          </>
        )}

        {tab === "conversations" && (
          <section className="soft-panel workspace-history">
            <div className="panel-heading">
              <div><h2>Conversation history</h2><p>Every test chat stays scoped to this agent.</p></div>
              <button className="secondary-button" onClick={() => navigate(`/workspace?agent=${agent.id}&mode=test`)}>New test</button>
            </div>
            {conversations.length
              ? conversations.map((conversation) => (
                <button className="agent-history-row" key={conversation.id} onClick={() => navigate(`/workspace?agent=${agent.id}&mode=test&conversation=${conversation.id}`)}>
                  <span>◌</span>
                  <div><strong>{conversation.title}</strong><small>{conversation.messages.length} messages · {new Date(conversation.updated_at).toLocaleString()}</small></div>
                  <b>→</b>
                </button>
              ))
              : <div className="workspace-empty">No conversations yet. Open Test agent to start one.</div>}
          </section>
        )}

        {tab === "tools" && (
          <div className="tool-workspace-layout">
            <aside className="tool-workspace-list">
              <span>Agent tools</span>
              {agent.mcp_tools.map((tool) => (
                <button key={tool.name} className={selectedTool === tool.name ? "active" : ""} onClick={() => setSelectedTool(tool.name)}>
                  <i>⌁</i>
                  <span><strong>{tool.name}</strong><small>{(toolActivity[tool.name] || []).length} runs</small></span>
                  <b>›</b>
                </button>
              ))}
            </aside>
            <section className="tool-workspace-detail">
              {activeTool ? (
                <>
                  <div className="tool-detail-heading">
                    <span className="soft-orb">⌁</span>
                    <div><p className="eyebrow">TOOL WORKSPACE</p><h2>{activeTool.name}</h2><p>{activeTool.description}</p></div>
                    <button className="primary-button" onClick={() => navigate(`/workspace?agent=${agent.id}&mode=test&tool=${activeTool.name}&context=full`)}>Test this tool</button>
                  </div>
                  <div className="tool-detail-grid">
                    <section><span>Input contract</span><pre><code>{JSON.stringify(activeTool.input_schema, null, 2)}</code></pre></section>
                    <section>
                      <span>Run history</span>
                      {(toolActivity[activeTool.name] || []).length
                        ? toolActivity[activeTool.name].map((activity) => (
                          <div className="tool-run" key={activity.id}>
                            <i className={activity.status} />
                            <div><strong>{activity.status} · {activity.duration_ms} ms</strong><small>{activity.conversation.title}</small></div>
                            <time>{new Date(activity.conversation.updated_at).toLocaleDateString()}</time>
                          </div>
                        ))
                        : <div className="tool-empty">This tool has not been used in a conversation yet.</div>}
                    </section>
                  </div>
                </>
              ) : (
                <div className="select-tool-empty">
                  <span>⌁</span>
                  <h2>Select a tool workspace</h2>
                  <p>Inspect its contract, test it in context, and review every previous run.</p>
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </>
  );
}
