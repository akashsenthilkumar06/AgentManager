import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var store: AppStore

    private var overview: Overview { store.overview! }
    private var attention: [HealthResult] {
        store.health?.results.filter { $0.status != "healthy" } ?? []
    }
    private var activeFindings: [ReconciliationFinding] {
        overview.standingFindings.filter { $0.status != "resolved" }
    }
    private var latestConversation: AgentConversation? {
        overview.recentConversations.first
    }
    private var latestAgent: AgentRecord? {
        if let conversation = latestConversation {
            return overview.architecture.agents.first { $0.id == conversation.agentId }
        }
        return overview.architecture.agents.first
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                HStack(alignment: .bottom) {
                    PageTitle(
                        eyebrow: "AGENT OPERATING SYSTEM",
                        title: "Control center",
                        detail: "Continue active work, resolve attention items, or move directly into an agent workspace."
                    )
                    Spacer()
                    Button {
                        if let agent = latestAgent {
                            store.openWorkspace(agentID: agent.id)
                        }
                    } label: {
                        Label("Open Workspace", systemImage: "arrow.up.right")
                    }
                    .buttonStyle(.borderedProminent)
                }

                HStack(alignment: .top, spacing: 14) {
                    continueWorking
                    systemPulse
                }

                standingWatch

                VStack(alignment: .leading, spacing: 12) {
                    sectionHeader("PRIORITY", "Needs attention", trailing: attention.isEmpty ? "Nothing blocking your agents" : "\(attention.count) open")
                    if attention.isEmpty {
                        HStack(spacing: 12) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.title2)
                                .foregroundStyle(AppTheme.accent)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Everything is clear").font(.headline)
                                Text("All monitored tools and connections are operating normally.")
                                    .foregroundStyle(AppTheme.secondaryText)
                            }
                            Spacer()
                            Button("Review Health") { store.section = .health }
                        }
                        .surface(15)
                    } else {
                        ForEach(attention.prefix(3)) { result in
                            Button {
                                investigate(result)
                            } label: {
                                HStack(spacing: 12) {
                                    Image(systemName: "exclamationmark.triangle.fill")
                                        .foregroundStyle(AppTheme.warning)
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text(result.name).font(.headline)
                                        Text(result.message)
                                            .font(.callout)
                                            .foregroundStyle(AppTheme.secondaryText)
                                            .lineLimit(2)
                                    }
                                    Spacer()
                                    StatusPill(status: result.status)
                                    Image(systemName: "chevron.right")
                                        .foregroundStyle(AppTheme.secondaryText)
                                }
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            .surface(14)
                        }
                    }
                }

                HStack(alignment: .top, spacing: 14) {
                    managedAgents
                    recentActivity
                }
            }
            .padding(26)
            .frame(maxWidth: 1260)
            .frame(maxWidth: .infinity)
        }
    }

    private var continueWorking: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("CONTINUE WORKING")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(AppTheme.secondaryText)
                Spacer()
                StatusPill(status: "healthy")
            }
            HStack(spacing: 10) {
                agentAvatar(latestAgent)
                VStack(alignment: .leading, spacing: 2) {
                    Text(latestAgent?.name ?? "Manager workspace").font(.headline)
                    Text(latestAgent?.owner ?? "Agent Manager")
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                }
            }
            Text(latestConversation?.title ?? "Start a new agent task")
                .font(.title2.weight(.semibold))
            Text(latestConversation == nil
                 ? "Describe a change and let the Manager choose the right MCP tools to complete it."
                 : "\(latestConversation!.messages.count) messages are ready to continue with the same agent context.")
                .foregroundStyle(AppTheme.secondaryText)
            Spacer()
            HStack {
                Text(latestConversation?.updatedAt.shortTimestamp ?? "Ready when you are")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)
                Spacer()
                Button(latestConversation == nil ? "Start Working" : "Resume Work") {
                    guard let agent = latestAgent else { return }
                    store.openWorkspace(
                        agentID: agent.id,
                        mode: latestConversation == nil ? "edit" : "test",
                        conversationID: latestConversation?.id
                    )
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 230, alignment: .leading)
        .surface(20)
    }

    private var systemPulse: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("SYSTEM PULSE")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(AppTheme.secondaryText)
                Spacer()
                StatusPill(status: store.health?.status ?? "degraded")
            }
            HStack(alignment: .firstTextBaseline, spacing: 7) {
                Text("\(store.health?.healthy ?? 0)/\(store.health?.total ?? 0)")
                    .font(.system(size: 38, weight: .semibold, design: .rounded))
                Text("components healthy")
                    .foregroundStyle(AppTheme.secondaryText)
            }
            Divider()
            pulseRow("MCP connections", "\(overview.mcpServers.count)/\(overview.mcpServers.count)", healthy: true)
            pulseRow(
                "Managed agents",
                "\(overview.architecture.agents.filter { $0.status == "healthy" }.count)/\(overview.architecture.agents.count)",
                healthy: true
            )
            pulseRow(
                "OpenAI reasoning",
                overview.openai.status == "connected"
                    ? "live"
                    : (overview.openai.configured ? "ready" : "local"),
                healthy: overview.openai.status != "error"
            )
            pulseRow(
                "Needs attention",
                "\(attention.count + activeFindings.count)",
                healthy: attention.isEmpty && activeFindings.isEmpty
            )
            Spacer()
            Button("View System Health") { store.section = .health }
                .buttonStyle(.plain)
                .foregroundStyle(AppTheme.accent)
        }
        .frame(width: 330, alignment: .leading)
        .frame(minHeight: 230, alignment: .leading)
        .surface(20)
    }

    private var standingWatch: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .bottom) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("AUTONOMOUS CONTROL PLANE")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(AppTheme.accent)
                    Text("Caught without a prompt").font(.title3.weight(.semibold))
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Label(
                        overview.reconciliation.mode == "edge_triggered"
                        ? "Edge-triggered"
                        : "Starting",
                        systemImage: "waveform.path.ecg"
                    )
                    .font(.caption.weight(.semibold))
                    Text("\(overview.reconciliation.intervalSeconds)s observation interval · 0 model tokens")
                        .font(.caption2)
                        .foregroundStyle(AppTheme.secondaryText)
                }
            }

            if overview.standingFindings.isEmpty {
                HStack(spacing: 12) {
                    Image(systemName: "scope")
                        .font(.title2)
                        .foregroundStyle(AppTheme.accent)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Fleet baseline is steady").font(.headline)
                        Text("No unprompted drift, duplicates, contract conflicts, or endpoint failures observed.")
                            .font(.callout)
                            .foregroundStyle(AppTheme.secondaryText)
                    }
                    Spacer()
                    Text(overview.reconciliation.lastCheckedAt?.shortTimestamp ?? "Establishing baseline")
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                }
                .surface(14)
            } else {
                ForEach(overview.standingFindings.prefix(4)) { finding in
                    Button {
                        investigate(finding)
                    } label: {
                        HStack(spacing: 12) {
                            Image(systemName: finding.status == "resolved"
                                  ? "checkmark.circle.fill"
                                  : "exclamationmark.triangle.fill")
                                .foregroundStyle(
                                    finding.status == "resolved"
                                    ? AppTheme.accent
                                    : finding.severity == "critical"
                                    ? AppTheme.danger
                                    : AppTheme.warning
                                )
                            VStack(alignment: .leading, spacing: 3) {
                                Text("\(finding.kind.replacingOccurrences(of: "_", with: " ")) · \(finding.status)")
                                    .font(.caption2.weight(.semibold))
                                    .foregroundStyle(AppTheme.secondaryText)
                                Text(finding.title).font(.callout.weight(.semibold))
                                Text(finding.detail)
                                    .font(.caption)
                                    .foregroundStyle(AppTheme.secondaryText)
                                    .lineLimit(2)
                            }
                            Spacer()
                            Text(finding.lastSeenAt.shortTimestamp)
                                .font(.caption2)
                                .foregroundStyle(AppTheme.secondaryText)
                            Image(systemName: "chevron.right")
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .surface(12)
                }
            }
        }
    }

    private var managedAgents: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader("YOUR TEAM", "Managed agents", trailing: "")
            ForEach(overview.architecture.agents.prefix(4)) { agent in
                Button {
                    store.selectedAgentID = agent.id
                    store.section = .agents
                } label: {
                    HStack(spacing: 10) {
                        agentAvatar(agent)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(agent.name).font(.callout.weight(.semibold))
                            Text("\(agent.owner) · \(agent.mcpTools.count) tools")
                                .font(.caption)
                                .foregroundStyle(AppTheme.secondaryText)
                        }
                        Spacer()
                        StatusDot(status: agent.status)
                        Image(systemName: "chevron.right")
                            .font(.caption)
                            .foregroundStyle(AppTheme.secondaryText)
                    }
                }
                .buttonStyle(.plain)
                .padding(.vertical, 7)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .surface()
    }

    private var recentActivity: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader("WORKSPACE MEMORY", "Recent activity", trailing: "")
            if overview.recentConversations.isEmpty && overview.recentBuilds.isEmpty {
                ContentUnavailableView(
                    "No Activity Yet",
                    systemImage: "clock",
                    description: Text("Conversations and Manager runs appear here.")
                )
                .frame(height: 180)
            } else {
                ForEach(overview.recentConversations.prefix(4)) { conversation in
                    Button {
                        store.openWorkspace(
                            agentID: conversation.agentId,
                            mode: "test",
                            conversationID: conversation.id
                        )
                    } label: {
                        HStack {
                            Image(systemName: "bubble.left.and.bubble.right")
                                .foregroundStyle(AppTheme.accent)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(conversation.title)
                                    .font(.callout.weight(.medium))
                                    .lineLimit(1)
                                Text(conversation.updatedAt.shortTimestamp)
                                    .font(.caption)
                                    .foregroundStyle(AppTheme.secondaryText)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.caption)
                                .foregroundStyle(AppTheme.secondaryText)
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 7)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .surface()
    }

    private func sectionHeader(_ eyebrow: String, _ title: String, trailing: String) -> some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 3) {
                Text(eyebrow)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(AppTheme.accent)
                Text(title).font(.title3.weight(.semibold))
            }
            Spacer()
            Text(trailing)
                .font(.caption)
                .foregroundStyle(AppTheme.secondaryText)
        }
    }

    private func pulseRow(_ label: String, _ value: String, healthy: Bool) -> some View {
        HStack {
            StatusDot(status: healthy ? "healthy" : "degraded")
            Text(label)
            Spacer()
            Text(value).fontWeight(.semibold)
        }
        .font(.callout)
    }

    private func agentAvatar(_ agent: AgentRecord?) -> some View {
        RoundedRectangle(cornerRadius: 7)
            .fill(Color.white.opacity(0.08))
            .frame(width: 38, height: 38)
            .overlay(
                Text(String(agent?.name.first ?? "A"))
                    .font(.headline)
                    .foregroundStyle(AppTheme.accent)
            )
    }

    private func investigate(_ result: HealthResult) {
        let architecture = overview.architecture
        if result.kind == "agent",
           let agent = architecture.agents.first(where: { $0.id == result.id.components(separatedBy: "-").dropFirst().joined(separator: "-") }) {
            store.openWorkspace(agentID: agent.id, mode: "test")
            return
        }
        if let tool = architecture.tools.first(where: { $0.name == result.name || $0.id == result.name }),
           let agent = architecture.agents.first(where: { $0.toolIds.contains(tool.id) }) {
            store.openWorkspace(agentID: agent.id, mode: "test", tool: tool.name)
            return
        }
        store.section = .health
    }

    private func investigate(_ finding: ReconciliationFinding) {
        guard let agentID = finding.agentIds.first else {
            store.section = .health
            return
        }
        store.openWorkspace(
            agentID: agentID,
            mode: "test",
            tool: finding.toolNames.first
        )
    }
}
