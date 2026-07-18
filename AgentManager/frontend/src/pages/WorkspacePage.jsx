import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";

const TEST_STARTERS = {
  "finance-agent": ["What is the status of INV-2048?", "Summarize the billing risk for INV-1120."],
  "coding-agent": ["How healthy is REPO-1 right now?", "Summarize release risk for REPO-1."],
  "support-agent": ["What is the status of TCK-9001?", "Summarize the next action for TCK-9012."],
};

const EDIT_STARTERS = [
  "Review this agent's architecture and suggest the most important improvement.",
  "Make this agent verify its answer against tool evidence before responding.",
  "Check whether this agent is running and discover the tools it exposes.",
  "Should we redesign how this agent uses its current tool?",
];

function Verification({ verification, contextUsed, toolCalls }) {
  const [open, setOpen] = useState(false);
  if (!verification) return null;
  return <div className={`verification-card ${open ? "open" : ""}`}>
    <button className="verification-summary" onClick={() => setOpen((value) => !value)}>
      <span className="verified-icon">✓</span>
      <span><strong>Output {verification.status}</strong><small>{Math.round(verification.confidence * 100)}% confidence · {toolCalls.length} tool{toolCalls.length === 1 ? "" : "s"} used</small></span>
      <b>{open ? "Hide evidence" : "See evidence"}</b>
    </button>
    {open && <div className="verification-details"><p>{verification.summary}</p><div className="proof-columns"><div><span>Acceptance criteria</span>{verification.criteria.map((item) => <small key={item}>✓ {item}</small>)}</div><div><span>Grounding evidence</span>{verification.evidence.map((item) => <small key={item}>↳ {item}</small>)}</div></div><div className="context-receipt"><span>Context used</span>{contextUsed.map((item) => <em key={item}>{item}</em>)}</div>{toolCalls.length > 0 && <div className="conversation-tool-trace"><span>Tool execution trace</span>{toolCalls.map((call) => <details key={call.id}><summary><i className={call.status} />{call.tool_name}<small>{call.provider || "deterministic"}</small><b>{call.duration_ms} ms</b></summary><div>{call.endpoint && <><label>Execution endpoint</label><code>{call.endpoint}</code></>}<label>Input</label><pre><code>{JSON.stringify(call.input, null, 2)}</code></pre><label>Output</label><pre><code>{JSON.stringify(call.output, null, 2)}</code></pre></div></details>)}</div>}</div>}
  </div>;
}

function ExecutionReceipt({ message }) {
  const mode = message.execution_mode || "deterministic";
  if (mode === "live") {
    return <div className="execution-receipt live"><span><i />Live MCP</span><code>{message.provider}</code><small>{message.endpoint}</small></div>;
  }
  if (mode === "fallback") {
    return <div className="execution-receipt fallback"><span><i />Fallback demo</span><div><strong>The live agent was not used for this answer.</strong><small>{message.fallback_reason || "Live MCP was unavailable."}</small></div></div>;
  }
  return <div className="execution-receipt deterministic"><span><i />Local demo</span><small>Deterministic fixture response</small></div>;
}

function Conversation({ conversation }) {
  const bottomRef = useRef(null);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [conversation?.messages.length]);
  if (!conversation?.messages.length) return null;
  return <div className="message-list">{conversation.messages.map((message) => <article className={`message ${message.role}`} key={message.id}><span className="message-avatar">{message.role === "user" ? "You" : "A"}</span><div className="message-body"><span className="message-author">{message.role === "user" ? "You" : "Client agent"}</span><p>{message.content}</p>{message.role === "agent" && <><ExecutionReceipt message={message} /><div className="orchestration-receipt"><span>✓ Context scoped</span><span>✓ {message.tool_calls.length} tool{message.tool_calls.length === 1 ? "" : "s"} recorded</span><span>✓ Output checked</span></div><Verification verification={message.verification} contextUsed={message.context_used} toolCalls={message.tool_calls} /></>}</div></article>)}<div ref={bottomRef} /></div>;
}

