import { useNavigate } from "react-router-dom";
import PageHeader from "../components/PageHeader";
import { findWorkspaceTarget, workspaceUrl } from "../workspaceLinks";

function timeAgo(value) {
  if (!value) return "just now";
  const elapsed = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(elapsed / 60000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function DashboardPage({ overview, health }) {
  const navigate = useNavigate();
  const architecture = overview.architecture;
  const agents = architecture.agents;
  const conversations = overview.recent_conversations || [];
  const builds = overview.recent_builds || [];
  const latestConversation = conversations[0];
  const latestAgent = agents.find((agent) => agent.id === latestConversation?.agent_id) || agents[0];
  const attention = (health?.results || []).filter((result) => result.status !== "healthy");
  const recentActivity = [
    ...conversations.map((conversation) => ({ ...conversation, kind: "conversation", date: conversation.updated_at })),
    ...builds.map((build) => ({ ...build, kind: "build", date: build.created_at })),
  ].sort((a, b) => new Date(b.date) - new Date(a.date)).slice(0, 4);

  const continueUrl = latestConversation
    ? workspaceUrl({ agentId: latestConversation.agent_id, mode: "test", conversationId: latestConversation.id })
    : workspaceUrl({ agentId: latestAgent?.id });

  function openAttention(result) {
    const target = findWorkspaceTarget(result, architecture);
    if (!target) {
      navigate("/health");
      return;
    }
    navigate(workspaceUrl({
      agentId: target.agentId,
      mode: "test",
      toolName: target.toolName,
      context: "full",
    }));
  }

  return (
    <div className="dashboard-page">
      <PageHeader
        eyebrow="AGENT OPERATING SYSTEM"
        title="Control center"
        description="Pick up where you left off, resolve what needs attention, or move directly into an agent workspace."
        actions={<button className="primary-button" onClick={() => navigate(workspaceUrl({ agentId: latestAgent?.id }))}>Open workspace <span>→</span></button>}
      />

      <section className="dashboard-hero">
        <article className="continue-card">
          <div className="dashboard-card-label"><span>CONTINUE WORKING</span><i>Active</i></div>
          <div className="continue-agent">
            <span>{latestAgent?.name.charAt(0) || "A"}</span>
            <div><strong>{latestAgent?.name || "Manager workspace"}</strong><small>{latestAgent?.owner || "Agent Manager"}</small></div>
          </div>
          <h2>{latestConversation?.title || "Start a new agent task"}</h2>
          <p>{latestConversation ? `${latestConversation.messages.length} messages are ready to continue with the same agent context.` : "Describe a change and let the Manager choose the right MCP tools to complete it."}</p>
          <div className="continue-footer">
            <span>{latestConversation ? `Updated ${timeAgo(latestConversation.updated_at)}` : "Ready when you are"}</span>
            <div>
              {latestConversation && <button className="quiet-button" onClick={() => navigate(workspaceUrl({ agentId: latestAgent?.id }))}>New task</button>}
              <button className="dashboard-primary-action" onClick={() => navigate(continueUrl)}>{latestConversation ? "Resume work" : "Start working"} <b>→</b></button>
            </div>
          </div>
        </article>

        <article className={`system-pulse-card ${health?.status || "healthy"}`}>
          <div className="dashboard-card-label"><span>SYSTEM PULSE</span><i>{health?.status || "checking"}</i></div>
          <div className="pulse-score"><strong>{health ? `${health.healthy}/${health.total}` : "—"}</strong><span>components healthy</span></div>
          <div className="pulse-lines">
            <div><span><i />MCP connections</span><strong>{overview.mcp_servers.length}/{overview.mcp_servers.length}</strong></div>
            <div><span><i />Managed agents</span><strong>{agents.filter((agent) => agent.status === "healthy").length}/{agents.length}</strong></div>
            <div><span><i className={attention.length ? "warning" : ""} />Needs attention</span><strong>{attention.length}</strong></div>
          </div>
          <button onClick={() => navigate("/health")}>View system health <span>→</span></button>
        </article>
      </section>

      <section className="dashboard-section attention-section">
        <div className="dashboard-section-heading">
          <div><span>PRIORITY</span><h2>Needs attention</h2></div>
          <small>{attention.length ? `${attention.length} open issue${attention.length === 1 ? "" : "s"}` : "Nothing is blocking your agents"}</small>
        </div>
        {attention.length ? (
          <div className="attention-grid">
            {attention.slice(0, 3).map((result) => {
              const target = findWorkspaceTarget(result, architecture);
              return (
                <article className="attention-card" key={`${result.kind}-${result.id}`}>
                  <div className="attention-icon">!</div>
                  <div><span>{result.kind} · {result.status}</span><strong>{result.name}</strong><small>{result.message}</small>{target && <em>{target.agentName}{target.toolName ? ` · ${target.toolName}` : ""}</em>}</div>
                  <button onClick={() => openAttention(result)} aria-label={`Open ${result.name} in workspace`}>→</button>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="attention-clear">
            <span>✓</span>
            <div><strong>Everything is clear</strong><small>All monitored tools and connections are operating normally.</small></div>
            <button onClick={() => navigate("/health")}>Review health</button>
          </div>
        )}
      </section>

      <div className="dashboard-columns">
        <section className="dashboard-section agents-overview">
          <div className="dashboard-section-heading">
            <div><span>YOUR TEAM</span><h2>Managed agents</h2></div>
            <button onClick={() => navigate("/agents")}>View all <b>→</b></button>
          </div>
          <div className="dashboard-agent-list">
            {agents.slice(0, 4).map((agent) => (
              <article className="dashboard-agent-row" key={agent.id}>
                <button className="dashboard-agent-main" onClick={() => navigate(`/agents/${agent.id}`)}>
                  <span className="dashboard-agent-avatar">{agent.name.charAt(0)}</span>
                  <span><strong>{agent.name}</strong><small>{agent.owner} · {agent.mcp_tools.length} tools</small></span>
                  <i className={agent.status} />
                </button>
                <button className="dashboard-agent-work" onClick={() => navigate(workspaceUrl({ agentId: agent.id }))}>Work on agent <span>→</span></button>
              </article>
            ))}
          </div>
        </section>

        <section className="dashboard-section recent-overview">
          <div className="dashboard-section-heading">
            <div><span>WORKSPACE MEMORY</span><h2>Recent activity</h2></div>
            <button onClick={() => navigate("/history")}>View all <b>→</b></button>
          </div>
          <div className="dashboard-activity-list">
            {recentActivity.length ? recentActivity.map((item) => {
              const agent = item.kind === "conversation" ? agents.find((entry) => entry.id === item.agent_id) : null;
              const destination = item.kind === "conversation"
                ? workspaceUrl({ agentId: item.agent_id, mode: "test", conversationId: item.id })
                : "/history";
              return (
                <button key={`${item.kind}-${item.id}`} onClick={() => navigate(destination)}>
                  <span className={item.kind}>{item.kind === "conversation" ? agent?.name.charAt(0) || "A" : "✣"}</span>
                  <span><small>{item.kind === "conversation" ? agent?.name || "Agent conversation" : "Manager orchestration"}</small><strong>{item.kind === "conversation" ? item.title : item.tool?.name || "Capability run"}</strong></span>
                  <time>{timeAgo(item.date)}</time>
                </button>
              );
            }) : <div className="dashboard-empty-activity"><span>◌</span><p>Your conversations and Manager runs will appear here.</p></div>}
          </div>
        </section>
      </div>
    </div>
  );
}
