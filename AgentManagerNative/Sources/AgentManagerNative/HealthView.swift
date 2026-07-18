import SwiftUI

struct HealthView: View {
    @EnvironmentObject private var store: AppStore
    @State private var query = ""
    @State private var kind = "all"
    @State private var status = "all"
    @State private var refreshing = false
    @State private var testingOpenAI = false
    @State private var expanded: String?

    private var results: [HealthResult] { store.health?.results ?? [] }
    private var kinds: [String] {
        ["all"] + Array(Set(results.map(\.kind))).sorted()
    }
    private var filtered: [HealthResult] {
        results.filter { result in
            (query.isEmpty || "\(result.name) \(result.message)".localizedCaseInsensitiveContains(query))
                && (kind == "all" || result.kind == kind)
                && (status == "all" || result.status == status)
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            openAIProvider
            summary
            filters
            ScrollView {
                LazyVStack(spacing: 5) {
                    ForEach(filtered) { result in
                        healthRow(result)
                    }
                    if filtered.isEmpty {
                        ContentUnavailableView.search(text: query)
                            .padding(.top, 100)
                    }
                }
                .padding(18)
                .frame(maxWidth: 1050)
                .frame(maxWidth: .infinity)
            }
        }
    }

    private var openAIProvider: some View {
        let provider = store.health?.openai ?? store.overview?.openai
        return HStack(spacing: 16) {
            RoundedRectangle(cornerRadius: 11)
                .fill(provider?.status == "connected"
                      ? AppTheme.accent.opacity(0.16)
                      : Color.white.opacity(0.07))
                .frame(width: 44, height: 44)
                .overlay(
                    Text("AI")
                        .font(.caption.monospaced().weight(.bold))
                        .foregroundStyle(
                            provider?.status == "error"
                            ? AppTheme.danger
                            : AppTheme.accent
                        )
                )

            VStack(alignment: .leading, spacing: 4) {
                Text("OPENAI RESPONSES API")
                    .font(.caption2.monospaced().weight(.semibold))
                    .foregroundStyle(AppTheme.secondaryText)
                Text(providerTitle(provider))
                    .font(.headline)
                Text(providerDetail(provider))
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)
                    .lineLimit(2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Divider().frame(height: 46)
            providerValue("Model", provider?.effectiveModel ?? "—")
            providerValue("Reasoning", provider?.reasoningEffort ?? "default")
            providerValue(
                "Project",
                provider?.projectConfigured == true ? "configured" : "automatic"
            )
            Divider().frame(height: 46)

            VStack(alignment: .trailing, spacing: 8) {
                StatusPill(status: provider?.status ?? "not_configured")
                Button(testingOpenAI ? "Testing…" : "Test Connection") {
                    Task { await testOpenAI() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(provider?.configured != true || testingOpenAI)
            }
        }
        .padding(16)
        .liquidGlass(cornerRadius: 16, interactive: true)
        .padding(.horizontal, 18)
        .padding(.top, 14)
    }

    private func providerValue(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label.uppercased())
                .font(.caption2)
                .foregroundStyle(AppTheme.secondaryText)
            Text(value)
                .font(.caption.monospaced().weight(.semibold))
                .lineLimit(1)
        }
        .frame(minWidth: 95, alignment: .leading)
    }

    private func providerTitle(_ provider: OpenAIStatus?) -> String {
        guard let provider else { return "Loading provider status" }
        if provider.status == "connected" { return "Live reasoning is connected" }
        if provider.status == "error" { return "OpenAI needs attention" }
        if provider.configured { return "API key loaded — connection not tested" }
        return "API key is not configured"
    }

    private func providerDetail(_ provider: OpenAIStatus?) -> String {
        guard let provider else { return "Waiting for the backend readiness report." }
        if let error = provider.lastError { return error }
        if provider.configured {
            return "Run a small readiness request to verify the key, project, model, and billing path."
        }
        return "Add OPENAI_API_KEY to the app environment to enable live Manager reasoning."
    }

    private var header: some View {
        HStack(alignment: .bottom) {
            PageTitle(
                eyebrow: "CONTINUOUS GUARD",
                title: "System health",
                detail: "Narrow to components that need investigation, then open the owning agent in context."
            )
            Spacer()
            Button {
                Task { await refresh() }
            } label: {
                Label(refreshing ? "Refreshing" : "Refresh Probes", systemImage: "arrow.clockwise")
            }
            .buttonStyle(.borderedProminent)
            .disabled(refreshing)
        }
        .padding(22)
        .background(AppTheme.surface)
    }

    private var summary: some View {
        HStack(spacing: 18) {
            HStack(alignment: .firstTextBaseline, spacing: 7) {
                Text("\(store.health?.healthy ?? 0)/\(store.health?.total ?? 0)")
                    .font(.system(size: 34, weight: .semibold, design: .rounded))
                Text("healthy components")
                    .foregroundStyle(AppTheme.secondaryText)
            }
            Divider().frame(height: 38)
            VStack(alignment: .leading, spacing: 3) {
                Text(store.health?.status == "healthy"
                     ? "All monitored components are operational."
                     : "Some components need attention.")
                    .font(.headline)
                Text("Probe results use the same monitoring connection as the website.")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)
            }
            Spacer()
            StatusPill(status: store.health?.status ?? "degraded")
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 15)
        .background(AppTheme.raised)
    }