function ManagerMessage({ message, onApply, applying }) {
  if (message.role === "user") return <article className="manager-message user"><span className="manager-message-avatar">You</span><div><span>You</span><p>{message.content}</p></div></article>;
  const pending = message.changes.some((change) => change.status === "pending");
  return <article className="manager-message manager"><span className="manager-message-avatar">M</span><div><span>Manager Agent <em>{message.provider}</em></span><p>{message.content}</p>
    {message.actions.length > 0 && <div className="manager-tool-strip">{message.actions.map((action) => <span key={action.id} className={action.status}><i />{action.tool}</span>)}</div>}
    {message.actions.some((action) => Object.keys(action.evidence || {}).length > 0) && <div className="manager-runtime-evidence"><span>Execution evidence</span>{message.actions.filter((action) => Object.keys(action.evidence || {}).length > 0).map((action) => <details key={action.id}><summary><i className={action.status} />{action.tool}<b>{action.evidence.protocol || action.evidence.access || "Recorded output"}</b></summary><pre><code>{JSON.stringify(action.evidence, null, 2)}</code></pre></details>)}</div>}
    {message.changes.map((change) => <div className="manager-change-card" key={change.id}><div><span>{change.status === "pending" ? "PROPOSED CHANGE" : "APPLIED CHANGE"}</span><strong>{change.target}</strong><small>{change.summary}</small></div><b className={change.status}>{change.status}</b><details><summary>Review instructions diff</summary><div className="manager-diff"><p><span>− Before</span>{change.before}</p><p><span>+ After</span>{change.after}</p></div></details></div>)}
    {message.evaluation && <div className={`manager-evaluation ${message.evaluation.status}`}><span>✓</span><div><strong>Validation {message.evaluation.status}</strong><small>{message.evaluation.summary}</small></div></div>}
    {pending && <button className="apply-manager-change" onClick={onApply} disabled={applying}>{applying ? "Applying…" : "Apply reviewed change"}</button>}
  </div></article>;
}

