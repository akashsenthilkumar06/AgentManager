import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api";
import AppShell from "./layout/AppShell";
import AgentsPage from "./pages/AgentsPage";
import AgentWorkspacePage from "./pages/AgentWorkspacePage";
import BenchmarksPage from "./pages/BenchmarksPage";
import DashboardPage from "./pages/DashboardPage";
import HealthPage from "./pages/HealthPage";
import HistoryPage from "./pages/HistoryPage";
import WorkspacePage from "./pages/WorkspacePage";
import FinanceDemoPage from "./pages/FinanceDemoPage";

export default function App() {
  const location = useLocation();
  const [overview, setOverview] = useState(null);
  const [health, setHealth] = useState(null);
  const [toast, setToast] = useState(null);

  const notify = useCallback((message, error = false) => {
    setToast({ message, error });
    window.setTimeout(() => setToast(null), 3200);
  }, []);

  const refresh = useCallback(async () => {
    const [nextOverview, nextHealth] = await Promise.all([api("/api/overview"), api("/api/health")]);
    setOverview(nextOverview);
    setHealth(nextHealth);
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([api("/api/overview"), api("/api/health")])
      .then(([nextOverview, nextHealth]) => {
        if (active) { setOverview(nextOverview); setHealth(nextHealth); }
      })
      .catch((error) => notify(error.message, true));
    return () => { active = false; };
  }, [notify]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      api("/api/overview")
        .then(setOverview)
        .catch(() => {});
    }, 15000);
    return () => window.clearInterval(timer);
  }, []);

  async function resetDemo() {
    if (!window.confirm("Reset the demo architecture and remove generated tools?")) return;
    try { await api("/api/reset", { method: "POST", body: "{}" }); await refresh(); notify("Demo workspace reset."); }
    catch (error) { notify(error.message, true); }
  }

  if (!overview) return <div className="loading-screen"><span className="brand-mark"><i /><i /><i /></span><strong>Connecting to the Manager</strong><span>Loading architecture and health signals…</span></div>;

  return (
    <AppShell overview={overview} onReset={resetDemo}>
      <div className="route-stage" key={location.pathname}><Routes location={location}>
        <Route path="/" element={<DashboardPage overview={overview} health={health} />} />
        <Route path="/workspace" element={<WorkspacePage agents={overview.architecture.agents} openai={overview.openai} onRefresh={refresh} notify={notify} />} />
        <Route path="/agents" element={<AgentsPage agents={overview.architecture.agents} conversations={overview.recent_conversations || []} onRefresh={refresh} notify={notify} />} />
        <Route path="/agents/:agentId" element={<AgentWorkspacePage agents={overview.architecture.agents} openai={overview.openai} onRefresh={refresh} notify={notify} />} />
        <Route path="/benchmarks" element={<BenchmarksPage agents={overview.architecture.agents} notify={notify} />} />
        <Route path="/finance-demo" element={<FinanceDemoPage notify={notify} />} />
        <Route path="/architecture" element={<Navigate to="/agents" replace />} />
        <Route path="/files" element={<Navigate to="/agents" replace />} />
        <Route path="/health" element={<HealthPage health={health} architecture={overview.architecture} setHealth={setHealth} notify={notify} />} />
        <Route path="/history" element={<HistoryPage builds={overview.recent_builds} conversations={overview.recent_conversations || []} agents={overview.architecture.agents} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes></div>
      {toast && <div className={`toast show ${toast.error ? "error" : ""}`} role="status">{toast.message}</div>}
    </AppShell>
  );
}
