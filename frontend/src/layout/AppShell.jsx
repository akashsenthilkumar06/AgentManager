import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import BrandMark from "../components/BrandMark";

const NAVIGATION = [
  ["/", "⌁", "Workspace"],
  ["/agents", "◎", "Managed agents"],
  ["/history", "↗", "Activity"],
  ["/health", "◉", "System health"],
];

export default function AppShell({ overview, onReset, children }) {
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const isWorkspace = location.pathname === "/";
  useEffect(() => {
    const closeOnEscape = (event) => { if (event.key === "Escape") setMenuOpen(false); };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, []);
  return (
    <div className="app-shell">
      <button className={`menu-orb ${menuOpen ? "open" : ""}`} onClick={() => setMenuOpen((open) => !open)} aria-label={menuOpen ? "Close navigation" : "Open navigation"} aria-expanded={menuOpen}><i /><i /><i /></button>
      <button className={`drawer-backdrop ${menuOpen ? "open" : ""}`} onClick={() => setMenuOpen(false)} aria-label="Close navigation" tabIndex={menuOpen ? 0 : -1} />
      <aside className={`sidebar liquid-drawer ${menuOpen ? "open" : ""}`} aria-hidden={!menuOpen}>
        <div className="brand"><BrandMark /><div><strong>Agent Manager</strong><small>AGENT OPERATING SYSTEM</small></div></div>
        <nav aria-label="Main navigation">
          {NAVIGATION.map(([path, icon, label]) => <NavLink key={path} to={path} end={path === "/"} onClick={() => setMenuOpen(false)} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}><span>{icon}</span>{label}</NavLink>)}
        </nav>
        <div className="sidebar-spacer" />
        <button className="mcp-label mcp-toggle" onClick={() => setConnectionsOpen((open) => !open)}>MCP CONNECTIONS <span>{overview.mcp_servers.length} / {overview.mcp_servers.length} {connectionsOpen ? "⌃" : "⌄"}</span></button>
        <div className={`server-list-shell ${connectionsOpen ? "open" : ""}`}><div className="server-list">{overview.mcp_servers.map((server) => <div className="server-row" key={server.id}><i />{server.name}<span>{server.tools} tool{server.tools === 1 ? "" : "s"}</span></div>)}</div></div>
        <div className="sidebar-footer"><span className="avatar">AS</span><div><strong>Demo workspace</strong><small>Local environment</small></div><button onClick={() => { onReset(); setMenuOpen(false); }} title="Reset demo">↻</button></div>
      </aside>
      <main className={isWorkspace ? "workspace-main" : ""}>{children}</main>
    </div>
  );
}