function ManagerWorkspace({ agent, openai, onRefresh, notify }) {
  const [conversations, setConversations] = useState([]);
  const [conversation, setConversation] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [autonomy, setAutonomy] = useState("review");
  const [liveOpen, setLiveOpen] = useState(false);
  const [working, setWorking] = useState(false);
  const [applying, setApplying] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    let active = true;
    api(`/api/manager/conversations?agent_id=${encodeURIComponent(agent.id)}`).then((items) => { if (active) setConversations(items); }).catch((error) => notify(error.message, true));
    return () => { active = false; };
  }, [agent.id, notify]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [conversation?.messages.length, working]);

  const latestManagerMessage = [...(conversation?.messages || [])].reverse().find((message) => message.role === "manager");
  async function send(event, suggestion) {
    event?.preventDefault();
    const outgoing = (suggestion || prompt).trim();
    if (!outgoing || working) return;
    setWorking(true);
    setPrompt("");
    try {
      const next = await api("/api/manager/message", { method: "POST", body: JSON.stringify({ agent_id: agent.id, message: outgoing, conversation_id: conversation?.id || null, autonomy }) });
      setConversation(next);
      setConversations((items) => [next, ...items.filter((item) => item.id !== next.id)]);
      if (autonomy === "auto") await onRefresh();
    } catch (error) {
      setPrompt(outgoing);
      notify(error.message, true);
    } finally {
      setWorking(false);
    }
  }

  async function applyChanges() {
    if (!conversation || applying) return;
    setApplying(true);
    try {
      const next = await api(`/api/manager/conversations/${encodeURIComponent(conversation.id)}/apply`, { method: "POST", body: "{}" });
      setConversation(next);
      setConversations((items) => [next, ...items.filter((item) => item.id !== next.id)]);
      await onRefresh();
      notify("Reviewed change applied to the client agent.");
    } catch (error) {
      notify(error.message, true);
    } finally {
      setApplying(false);
    }
  }

  return <div className={`manager-workspace ${liveOpen ? "live-open" : "live-closed"}`}>
    <aside className="manager-history-rail"><button className="new-manager-task" onClick={() => setConversation(null)}>＋ New agent task</button><div className="manager-rail-section"><span>Manager conversations</span>{conversations.length ? conversations.map((item) => <button key={item.id} className={conversation?.id === item.id ? "active" : ""} onClick={() => setConversation(item)}><i>◌</i><span><strong>{item.title}</strong><small>{item.messages.length} messages · {item.autonomy}</small></span></button>) : <p>Your work with the Manager will appear here.</p>}</div></aside>
    <section className="manager-chat"><header className="manager-chat-header"><div><span className="manager-presence"><i />Manager Agent</span><small>Working on {agent.name} · {agent.openai_model || openai?.model || "app default"} / {agent.openai_reasoning_effort || openai?.reasoning_effort || "provider default"}</small></div><button className={`live-work-toggle ${liveOpen ? "active" : ""}`} onClick={() => setLiveOpen((open) => !open)}><span>⌁</span> Live work{latestManagerMessage?.actions.length ? <b>{latestManagerMessage.actions.length}</b> : null}<i>{liveOpen ? "›" : "‹"}</i></button></header>
      <div className="manager-chat-scroll">{conversation ? <div className="manager-message-list">{conversation.messages.map((message) => <ManagerMessage key={message.id} message={message} onApply={applyChanges} applying={applying} />)}{working && <div className="manager-thinking"><span><i /><i /><i /></span>Manager is selecting tools and inspecting the agent…</div>}<div ref={bottomRef} /></div> : <div className="manager-welcome"><span className="manager-orb">M</span><p className="eyebrow">YOUR AGENTIC MANAGER</p><h2>What should the Manager do with {agent.name}?</h2><p>Ask it to inspect or change the agent—or, for imported agents, launch the runtime, discover MCP tools, and prove a real tool call.</p><div className="manager-starters">{EDIT_STARTERS.map((starter) => <button key={starter} onClick={() => send(null, starter)}>{starter}<span>→</span></button>)}</div></div>}</div>
      <form className="manager-composer" onSubmit={send}><textarea rows="2" value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder={`Tell the Manager what to do with ${agent.name}…`} /><div><span><i />{autonomy === "auto" ? "May launch, stop, call tools, and apply validated changes" : "Read-only runtime checks; edits wait for review"}</span><div className="manager-compose-actions"><div className="composer-permission"><span>Permission</span><button type="button" className={autonomy === "review" ? "active" : ""} onClick={() => setAutonomy("review")}>Review</button><button type="button" className={autonomy === "auto" ? "active" : ""} onClick={() => setAutonomy("auto")}>Auto</button></div><button className="manager-send-button" disabled={working || !prompt.trim()}>{working ? "Working…" : "Send"} <b>↑</b></button></div></div></form>
    </section>
    <aside className="manager-live-panel" aria-hidden={!liveOpen}><div className="manager-live-heading"><div><span>Live work</span><small>{working ? "Orchestrating now" : latestManagerMessage ? "Latest run" : "Waiting for task"}</small></div><button onClick={() => setLiveOpen(false)} aria-label="Collapse live work">×</button></div>{working ? <div className="live-working"><span><i /></span><strong>Understanding request</strong><small>The Manager is deciding which MCP specialist to call first.</small></div> : latestManagerMessage ? <><div className="manager-live-section"><span>Tool route</span>{latestManagerMessage.actions.map((action, index) => <div className="live-action" key={action.id}><b>{index + 1}</b><div><strong>{action.title}</strong><small>{action.server} MCP · {action.tool}</small><em>{action.detail}</em></div><i className={action.status}>✓</i></div>)}</div><div className="manager-live-section"><span>Outcome</span><div className="live-outcome"><strong>{latestManagerMessage.changes.length} change{latestManagerMessage.changes.length === 1 ? "" : "s"}</strong><small>{latestManagerMessage.changes.some((change) => change.status === "pending") ? "Waiting for review" : "Applied to workspace"}</small></div>{latestManagerMessage.evaluation && <div className="live-outcome"><strong>{latestManagerMessage.evaluation.checks.length} checks</strong><small>{latestManagerMessage.evaluation.status}</small></div>}</div></> : <div className="live-empty"><span>⌁</span><strong>No active run</strong><p>Tool calls, changes, and validation will appear here while the Manager works.</p></div>}<div className="manager-live-footer"><span>Target connection</span><strong><i />Local workspace + MCP</strong><small>{agent.mcp_endpoint}</small></div></aside>
  </div>;
}

