import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import PageHeader from "../components/PageHeader";

const TABS = [
  ["overview", "Overview"],
  ["conversations", "Conversations"],
  ["tools", "Tool workspaces"],
];

function updatePayload(agent, endpoint, overrides = {}) {
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
    openai_model: agent.openai_model || null,
    openai_reasoning_effort: agent.openai_reasoning_effort || null,
    ...overrides,
  };
}

function ModelSettingsEditor({
  agent,
  openai,
  onRefresh,
  notify,
}) {
  const [model, setModel] = useState(agent.openai_model || "");
  const [reasoning, setReasoning] = useState(
    agent.openai_reasoning_effort || "",
  );
  const [saving, setSaving] = useState(false);
  const options = openai?.model_options || [];
  const effectiveModel = model || openai?.model || "application default";
  const selected = options.find(
    (option) => option.id === effectiveModel,
  );
  const reasoningOptions = selected?.reasoning_efforts || [];
  const effectiveReasoning = reasoning
    || openai?.reasoning_effort
    || "provider default";

  function chooseModel(value) {
    setModel(value);
    const option = options.find(
      (item) => item.id === (value || openai?.model),
    );
    if (
      reasoning
      && option
      && !option.reasoning_efforts.includes(reasoning)
    ) {
      setReasoning("");
    }
  }

  async function save() {
    if (saving) return;
    setSaving(true);
    try {
      await api(`/api/managed-agents/${agent.id}`, {
        method: "PATCH",
        body: JSON.stringify(
          updatePayload(agent, agent.mcp_endpoint || "", {
            openai_model: model || null,
            openai_reasoning_effort: reasoning || null,
          }),
        ),
      });
      await onRefresh();
      notify(`Model settings saved for ${agent.name}.`);
    } catch (error) {
      notify(error.message, true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="model-settings-editor">
      <div className="model-settings-heading">
        <div>
          <p className="eyebrow">LIVE REASONING</p>
          <h2>OpenAI model</h2>
          <p>Choose the model and reasoning effort used when Manager or Test mode performs OpenAI-backed work for this agent.</p>
        </div>
        <span><small>Effective model</small><strong>{effectiveModel}</strong></span>
      </div>
      <div className="model-settings-controls">
        <label>
          <span>Model</span>
          <select value={model} onChange={(event) => chooseModel(event.target.value)}>
            <option value="">Inherit app default ({openai?.model || "configured model"})</option>
            {options.map((option) => (
              <option value={option.id} key={option.id}>
                {option.label} · {option.role}
              </option>
            ))}
          </select>
          <small>{selected?.description || "Uses the model configured by OPENAI_MODEL."}</small>
        </label>
        <label>
          <span>Reasoning effort</span>
          <select
            value={reasoning}
            onChange={(event) => setReasoning(event.target.value)}
          >
            <option value="">Inherit app default ({openai?.reasoning_effort || "provider default"})</option>
            {reasoningOptions.map((effort) => (
              <option value={effort} key={effort}>
                {effort === "none" ? "None" : effort.charAt(0).toUpperCase() + effort.slice(1)}
              </option>
            ))}
          </select>
          <small>Higher effort can improve difficult work, but usually adds latency and token usage.</small>
        </label>
        <button className="primary-button" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save model"}
        </button>
      </div>
      <div className="model-effective-note">
        <i />
        OpenAI-backed runs use <strong>{effectiveModel}</strong> with <strong>{effectiveReasoning}</strong> reasoning; live Test responses record both in their evidence.
      </div>
    </section>
  );
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

function ImportedRuntimePanel({ agent, onRefresh, notify }) {
  const [runtime, setRuntime] = useState(null);
  const [command, setCommand] = useState(agent.run_command || "");
  const [working, setWorking] = useState(false);

  useEffect(() => {
    if (!agent.imported) return undefined;
    let active = true;
    api(`/api/managed-agents/${agent.id}/process`)
      .then((result) => {
        if (!active) return;
        setRuntime(result);
      })
      .catch((error) => notify(error.message, true));
    return () => { active = false; };
  }, [agent.id, agent.imported, notify]);

  useEffect(() => {
    if (!agent.imported || runtime?.status !== "running") {
      return undefined;
    }
    const timer = window.setInterval(() => {
      api(`/api/managed-agents/${agent.id}/process`)
        .then(setRuntime)
        .catch(() => {});
    }, 1800);
    return () => window.clearInterval(timer);
  }, [agent.id, agent.imported, runtime?.status]);

  if (!agent.imported) return null;

  async function start() {
    if (!command.trim() || working) return;
    setWorking(true);
    try {
      const result = await api(`/api/managed-agents/${agent.id}/process/start`, {
        method: "POST",
        body: JSON.stringify({ command }),
      });
      setRuntime(result);
      await onRefresh();
      notify(`${agent.name} started.`);
    } catch (error) {
      notify(error.message, true);
    } finally {
      setWorking(false);
    }
  }

  async function stop() {
    if (working) return;
    setWorking(true);
    try {
      setRuntime(await api(`/api/managed-agents/${agent.id}/process/stop`, { method: "POST", body: "{}" }));
      notify(`${agent.name} stopped.`);
    } catch (error) {
      notify(error.message, true);
    } finally {
      setWorking(false);
    }
  }

  return <section className="imported-runtime-panel">
    <div className="runtime-panel-heading"><div><p className="eyebrow">CONNECTED LOCAL RUNTIME</p><h2>Source and process</h2><p>The Manager can search and read this directory as scoped context. Starting the runtime executes only the command shown below, directly in the imported directory.</p></div><span className={`runtime-state ${runtime?.status || "stopped"}`}><i />{runtime?.status || "stopped"}</span></div>
    <div className="runtime-directory"><span>▱</span><div><strong>{agent.workspace_root}</strong><small>Connected source · secret and dependency paths excluded</small></div></div>
    {agent.detected_entrypoints?.length > 0 && <div className="runtime-entrypoints"><span>Detected commands</span><div>{agent.detected_entrypoints.map((entrypoint) => <button key={entrypoint} onClick={() => setCommand(entrypoint)} className={command === entrypoint ? "active" : ""}>{entrypoint}</button>)}</div></div>}
    <div className="runtime-command-row"><label><span>Run command</span><input value={command} onChange={(event) => setCommand(event.target.value)} placeholder="make dev" spellCheck="false" /></label>{runtime?.status === "running" ? <button className="runtime-stop-button" onClick={stop} disabled={working}>{working ? "Stopping…" : "Stop agent"}</button> : <button className="primary-button" onClick={start} disabled={working || !command.trim()}>{working ? "Starting…" : "Start agent"} <span>▶</span></button>}</div>
    <div className="runtime-log"><div><span>Runtime output</span><small>{runtime?.pid ? `PID ${runtime.pid}` : runtime?.exit_code !== null && runtime?.exit_code !== undefined ? `Exited ${runtime.exit_code}` : "Not running"}</small></div>{runtime?.logs?.length ? <pre><code>{runtime.logs.join("\n")}</code></pre> : <p>Process output will appear here after the agent starts.</p>}</div>
  </section>;
}

export default function AgentWorkspacePage({
  agents,
  openai,
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
        actions={<div className="agent-page-actions"><button className="quiet-button" onClick={() => navigate(`/benchmarks?agent=${agent.id}`)}>Benchmark</button><button className="primary-button" onClick={() => navigate(`/workspace?agent=${agent.id}`)}>Edit in workspace</button></div>}
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
            <ModelSettingsEditor
              key={`model-${agent.id}`}
              agent={agent}
              openai={openai}
              onRefresh={onRefresh}
              notify={notify}
            />
            <ImportedRuntimePanel
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
