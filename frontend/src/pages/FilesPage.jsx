import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import EmptyResults from "../components/EmptyResults";
import FilterBar, { FilterChips, SearchField, ViewToggle } from "../components/FilterBar";
import PageHeader from "../components/PageHeader";

function formatSize(bytes) {
  if (!bytes) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function workspaceFileUrl(workspaceId, path) {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/file?path=${encodeURIComponent(path)}`;
}

function workspaceFilesUrl(workspaceId, path = "") {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/files?path=${encodeURIComponent(path)}`;
}

export default function FilesPage({ agents, notify }) {
  const [workspaces, setWorkspaces] = useState([]);
  const [workspaceId, setWorkspaceId] = useState("default");
  const [summary, setSummary] = useState(null);
  const [listing, setListing] = useState(null);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [path, setPath] = useState("");
  const [name, setName] = useState("");
  const [agentId, setAgentId] = useState("");
  const [query, setQuery] = useState("");
  const [type, setType] = useState("all");
  const [view, setView] = useState("split");

  const loadWorkspaces = useCallback(async () => {
    const body = await api("/api/workspaces");
    setWorkspaces(body.workspaces || []);
    if (!body.workspaces?.some((workspace) => workspace.id === workspaceId)) {
      setWorkspaceId("default");
    }
  }, [workspaceId]);

  const loadDirectory = useCallback(async (nextWorkspaceId = workspaceId, nextPath = "") => {
    setLoading(true);
    try {
      const [nextSummary, nextListing] = await Promise.all([
        api(`/api/workspaces/${encodeURIComponent(nextWorkspaceId)}`),
        api(workspaceFilesUrl(nextWorkspaceId, nextPath)),
      ]);
      setSummary(nextSummary);
      setListing(nextListing);
      setSelected(null);
      setQuery("");
    } catch (error) {
      notify(error.message, true);
    } finally {
      setLoading(false);
    }
  }, [notify, workspaceId]);

  useEffect(() => {
    let active = true;
    api("/api/workspaces")
      .then((body) => {
        if (!active) return;
        setWorkspaces(body.workspaces || []);
        if (!body.workspaces?.some((workspace) => workspace.id === workspaceId)) {
          setWorkspaceId("default");
        }
      })
      .catch((error) => notify(error.message, true));
    return () => { active = false; };
  }, [notify, workspaceId]);

  useEffect(() => {
    let active = true;
    Promise.all([
      api(`/api/workspaces/${encodeURIComponent(workspaceId)}`),
      api(workspaceFilesUrl(workspaceId, "")),
    ])
      .then(([nextSummary, nextListing]) => {
        if (!active) return;
        setSummary(nextSummary);
        setListing(nextListing);
        setSelected(null);
        setQuery("");
      })
      .catch((error) => notify(error.message, true));
    return () => { active = false; };
  }, [notify, workspaceId]);

  const filtered = useMemo(() => (
    listing?.entries || []
  ).filter((entry) => (
    (!query || entry.name.toLowerCase().includes(query.toLowerCase()))
    && (type === "all" || type === entry.kind || (type === "previewable" && entry.previewable))
  )), [listing, query, type]);

  const crumbs = listing?.path ? listing.path.split("/") : [];

  async function connectWorkspace(event) {
    event.preventDefault();
    if (!path.trim() || connecting) return;
    setConnecting(true);
    try {
      const connected = await api("/api/workspaces/connect", {
        method: "POST",
        body: JSON.stringify({
          path,
          name: name || null,
          agent_id: agentId || null,
        }),
      });
      await loadWorkspaces();
      setWorkspaceId(connected.id);
      setPath("");
      setName("");
      setAgentId("");
      notify(`Connected ${connected.name}.`);
    } catch (error) {
      notify(error.message, true);
    } finally {
      setConnecting(false);
    }
  }

  async function open(entry) {
    if (entry.kind === "directory") {
      return loadDirectory(workspaceId, entry.path);
    }
    if (!entry.previewable) {
      return notify("This file type is not available for safe preview.", true);
    }
    try {
      setSelected(await api(workspaceFileUrl(workspaceId, entry.path)));
      if (view === "list") setView("split");
    } catch (error) {
      notify(error.message, true);
    }
  }

  function selectWorkspace(nextWorkspaceId) {
    setWorkspaceId(nextWorkspaceId);
    setSelected(null);
  }

  function clear() {
    setQuery("");
    setType("all");
  }

  return (
    <>
      <PageHeader
        eyebrow="LOCAL AGENT CONTEXT"
        title="Connected workspaces"
        description="Connect a local agent directory to the backend, browse its safe source files, and keep browser access read-only."
        actions={summary && <span className="read-only-badge">READ ONLY</span>}
      />

      <section className="workspace-connect-panel">
        <form onSubmit={connectWorkspace}>
          <label>
            <span>Local path</span>
            <input value={path} onChange={(event) => setPath(event.target.value)} placeholder="/Users/you/projects/my-agent" spellCheck="false" />
          </label>
          <label>
            <span>Name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Support agent workspace" />
          </label>
          <label>
            <span>Agent</span>
            <select value={agentId} onChange={(event) => setAgentId(event.target.value)}>
              <option value="">Unassigned</option>
              {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
            </select>
          </label>
          <button className="primary-button" disabled={connecting || !path.trim()}>{connecting ? "Connecting..." : "Connect workspace"}</button>
        </form>
        <p>Local paths are resolved by the backend process. Deployed browser-only hosting still needs a native app or local companion service for filesystem permissions.</p>
      </section>

      <div className="workspace-selector-strip">
        {workspaces.map((workspace) => (
          <button key={workspace.id} className={workspace.id === workspaceId ? "active" : ""} onClick={() => selectWorkspace(workspace.id)}>
            <strong>{workspace.name || workspace.root_name}</strong>
            <small>{workspace.default ? "Default" : workspace.agent_id || "Connected"} · {workspace.files} files</small>
          </button>
        ))}
      </div>

      <div className="workspace-compact">
        <span><strong>{summary?.name || summary?.root_name}</strong><small>{summary?.root_path}</small></span>
        <span>{summary?.files} files</span>
        <span>{summary?.directories} folders</span>
      </div>

      <FilterBar resultCount={filtered.length} hasFilters={Boolean(query || type !== "all")} onClear={clear}>
        <SearchField value={query} onChange={setQuery} placeholder="Filter this folder" />
        <FilterChips value={type} onChange={setType} options={["all", "directory", "file", "previewable"]} />
        <ViewToggle value={view} onChange={setView} options={[["split", "◫", "Split preview"], ["list", "☷", "List only"]]} />
      </FilterBar>

      <div className={`file-browser ${view === "list" ? "list-only" : ""}`}>
        <section className="file-pane">
          <div className="breadcrumbs">
            <button onClick={() => loadDirectory(workspaceId, "")}>{listing?.root_name || "Workspace"}</button>
            {crumbs.map((crumb, index) => (
              <button key={`${crumb}-${index}`} onClick={() => loadDirectory(workspaceId, crumbs.slice(0, index + 1).join("/"))}>/ {crumb}</button>
            ))}
          </div>
          {listing?.parent !== null && <button className="file-row parent" onClick={() => loadDirectory(workspaceId, listing.parent)}>↰ <span>Parent directory</span></button>}
          {loading
            ? <div className="empty-state">Loading directory...</div>
            : filtered.length
              ? filtered.map((entry) => (
                <button className={`file-row ${selected?.path === entry.path ? "selected" : ""}`} key={entry.path} onClick={() => open(entry)}>
                  <span className="file-icon">{entry.kind === "directory" ? "▰" : "▱"}</span>
                  <span><strong>{entry.name}</strong><small>{entry.kind === "directory" ? "Folder" : formatSize(entry.size)}</small></span>
                  <b>{entry.kind === "directory" ? "›" : entry.previewable ? "Preview" : "Restricted"}</b>
                </button>
              ))
              : <EmptyResults onClear={clear} />}
        </section>
        {view === "split" && (
          <section className="preview-pane">
            {selected ? (
              <>
                <div className="preview-head">
                  <div>
                    <span>{selected.language.toUpperCase()}</span>
                    <h2>{selected.name}</h2>
                    <p>{selected.path} · {formatSize(selected.size)}{selected.truncated ? " · preview truncated" : ""}</p>
                  </div>
                </div>
                <pre><code>{selected.content}</code></pre>
              </>
            ) : (
              <div className="preview-empty">
                <span>▱</span>
                <h2>Select a file</h2>
                <p>Only supported text files are previewed, and sensitive names stay hidden.</p>
              </div>
            )}
          </section>
        )}
      </div>
    </>
  );
}