function AgentTester({ agent, openai, conversations, conversation, setConversation, contextMode, setContextMode, requestedTool, message, setMessage, sending, send }) {
  const hasStandaloneTools = agent.mcp_tools.some((tool) => tool.name === "support.lookup_ticket");
  const starters = hasStandaloneTools ? ["Look up support ticket TCK-9001 and tell me its current status.", "Look up TCK-9001, estimate its resolution time, and include the live proof values."] : TEST_STARTERS[agent.id] || [];
  const isLiveEndpoint = agent.mcp_endpoint?.startsWith("http://") || agent.mcp_endpoint?.startsWith("https://");
  const effectiveModel = agent.openai_model || openai?.model || "app default";
  const effectiveReasoning = agent.openai_reasoning_effort || openai?.reasoning_effort || "provider default";
  return <div className="conversation-workspace studio-test-workspace"><aside className="conversation-rail"><div className="rail-heading"><div><span>Test conversations</span><small>{conversations.length} with this agent</small></div><button onClick={() => setConversation(null)} aria-label="New conversation">＋</button></div><div className="conversation-list">{conversations.length ? conversations.map((item) => <button key={item.id} className={conversation?.id === item.id ? "active" : ""} onClick={() => setConversation(item)}><strong>{item.title}</strong><small>{item.messages.length} messages · {new Date(item.updated_at).toLocaleDateString()}</small></button>) : <div className="rail-empty">Test runs will stay with this agent.</div>}</div></aside><section className="chat-surface"><header className="chat-header"><span className="agent-presence"><i />Testing {agent.name}</span><div className="context-mode"><span>Context</span><button className={contextMode === "minimal" ? "active" : ""} onClick={() => setContextMode("minimal")}>Focused</button><button className={contextMode === "full" ? "active" : ""} onClick={() => setContextMode("full")}>Import all</button></div></header><div className="chat-scroll">{conversation ? <Conversation conversation={conversation} /> : <div className="conversation-empty"><span className="soft-orb">✣</span><h2>Test {agent.name}</h2><p>Talk directly to the client agent and inspect its tool use and verification evidence.</p><div className="starter-grid">{starters.map((starter) => <button key={starter} onClick={() => send(null, starter)}>{starter}<span>→</span></button>)}</div></div>}</div><form className="chat-composer" onSubmit={send}><textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder={`Test ${agent.name}…`} rows="2" /><div><span>{contextMode === "full" ? "Full agent context will be imported" : "Only relevant context will be imported"}</span><button disabled={sending || !message.trim()}>{sending ? "Working…" : "Run test"} <b>↑</b></button></div></form></section><aside className="context-panel"><div className="context-panel-head"><span>Test context</span><small>{contextMode === "full" ? "Full import" : "Focused import"}</small></div><div className="context-block"><span>Execution path</span><strong>{isLiveEndpoint ? "External MCP" : "Local demo"}</strong><small className="context-endpoint">{agent.mcp_endpoint || "No endpoint configured"}</small></div><div className="context-block"><span>OpenAI model</span><strong>{effectiveModel}</strong><small>{effectiveReasoning} reasoning · {agent.openai_model ? "agent override" : "app default"}</small></div><div className="context-block"><span>Active configuration</span><strong>{agent.response_style || "balanced"} responses</strong><small>{agent.verification_mode || "balanced"} verification · memory {agent.memory_enabled === false ? "off" : "on"}</small></div><div className="context-block"><span>Enabled tools</span>{agent.mcp_tools.filter((tool) => !agent.enabled_tools?.length || agent.enabled_tools.includes(tool.name)).map((tool) => <div className={`context-tool ${requestedTool === tool.name ? "selected" : ""}`} key={tool.name}><i />{tool.name}</div>)}</div><div className="context-block"><span>Instructions</span><small className="context-instructions">{agent.instructions}</small></div></aside></div>;
}

