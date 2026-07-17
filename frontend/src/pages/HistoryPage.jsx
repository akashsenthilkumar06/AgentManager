import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import EmptyResults from "../components/EmptyResults";
import FilterBar, { SearchField } from "../components/FilterBar";
import PageHeader from "../components/PageHeader";

export default function HistoryPage({ builds, conversations, agents }) {
  const navigate = useNavigate();
  const [kind, setKind] = useState("conversations");
  const [query, setQuery] = useState("");
  const filteredConversations = useMemo(() => conversations.filter((conversation) => {
    const agent = agents.find((item) => item.id === conversation.agent_id);
    return !query || `${conversation.title} ${agent?.name || ""}`.toLowerCase().includes(query.toLowerCase());
  }), [conversations, agents, query]);
  const filteredBuilds = useMemo(() => builds.filter((build) => !query || `${build.prompt} ${build.tool?.name || ""}`.toLowerCase().includes(query.toLowerCase())), [builds, query]);
  return <><PageHeader eyebrow="WORKSPACE MEMORY" title="Activity" description="Return to agent conversations and capability runs without digging through system internals." />
    <div className="activity-tabs"><button className={kind === "conversations" ? "active" : ""} onClick={() => setKind("conversations")}>Agent conversations <span>{conversations.length}</span></button><button className={kind === "builds" ? "active" : ""} onClick={() => setKind("builds")}>Capability runs <span>{builds.length}</span></button></div>
    <FilterBar resultCount={kind === "conversations" ? filteredConversations.length : filteredBuilds.length} hasFilters={Boolean(query)} onClear={() => setQuery("")}><SearchField value={query} onChange={setQuery} placeholder={`Search ${kind === "conversations" ? "conversations or agents" : "capabilities or requests"}`} /></FilterBar>
    {kind === "conversations" ? <div className="activity-list">{filteredConversations.length ? filteredConversations.map((conversation) => {
      const agent = agents.find((item) => item.id === conversation.agent_id);
      const toolCalls = conversation.messages.flatMap((message) => message.tool_calls);
      const verified = conversation.messages.filter((message) => message.verification?.status === "verified").length;
      return <button className="activity-card" key={conversation.id} onClick={() => navigate(`/workspace?agent=${conversation.agent_id}&mode=test&conversation=${conversation.id}`)}><span className="activity-avatar">{agent?.name.charAt(0) || "A"}</span><div><span>{agent?.name || conversation.agent_id}</span><strong>{conversation.title}</strong><small>{conversation.messages.length} messages · {toolCalls.length} tool runs · {verified} verified outputs</small></div><time>{new Date(conversation.updated_at).toLocaleString()}</time><b>→</b></button>;
    }) : <EmptyResults onClear={() => setQuery("")} message="No conversations match your search." />}</div>
      : <div className="activity-list">{filteredBuilds.length ? filteredBuilds.map((build) => <article className="activity-card static" key={build.id}><span className="activity-avatar build">✣</span><div><span>Manager orchestration</span><strong>{build.tool?.name || "Capability run"}</strong><small>{build.prompt}</small></div><span className={`status-pill ${build.status}`}>{build.status.replace("_", " ")}</span><time>{new Date(build.created_at).toLocaleString()}</time></article>) : <EmptyResults onClear={() => setQuery("")} message="No capability runs match your search." />}</div>}
  </>;
}