    private var filters: some View {
        HStack {
            TextField("Search components or messages", text: $query)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 340)
            Picker("Component", selection: $kind) {
                ForEach(kinds, id: \.self) {
                    Text($0 == "all" ? "All Components" : $0.capitalized).tag($0)
                }
            }
            .frame(width: 170)
            Picker("Status", selection: $status) {
                Text("All Statuses").tag("all")
                Text("Healthy").tag("healthy")
                Text("Degraded").tag("degraded")
                Text("Offline").tag("offline")
            }
            .frame(width: 155)
            Spacer()
            Text("\(filtered.count) results")
                .font(.caption)
                .foregroundStyle(AppTheme.secondaryText)
        }
        .padding(11)
        .background(AppTheme.sidebar)
    }

    private func healthRow(_ result: HealthResult) -> some View {
        VStack(spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.15)) {
                    expanded = expanded == result.id ? nil : result.id
                }
            } label: {
                HStack(spacing: 12) {
                    Text(result.kind.uppercased())
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(AppTheme.secondaryText)
                        .frame(width: 76, alignment: .leading)
                    Text(result.name)
                        .font(.callout.weight(.semibold))
                    Spacer()
                    StatusPill(status: result.status)
                    Text("\(result.latencyMs) ms")
                        .font(.caption.monospaced())
                        .foregroundStyle(AppTheme.secondaryText)
                        .frame(width: 70, alignment: .trailing)
                    Image(systemName: expanded == result.id ? "chevron.up" : "chevron.down")
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                }
                .padding(12)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            if expanded == result.id {
                Divider()
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(result.message)
                        Text("Last checked \(result.checkedAt.shortTimestamp)")
                            .font(.caption)
                            .foregroundStyle(AppTheme.secondaryText)
                    }
                    Spacer()
                    if result.status != "healthy", target(for: result) != nil {
                        Button {
                            investigate(result)
                        } label: {
                            Label("Open in Workspace", systemImage: "arrow.up.right")
                        }
                        .buttonStyle(.borderedProminent)
                    }
                }
                .padding(14)
            }
        }
        .background(AppTheme.surface)
        .overlay(RoundedRectangle(cornerRadius: 7).stroke(AppTheme.border))
        .clipShape(RoundedRectangle(cornerRadius: 7))
    }

    private func refresh() async {
        guard let api = store.api else { return }
        refreshing = true
        do {
            let next: HealthReport = try await api.get("/api/health")
            store.health = next
            store.show("Health probes refreshed.")
        } catch {
            store.show(error.localizedDescription, error: true)
        }
        refreshing = false
    }

    private func testOpenAI() async {
        guard let api = store.api else { return }
        testingOpenAI = true
        do {
            let provider: OpenAIStatus = try await api.post("/api/openai/test")
            if let health = store.health {
                store.health = HealthReport(
                    status: health.status,
                    healthy: health.healthy,
                    total: health.total,
                    results: health.results,
                    openai: provider
                )
            }
            try? await store.refresh()
            store.show("OpenAI connected with \(provider.effectiveModel).")
        } catch {
            try? await store.refresh()
            store.show(error.localizedDescription, error: true)
        }
        testingOpenAI = false
    }

    private func target(for result: HealthResult) -> (AgentRecord, String?)? {
        guard let architecture = store.overview?.architecture else { return nil }
        if result.kind == "agent",
           let agent = architecture.agents.first(where: {
               $0.id == result.backendID || $0.name == result.name
           }) {
            return (agent, nil)
        }
        var tool: ToolRecord?
        if result.kind == "tool" {
            tool = architecture.tools.first {
                $0.id == result.backendID || $0.name == result.name
            }
        } else if result.kind == "endpoint" {
            tool = architecture.tools.first { $0.endpointIds.contains(result.backendID) }
        }
        guard let tool,
              let agent = architecture.agents.first(where: {
                  $0.toolIds.contains(tool.id)
                      || $0.mcpTools.contains(where: { $0.name == tool.name })
                      || $0.name.lowercased() == tool.owner.lowercased()
              })
        else { return nil }
        return (agent, tool.name)
    }

    private func investigate(_ result: HealthResult) {
        guard let (agent, tool) = target(for: result) else { return }
        store.openWorkspace(agentID: agent.id, mode: "test", tool: tool)
    }
}