export default function WorkspacePage({ agents, openai, onRefresh, notify }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedAgent = searchParams.get("agent");
  const requestedTool = searchParams.get("tool");
  const requestedConversation = searchParams.get("conversation");
  const [mode, setModeState] = useState(searchParams.get("mode") === "test" || requestedConversation || requestedTool ? "test" : "edit");
  const [agentId, setAgentId] = useState(requestedAgent || agents[0]?.id || "");
  const [contextMode, setContextMode] = useState(searchParams.get("context") === "full" ? "full" : "minimal");
  const [conversations, setConversations] = useState([]);
  const [conversation, setConversation] = useState(null);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [agentListOpen, setAgentListOpen] = useState(false);
  const selectedAgent = useMemo(() => agents.find((agent) => agent.id === agentId) || agents[0], [agents, agentId]);

  useEffect(() => {
    if (!agentId) return;
    let active = true;
    api(`/api/conversations?agent_id=${encodeURIComponent(agentId)}`).then((items) => { if (active) { setConversations(items); setConversation(items.find((item) => item.id === requestedConversation) || null); } }).catch((error) => notify(error.message, true));
    return () => { active = false; };
  }, [agentId, notify, requestedConversation]);

  function updateUrl(nextAgent, nextMode) { const params = { agent: nextAgent, mode: nextMode }; if (nextMode === "test") params.context = contextMode; setSearchParams(params); }
  function selectAgent(nextId) { setAgentId(nextId); setConversation(null); setAgentListOpen(false); updateUrl(nextId, mode); }
  function setMode(nextMode) { setModeState(nextMode); updateUrl(agentId, nextMode); }
  async function sendTest(event, suggestedMessage) {
    event?.preventDefault();
    const outgoing = (suggestedMessage || message).trim();
    if (!outgoing || sending) return;
    setSending(true); setMessage("");
    try {
      const next = await api("/api/conversations/message", { method: "POST", body: JSON.stringify({ agent_id: selectedAgent.id, message: outgoing, conversation_id: conversation?.id || null, context_mode: contextMode, tool_name: requestedTool || null }) });
      setConversation(next); setConversations((items) => [next, ...items.filter((item) => item.id !== next.id)]); await onRefresh();
    } catch (error) { setMessage(outgoing); notify(error.message, true); }
    finally { setSending(false); }
  }

  if (!selectedAgent) return null;
  return <div className="workspace-page-full"><header className="studio-header"><div className="studio-title"><p className="eyebrow">AGENT STUDIO</p><h1>{mode === "edit" ? "Build with your Manager" : "Test your client agent"}</h1><p>{mode === "edit" ? "Describe the change. Our Manager chooses the tools and does the work." : "Query the selected client agent exactly as its users would."}</p></div><div className="studio-header-actions"><div className="agent-list-select"><button className="agent-list-trigger" onClick={() => setAgentListOpen((open) => !open)} aria-expanded={agentListOpen}><span>{selectedAgent.name.charAt(0)}</span><span><small>Client agent</small><strong>{selectedAgent.name}</strong></span><b>{agentListOpen ? "⌃" : "⌄"}</b></button>{agentListOpen && <div className="agent-list-popover"><div className="agent-list-heading"><span>Select a client agent</span><small>{agents.length} available</small></div>{agents.map((agent) => <button key={agent.id} className={agent.id === selectedAgent.id ? "active" : ""} onClick={() => selectAgent(agent.id)}><span>{agent.name.charAt(0)}</span><span><strong>{agent.name}</strong><small>{agent.description}</small></span><i>{agent.id === selectedAgent.id ? "✓" : "›"}</i></button>)}</div>}</div><div className="studio-mode-toggle"><button className={mode === "edit" ? "active" : ""} onClick={() => setMode("edit")}><span>✣</span>Manager</button><button className={mode === "test" ? "active" : ""} onClick={() => setMode("test")}><span>▷</span>Test client</button></div></div></header><div className="studio-body">{mode === "edit" ? <ManagerWorkspace key={selectedAgent.id} agent={selectedAgent} openai={openai} onRefresh={onRefresh} notify={notify} /> : <AgentTester agent={selectedAgent} openai={openai} conversations={conversations} conversation={conversation} setConversation={setConversation} contextMode={contextMode} setContextMode={setContextMode} requestedTool={requestedTool} message={message} setMessage={setMessage} sending={sending} send={sendTest} />}</div></div>;
}
