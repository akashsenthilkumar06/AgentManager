import SwiftUI

struct ActivityView: View {
    @EnvironmentObject private var store: AppStore
    @State private var kind = "conversations"
    @State private var query = ""

    private var conversations: [AgentConversation] {
        (store.overview?.recentConversations ?? []).filter { conversation in
            guard !query.isEmpty else { return true }
            let agent = store.agents.first { $0.id == conversation.agentId }
            return "\(conversation.title) \(agent?.name ?? "")"
                .localizedCaseInsensitiveContains(query)
        }
    }

    private var builds: [BuildRecord] {
        (store.overview?.recentBuilds ?? []).filter { build in
            query.isEmpty || "\(build.prompt) \(build.tool?.name ?? "")"
                .localizedCaseInsensitiveContains(query)
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            controls
            ScrollView {
                LazyVStack(spacing: 8) {
                    if kind == "conversations" {
                        ForEach(conversations) { conversation in
                            conversationRow(conversation)
                        }
                        if conversations.isEmpty {
                            ContentUnavailableView.search(text: query)
                                .padding(.top, 100)
                        }
                    } else {
                        ForEach(builds) { build in
                            buildRow(build)
                        }
                        if builds.isEmpty {
                            ContentUnavailableView.search(text: query)
                                .padding(.top, 100)
                        }
                    }
                }
                .padding(20)
                .frame(maxWidth: 1000)
                .frame(maxWidth: .infinity)
            }
        }
    }

    private var header: some View {
        HStack(alignment: .bottom) {
            PageTitle(
                eyebrow: "WORKSPACE MEMORY",
                title: "Activity",
                detail: "Return to agent conversations and capability runs without digging through internals."
            )
            Spacer()
        }
        .padding(22)
        .background(AppTheme.surface)
    }

    private var controls: some View {
        HStack {
            Picker("Activity", selection: $kind) {
                Text("Agent Conversations (\(store.overview?.recentConversations.count ?? 0))")
                    .tag("conversations")
                Text("Capability Runs (\(store.overview?.recentBuilds.count ?? 0))")
                    .tag("builds")
            }
            .pickerStyle(.segmented)
            .frame(width: 390)
            Spacer()
            TextField(
                kind == "conversations" ? "Search conversations or agents" : "Search capabilities or requests",
                text: $query
            )
            .textFieldStyle(.roundedBorder)
            .frame(width: 320)
        }
        .padding(12)
        .background(AppTheme.sidebar)
    }

    private func conversationRow(_ conversation: AgentConversation) -> some View {
        let agent = store.agents.first { $0.id == conversation.agentId }
        let toolCalls = conversation.messages.flatMap(\.toolCalls)
        let verified = conversation.messages.filter { $0.verification?.status == "verified" }.count
        return Button {
            store.openWorkspace(
                agentID: conversation.agentId,
                mode: "test",
                conversationID: conversation.id
            )
        } label: {
            HStack(spacing: 13) {
                RoundedRectangle(cornerRadius: 7)
                    .fill(AppTheme.accent.opacity(0.12))
                    .frame(width: 42, height: 42)
                    .overlay(
                        Text(String(agent?.name.first ?? "A"))
                            .font(.headline)
                            .foregroundStyle(AppTheme.accent)
                    )
                VStack(alignment: .leading, spacing: 3) {
                    Text(agent?.name ?? conversation.agentId)
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                    Text(conversation.title).font(.headline)
                    Text("\(conversation.messages.count) messages · \(toolCalls.count) tool runs · \(verified) verified outputs")
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                }
                Spacer()
                Text(conversation.updatedAt.shortTimestamp)
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)
                Image(systemName: "chevron.right")
                    .foregroundStyle(AppTheme.secondaryText)
            }
            .padding(14)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .background(AppTheme.surface)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(AppTheme.border))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func buildRow(_ build: BuildRecord) -> some View {
        HStack(spacing: 13) {
            RoundedRectangle(cornerRadius: 7)
                .fill(Color.white.opacity(0.06))
                .frame(width: 42, height: 42)
                .overlay(Image(systemName: "hammer").foregroundStyle(AppTheme.accent))
            VStack(alignment: .leading, spacing: 3) {
                Text("Manager orchestration")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)
                Text(build.tool?.name ?? "Capability run")
                    .font(.headline.monospaced())
                Text(build.prompt)
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)
                    .lineLimit(2)
            }
            Spacer()
            StatusPill(status: build.status)
            Text(build.createdAt.shortTimestamp)
                .font(.caption)
                .foregroundStyle(AppTheme.secondaryText)
        }
        .padding(14)
        .background(AppTheme.surface)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(AppTheme.border))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
