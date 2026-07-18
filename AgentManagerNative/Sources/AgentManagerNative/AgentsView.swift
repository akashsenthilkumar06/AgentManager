import AppKit
import SwiftUI

struct AgentsView: View {
    @EnvironmentObject private var store: AppStore
    @State private var query = ""
    @State private var discovering = false
    @State private var showingImport = false
    @State private var detailAgentID: String?

    private var filtered: [AgentRecord] {
        store.agents.filter { agent in
            let searchable = (
                [agent.name, agent.owner, agent.description]
                + agent.features
                + agent.mcpTools.map(\.name)
            ).joined(separator: " ").lowercased()
            return query.isEmpty || searchable.contains(query.lowercased())
        }
    }

    var body: some View {
        Group {
            if let detailAgentID,
               let agent = store.agents.first(where: { $0.id == detailAgentID }) {
                agentDetailPage(agent)
            } else {
                directory
            }
        }
        .sheet(isPresented: $showingImport) {
            ImportAgentSheet()
                .environmentObject(store)
        }
    }

    private var directory: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                HStack(alignment: .center, spacing: 18) {
                    PageTitle(
                        eyebrow: "YOUR AGENT TEAM",
                        title: "Managed agents",
                        detail: "Each agent keeps its conversations, tools, source, runtime, and activity together."
                    )
                    Spacer()
                    Button {
                        showingImport = true
                    } label: {
                        Label("Add Agent", systemImage: "plus")
                    }
                    .buttonStyle(.borderedProminent)
                }

                HStack(spacing: 10) {
                    HStack(spacing: 8) {
                        Image(systemName: "magnifyingglass")
                            .foregroundStyle(AppTheme.secondaryText)
                        TextField("Search agents, tools, or capabilities", text: $query)
                            .textFieldStyle(.plain)
                    }
                    .padding(.horizontal, 12)
                    .frame(height: 38)
                    .background(AppTheme.surface)
                    .overlay(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .stroke(AppTheme.border)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))

                    Text("\(filtered.count) agent\(filtered.count == 1 ? "" : "s")")
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)

                    Menu {
                        Button {
                            Task { await discoverAll() }
                        } label: {
                            Label(
                                discovering ? "Syncing Capabilities…" : "Sync Capabilities",
                                systemImage: "arrow.triangle.2.circlepath"
                            )
                        }
                        .disabled(discovering)
                    } label: {
                        Image(systemName: "ellipsis")
                            .frame(width: 30, height: 30)
                    }
                    .menuStyle(.borderlessButton)
                }

                LazyVGrid(
                    columns: [
                        GridItem(.adaptive(minimum: 285, maximum: 430), spacing: 14)
                    ],
                    alignment: .leading,
                    spacing: 14
                ) {
                    ForEach(filtered) { agent in
                        Button {
                            open(agent)
                        } label: {
                            VStack(alignment: .leading, spacing: 14) {
                                HStack(spacing: 10) {
                                    RoundedRectangle(cornerRadius: 10)
                                        .fill(Color.white.opacity(0.075))
                                        .frame(width: 42, height: 42)
                                        .overlay(
                                            Text(String(agent.name.first ?? "A"))
                                                .font(.headline)
                                                .foregroundStyle(.white.opacity(0.9))
                                        )
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(agent.name)
                                            .font(.headline)
                                        Text(agent.owner)
                                            .font(.caption)
                                            .foregroundStyle(AppTheme.secondaryText)
                                    }
                                    Spacer()
                                    StatusPill(status: agent.status)
                                }
                                Text(agent.description)
                                    .font(.callout)
                                    .foregroundStyle(AppTheme.secondaryText)
                                    .lineLimit(3)
                                    .frame(minHeight: 50, alignment: .topLeading)
                                HStack(spacing: 14) {
                                    Text("\(agent.mcpTools.count) tools")
                                    Text("\(agent.features.count) capabilities")
                                    Spacer()
                                    Image(systemName: "chevron.right")
                                }
                                .font(.caption)
                                .foregroundStyle(AppTheme.secondaryText)
                            }
                            .padding(18)
                            .frame(maxWidth: .infinity, minHeight: 190, alignment: .topLeading)
                            .background(AppTheme.surface)
                            .overlay(
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .stroke(AppTheme.border)
                            )
                            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }

                if filtered.isEmpty {
                    ContentUnavailableView.search(text: query)
                        .frame(maxWidth: .infinity, minHeight: 260)
                }
            }
            .padding(28)
            .frame(maxWidth: 1180)
            .frame(maxWidth: .infinity)
        }
        .background(AppTheme.background)
    }

    private func agentDetailPage(_ agent: AgentRecord) -> some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Button {
                    detailAgentID = nil
                } label: {
                    Label("Managed agents", systemImage: "chevron.left")
                }
                .buttonStyle(.plain)
                .foregroundStyle(AppTheme.secondaryText)
                Spacer()
            }
            .padding(.horizontal, 22)
            .padding(.vertical, 13)
            .background(AppTheme.surface)
            .overlay(alignment: .bottom) { Divider() }

            AgentDetailView(agent: agent)
                .id(agent.id)
        }
    }

    private func open(_ agent: AgentRecord) {
        store.selectedAgentID = agent.id
        detailAgentID = agent.id
    }

    private func discoverAll() async {
        guard let api = store.api else { return }
        discovering = true
        do {
            let result: DiscoverAllResponse = try await api.post("/api/managed-agents/discover")
            try await store.refresh()
            store.show("Updated \(result.toolCount) tools across \(result.agents.count) agents.")
        } catch {
            store.show(error.localizedDescription, error: true)
        }
        discovering = false
    }
}

struct ImportAgentSheet: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss

    @State private var path = ""
    @State private var name = ""
    @State private var command = ""
    @State private var endpoint = ""
    @State private var startAfterImport = false
    @State private var importing = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("CONNECT LOCAL AGENT")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(AppTheme.accent)
                    Text("Import an agent directory")
                        .font(.title2.weight(.semibold))
                    Text("Index safe source files, detect launch commands, and make the project available as scoped Manager context.")
                        .foregroundStyle(AppTheme.secondaryText)
                }
                Spacer()
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark")
                }
                .buttonStyle(.plain)
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Agent directory").font(.caption.weight(.medium))
                HStack {
                    TextField("/Users/you/projects/my-agent", text: $path)
                        .textFieldStyle(.roundedBorder)
                        .font(.body.monospaced())
                    Button("Choose…") { chooseDirectory() }
                        .buttonStyle(.bordered)
                }
                Text("Secrets, environments, dependencies, builds, and Git internals stay excluded.")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)
            }

            HStack(spacing: 12) {
                field("Display name", placeholder: "Detected from folder", text: $name)
                field("MCP endpoint", placeholder: "Optional · http://…/mcp", text: $endpoint)
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Run command").font(.caption.weight(.medium))
                TextField("Optional · make dev or python app.py", text: $command)
                    .textFieldStyle(.roundedBorder)
                    .font(.body.monospaced())
                Text("Leave blank to use the first command detected from the project.")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)
            }

            Toggle(isOn: $startAfterImport) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Start after import").font(.callout.weight(.medium))
                    Text("Run only the selected command directly in this directory.")
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                }
            }
            .toggleStyle(.switch)

            HStack {
                Label("Read-only source scope", systemImage: "lock.shield")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)
                Spacer()
                Button("Cancel") { dismiss() }
                    .buttonStyle(.bordered)
                Button {
                    Task { await importAgent() }
                } label: {
                    Label(importing ? "Indexing…" : "Add Managed Agent", systemImage: "plus")
                }
                .buttonStyle(.borderedProminent)
                .disabled(importing || path.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(24)
        .frame(width: 680)
        .background(AppTheme.background)
    }

    private func field(
        _ label: String,
        placeholder: String,
        text: Binding<String>
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(.caption.weight(.medium))
            TextField(placeholder, text: text)
                .textFieldStyle(.roundedBorder)
        }
        .frame(maxWidth: .infinity)
    }

    private func chooseDirectory() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Import Agent"
        if panel.runModal() == .OK, let url = panel.url {
            path = url.path
            if name.isEmpty {
                name = url.lastPathComponent
                    .replacingOccurrences(of: "-", with: " ")
                    .capitalized
            }
        }
    }

    private func importAgent() async {
        guard let api = store.api else { return }
        importing = true
        do {
            let response: AgentImportResponse = try await api.post(
                "/api/managed-agents/import",
                body: AgentImportRequest(
                    path: path,
                    name: name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : name,
                    description: nil,
                    owner: "Local workspace",
                    runCommand: command.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : command,
                    mcpEndpoint: endpoint.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : endpoint,
                    startAfterImport: startAfterImport
                )
            )
            try await store.refresh()
            store.selectedAgentID = response.agent.id
            store.show(
                response.alreadyImported
                ? "That directory is already managed."
                : "Imported \(response.agent.name) with \(response.profile.indexedFiles) indexed files."
            )
            dismiss()
        } catch {
            store.show(error.localizedDescription, error: true)
        }
        importing = false
    }
}

struct AgentDetailView: View {
    @EnvironmentObject private var store: AppStore
    let agent: AgentRecord

    @State private var tab = "overview"
    @State private var conversations: [AgentConversation] = []
    @State private var selectedTool: String?

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header
                    Picker("Section", selection: $tab) {
                        Text("Overview").tag("overview")
                        Text("Conversations").tag("conversations")
                        Text("Tool Workspaces").tag("tools")
                    }
                    .pickerStyle(.segmented)
                    .frame(maxWidth: 470)

                    switch tab {
                    case "conversations":
                        conversationsView
                    case "tools":
                        toolsView
                    default:
                        overviewView
                    }
                }
                .padding(24)
                .frame(maxWidth: 1050)
                .frame(maxWidth: .infinity)
            }
        }
        .task { await loadConversations() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 15) {
            HStack(alignment: .top, spacing: 14) {
                RoundedRectangle(cornerRadius: 10)
                    .fill(AppTheme.accent.opacity(0.14))
                    .frame(width: 58, height: 58)
                    .overlay(
                        Text(String(agent.name.first ?? "A"))
                            .font(.title.weight(.bold))
                            .foregroundStyle(AppTheme.accent)
                    )
                VStack(alignment: .leading, spacing: 4) {
                    Text("MANAGED AGENT / WORKSPACE")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(AppTheme.accent)
                    Text(agent.name).font(.title.weight(.semibold))
                    Text(agent.description)
                        .foregroundStyle(AppTheme.secondaryText)
                }
                Spacer()
                HStack {
                    Button {
                        store.selectedAgentID = agent.id
                        store.section = .benchmarks
                    } label: {
                        Label("Benchmark", systemImage: "chart.bar.xaxis")
                    }
                    .buttonStyle(.bordered)
                    Button {
                        store.openWorkspace(agentID: agent.id)
                    } label: {
                        Label("Edit in Workspace", systemImage: "arrow.up.right")
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            HStack(spacing: 18) {
                StatusPill(status: agent.status)
                Label(agent.owner, systemImage: "person")
                Label("\(agent.mcpTools.count) tools", systemImage: "wrench.and.screwdriver")
                Label("\(conversations.count) conversations", systemImage: "bubble.left.and.bubble.right")
                if agent.imported {
                    Label("Local directory", systemImage: "folder.badge.gearshape")
                }
            }
            .font(.caption)
            .foregroundStyle(AppTheme.secondaryText)
        }
    }

    private var overviewView: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 14) {
                VStack(alignment: .leading, spacing: 10) {
                    Text("AGENT CONTEXT")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(AppTheme.accent)
                    Text("What it knows").font(.title3.weight(.semibold))
                    Text(agent.description).foregroundStyle(AppTheme.secondaryText)
                    FlowLayout(spacing: 7) {
                        ForEach(agent.features, id: \.self) { feature in
                            Text(feature)
                                .font(.caption)
                                .padding(.horizontal, 9)
                                .padding(.vertical, 6)
                                .background(Color.white.opacity(0.055))
                                .clipShape(Capsule())
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .surface()

                VStack(alignment: .leading, spacing: 10) {
                    Text("CONFIGURE IT")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(AppTheme.accent)
                    Text("Edit this agent").font(.title3.weight(.semibold))
                    Text("Use the Manager to change instructions and behavior with a reviewable, validated diff.")
                        .foregroundStyle(AppTheme.secondaryText)
                    Button("Open Agent Editor") {
                        store.openWorkspace(agentID: agent.id)
                    }
                    .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .surface()
            }

            AgentModelSettingsView(agent: agent)
            MCPConnectionView(agent: agent)

            if agent.imported {
                ImportedRuntimeView(agent: agent)
            }
        }
    }

    private var conversationsView: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Conversation history").font(.title3.weight(.semibold))
                    Text("Every test chat stays scoped to this agent.")
                        .foregroundStyle(AppTheme.secondaryText)
                }
                Spacer()
                Button("New Test") {
                    store.openWorkspace(agentID: agent.id, mode: "test")
                }
                .buttonStyle(.borderedProminent)
            }
            Divider()
            if conversations.isEmpty {
                ContentUnavailableView(
                    "No Conversations",
                    systemImage: "bubble.left.and.bubble.right",
                    description: Text("Open Test Client to start one.")
                )
                .frame(minHeight: 260)
            } else {
                ForEach(conversations) { conversation in
                    Button {
                        store.openWorkspace(
                            agentID: agent.id,
                            mode: "test",
                            conversationID: conversation.id
                        )
                    } label: {
                        HStack {
                            Image(systemName: "bubble.left")
                                .foregroundStyle(AppTheme.accent)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(conversation.title).font(.callout.weight(.semibold))
                                Text("\(conversation.messages.count) messages · \(conversation.updatedAt.shortTimestamp)")
                                    .font(.caption)
                                    .foregroundStyle(AppTheme.secondaryText)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                        }
                        .padding(11)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .background(Color.white.opacity(0.035))
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                }
            }
        }
        .surface()
    }

    private var toolsView: some View {
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 5) {
                Text("AGENT TOOLS")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(AppTheme.secondaryText)
                    .padding(10)
                ForEach(agent.mcpTools) { tool in
                    Button {
                        selectedTool = tool.name
                    } label: {
                        HStack {
                            Image(systemName: "wrench.and.screwdriver")
                            VStack(alignment: .leading) {
                                Text(tool.name).font(.callout.monospaced())
                                Text("\(toolRuns(tool.name).count) runs")
                                    .font(.caption2)
                                    .foregroundStyle(AppTheme.secondaryText)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                        }
                        .padding(10)
                        .background(selectedTool == tool.name ? Color.white.opacity(0.08) : .clear)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                    .buttonStyle(.plain)
                }
                Spacer()
            }
            .frame(width: 235)

            Divider()
            if let tool = agent.mcpTools.first(where: { $0.name == selectedTool }) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("TOOL WORKSPACE")
                                    .font(.caption2.weight(.semibold))
                                    .foregroundStyle(AppTheme.accent)
                                Text(tool.name).font(.title2.monospaced().weight(.semibold))
                                Text(tool.description).foregroundStyle(AppTheme.secondaryText)
                            }
                            Spacer()
                            Button("Test This Tool") {
                                store.openWorkspace(agentID: agent.id, mode: "test", tool: tool.name)
                            }
                            .buttonStyle(.borderedProminent)
                        }

                        Text("INPUT CONTRACT")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(AppTheme.secondaryText)
                        Text(JSONValue.object(tool.inputSchema).prettyPrinted)
                            .font(.caption.monospaced())
                            .textSelection(.enabled)
                            .padding(12)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.black.opacity(0.22))
                            .clipShape(RoundedRectangle(cornerRadius: 6))

                        Text("RUN HISTORY")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(AppTheme.secondaryText)
                        if toolRuns(tool.name).isEmpty {
                            Text("This tool has not been used in a conversation yet.")
                                .foregroundStyle(AppTheme.secondaryText)
                        } else {
                            ForEach(toolRuns(tool.name), id: \.call.id) { item in
                                HStack {
                                    StatusDot(status: item.call.status)
                                    VStack(alignment: .leading) {
                                        Text("\(item.call.status.capitalized) · \(item.call.durationMs) ms")
                                            .font(.callout.weight(.medium))
                                        Text(item.conversation.title)
                                            .font(.caption)
                                            .foregroundStyle(AppTheme.secondaryText)
                                    }
                                    Spacer()
                                    Text(item.conversation.updatedAt.shortTimestamp)
                                        .font(.caption)
                                        .foregroundStyle(AppTheme.secondaryText)
                                }
                                .padding(9)
                                .background(Color.white.opacity(0.035))
                                .clipShape(RoundedRectangle(cornerRadius: 6))
                            }
                        }
                    }
                    .padding(18)
                }
            } else {
                ContentUnavailableView(
                    "Select a Tool Workspace",
                    systemImage: "wrench.and.screwdriver",
                    description: Text("Inspect its contract, test it in context, and review previous runs.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .frame(minHeight: 520)
        .surface(0)
    }

    private func loadConversations() async {
        guard let api = store.api else { return }
        do {
            conversations = try await api.get(
                "/api/conversations",
                query: [URLQueryItem(name: "agent_id", value: agent.id)]
            )
        } catch {
            store.show(error.localizedDescription, error: true)
        }
    }

    private func toolRuns(_ name: String) -> [(call: ToolCallRecord, conversation: AgentConversation)] {
        conversations.flatMap { conversation in
            conversation.messages.flatMap { message in
                message.toolCalls
                    .filter { $0.toolName == name }
                    .map { ($0, conversation) }
            }
        }
    }
}

struct ImportedRuntimeView: View {
    @EnvironmentObject private var store: AppStore
    let agent: AgentRecord

    @State private var runtime: AgentProcessStatus?
    @State private var command = ""
    @State private var working = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("CONNECTED LOCAL RUNTIME")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(AppTheme.accent)
                    Text("Source and process").font(.title3.weight(.semibold))
                    Text("The Manager reads this directory as scoped context. Only the command shown below is executed.")
                        .foregroundStyle(AppTheme.secondaryText)
                }
                Spacer()
                StatusPill(status: runtime?.status ?? "stopped")
            }

            Label(agent.workspaceRoot ?? "Connected directory", systemImage: "folder")
                .font(.callout.monospaced())
                .textSelection(.enabled)
                .padding(11)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.white.opacity(0.035))
                .clipShape(RoundedRectangle(cornerRadius: 8))

            if !agent.detectedEntrypoints.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    Text("DETECTED COMMANDS")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(AppTheme.secondaryText)
                    FlowLayout(spacing: 7) {
                        ForEach(agent.detectedEntrypoints, id: \.self) { entrypoint in
                            Button(entrypoint) { command = entrypoint }
                                .buttonStyle(.bordered)
                                .tint(command == entrypoint ? AppTheme.accent : nil)
                        }
                    }
                }
            }

            HStack(alignment: .bottom, spacing: 10) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Run command").font(.caption)
                    TextField("make dev", text: $command)
                        .textFieldStyle(.roundedBorder)
                        .font(.body.monospaced())
                }
                if runtime?.status == "running" {
                    Button(working ? "Stopping…" : "Stop Agent") {
                        Task { await stop() }
                    }
                    .buttonStyle(.bordered)
                    .tint(AppTheme.danger)
                    .disabled(working)
                } else {
                    Button(working ? "Starting…" : "Start Agent") {
                        Task { await start() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(
                        working
                        || command.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    )
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("RUNTIME OUTPUT")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(AppTheme.secondaryText)
                    Spacer()
                    Text(runtime?.pid.map { "PID \($0)" }
                         ?? runtime?.exitCode.map { "Exited \($0)" }
                         ?? "Not running")
                        .font(.caption.monospaced())
                        .foregroundStyle(AppTheme.secondaryText)
                }
                ScrollView([.vertical, .horizontal]) {
                    Text(runtime?.logs.joined(separator: "\n")
                         ?? "Process output appears here after the agent starts.")
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .topLeading)
                }
                .frame(minHeight: 90, maxHeight: 180)
                .padding(10)
                .background(Color.black.opacity(0.22))
                .clipShape(RoundedRectangle(cornerRadius: 7))
            }
        }
        .surface()
        .task {
            command = agent.runCommand ?? agent.detectedEntrypoints.first ?? ""
            await load()
        }
        .task(id: runtime?.status) {
            guard runtime?.status == "running" else { return }
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1.8))
                await load(showErrors: false)
                if runtime?.status != "running" { return }
            }
        }
    }

    private func load(showErrors: Bool = true) async {
        guard let api = store.api else { return }
        do {
            runtime = try await api.get(
                "/api/managed-agents/\(agent.id)/process"
            )
        } catch where showErrors {
            store.show(error.localizedDescription, error: true)
        } catch {}
    }

    private func start() async {
        guard let api = store.api else { return }
        working = true
        do {
            runtime = try await api.post(
                "/api/managed-agents/\(agent.id)/process/start",
                body: AgentProcessStartRequest(command: command)
            )
            try await store.refresh()
            store.show("\(agent.name) started.")
        } catch {
            store.show(error.localizedDescription, error: true)
        }
        working = false
    }

    private func stop() async {
        guard let api = store.api else { return }
        working = true
        do {
            runtime = try await api.post(
                "/api/managed-agents/\(agent.id)/process/stop"
            )
            store.show("\(agent.name) stopped.")
        } catch {
            store.show(error.localizedDescription, error: true)
        }
        working = false
    }
}

struct AgentModelSettingsView: View {
    @EnvironmentObject private var store: AppStore
    let agent: AgentRecord

    @State private var model = ""
    @State private var reasoning = ""
    @State private var saving = false

    private var provider: OpenAIStatus? { store.overview?.openai }
    private var options: [OpenAIModelOption] { provider?.modelOptions ?? [] }
    private var effectiveModel: String {
        model.isEmpty ? (provider?.model ?? "application default") : model
    }
    private var selectedOption: OpenAIModelOption? {
        options.first { $0.id == effectiveModel }
    }
    private var reasoningOptions: [String] {
        selectedOption?.reasoningEfforts
            ?? ["none", "low", "medium", "high", "xhigh", "max"]
    }
    private var effectiveReasoning: String {
        reasoning.isEmpty ? (provider?.reasoningEffort ?? "provider default") : reasoning
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 15) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("LIVE REASONING")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(AppTheme.accent)
                    Text("OpenAI model").font(.title3.weight(.semibold))
                    Text("Choose the model and reasoning effort used when Manager or Test mode performs OpenAI-backed work for this agent.")
                        .foregroundStyle(AppTheme.secondaryText)
                }
                Spacer()
                VStack(alignment: .leading, spacing: 3) {
                    Text("EFFECTIVE MODEL")
                        .font(.caption2)
                        .foregroundStyle(AppTheme.secondaryText)
                    Text(effectiveModel)
                        .font(.caption.monospaced().weight(.semibold))
                }
                .padding(10)
                .background(Color.white.opacity(0.045))
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }

            HStack(alignment: .bottom, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Model").font(.caption.weight(.medium))
                    Picker("Model", selection: $model) {
                        Text("Inherit app default (\(provider?.model ?? "configured model"))")
                            .tag("")
                        ForEach(options) { option in
                            Text("\(option.label) · \(option.role)").tag(option.id)
                        }
                    }
                    .labelsHidden()
                    Text(selectedOption?.description ?? "Uses the model configured by OPENAI_MODEL.")
                        .font(.caption2)
                        .foregroundStyle(AppTheme.secondaryText)
                        .lineLimit(2)
                }
                .frame(maxWidth: .infinity)

                VStack(alignment: .leading, spacing: 6) {
                    Text("Reasoning effort").font(.caption.weight(.medium))
                    Picker("Reasoning effort", selection: $reasoning) {
                        Text("Inherit app default (\(provider?.reasoningEffort ?? "provider default"))")
                            .tag("")
                        ForEach(reasoningOptions, id: \.self) { effort in
                            Text(effort.capitalized).tag(effort)
                        }
                    }
                    .labelsHidden()
                    Text("Higher effort can improve difficult work, with more latency and token usage.")
                        .font(.caption2)
                        .foregroundStyle(AppTheme.secondaryText)
                        .lineLimit(2)
                }
                .frame(maxWidth: .infinity)

                Button(saving ? "Saving…" : "Save Model") {
                    Task { await save() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(saving)
            }

            Label(
                "OpenAI-backed runs use \(effectiveModel) with \(effectiveReasoning) reasoning and record the provider in their evidence.",
                systemImage: "sparkles"
            )
            .font(.caption)
            .foregroundStyle(AppTheme.secondaryText)
        }
        .liquidGlass(cornerRadius: 16, interactive: true)
        .onAppear {
            model = agent.openaiModel ?? ""
            reasoning = agent.openaiReasoningEffort ?? ""
        }
        .onChange(of: model) {
            if !reasoning.isEmpty, !reasoningOptions.contains(reasoning) {
                reasoning = ""
            }
        }
    }

    private func save() async {
        guard let api = store.api else { return }
        saving = true
        do {
            let request = updateRequest(
                agent,
                endpoint: agent.mcpEndpoint,
                model: model.isEmpty ? nil : model,
                reasoning: reasoning.isEmpty ? nil : reasoning
            )
            let _: AgentRecord = try await api.patch(
                "/api/managed-agents/\(agent.id)",
                body: request
            )
            try await store.refresh()
            store.show("Model settings saved for \(agent.name).")
        } catch {
            store.show(error.localizedDescription, error: true)
        }
        saving = false
    }
}

struct MCPConnectionView: View {
    @EnvironmentObject private var store: AppStore
    let agent: AgentRecord

    @State private var endpoint = ""
    @State private var saving = false
    @State private var testing = false
    @State private var result: String?
    @State private var resultStatus = ""

    private var displayedAgent: AgentRecord {
        store.agents.first { $0.id == agent.id } ?? agent
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 15) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("LIVE AGENT CONNECTION")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(AppTheme.accent)
                    Text("MCP endpoint").font(.title3.weight(.semibold))
                    Text("Connect this managed agent to a demo://, http://, or https:// MCP server.")
                        .foregroundStyle(AppTheme.secondaryText)
                }
                Spacer()
                StatusPill(status: displayedAgent.status)
            }

            HStack(alignment: .bottom, spacing: 10) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Endpoint URL").font(.caption)
                    TextField("http://127.0.0.1:8100/mcp", text: $endpoint)
                        .textFieldStyle(.roundedBorder)
                        .font(.body.monospaced())
                }
                Button(saving ? "Saving…" : "Save Endpoint") {
                    Task { await saveEndpoint(showNotice: true) }
                }
                .buttonStyle(.bordered)
                .disabled(saving || testing)
                Button(testing ? "Connecting…" : "Test & Discover") {
                    Task { await testConnection() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(saving || testing || endpoint.trimmingCharacters(in: .whitespaces).isEmpty)
            }

            Label(
                "HTTP(S) endpoints use Live MCP when an OpenAI API key is configured. Fallbacks remain clearly labeled.",
                systemImage: "info.circle"
            )
            .font(.caption)
            .foregroundStyle(AppTheme.secondaryText)

            HStack {
                Image(systemName: resultStatus == "failed" ? "exclamationmark.triangle" : "point.3.connected.trianglepath.dotted")
                    .foregroundStyle(resultStatus == "failed" ? AppTheme.danger : AppTheme.accent)
                VStack(alignment: .leading, spacing: 2) {
                    Text(result ?? displayedAgent.mcpServerName ?? "Not discovered yet")
                        .font(.callout.weight(.semibold))
                    Text(displayedAgent.lastDiscoveredAt?.shortTimestamp ?? "Test the endpoint to load advertised tools.")
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                }
                Spacer()
                Text("\(displayedAgent.mcpTools.count) tools")
                    .font(.callout.weight(.semibold))
            }
            .padding(12)
            .background(Color.black.opacity(0.16))
            .clipShape(RoundedRectangle(cornerRadius: 7))

            ForEach(displayedAgent.mcpTools) { tool in
                HStack {
                    Image(systemName: "wrench.and.screwdriver")
                        .foregroundStyle(AppTheme.accent)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(tool.name).font(.callout.monospaced().weight(.medium))
                        Text(tool.description)
                            .font(.caption)
                            .foregroundStyle(AppTheme.secondaryText)
                    }
                    Spacer()
                    Text("\(inputCount(tool)) inputs")
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                }
                .padding(.vertical, 5)
            }
        }
        .surface()
        .onAppear { endpoint = agent.mcpEndpoint ?? "" }
    }

    private func inputCount(_ tool: MCPToolCapability) -> Int {
        if case .object(let properties) = tool.inputSchema["properties"] {
            return properties.count
        }
        return 0
    }

    @discardableResult
    private func saveEndpoint(showNotice: Bool) async -> Bool {
        guard let api = store.api else { return false }
        saving = true
        do {
            let request = updateRequest(
                agent,
                endpoint: endpoint.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    ? nil
                    : endpoint,
                model: agent.openaiModel,
                reasoning: agent.openaiReasoningEffort
            )
            let updated: AgentRecord = try await api.patch(
                "/api/managed-agents/\(agent.id)",
                body: request
            )
            endpoint = updated.mcpEndpoint ?? ""
            try await store.refresh()
            if showNotice { store.show("MCP endpoint saved.") }
            saving = false
            return true
        } catch {
            resultStatus = "failed"
            result = error.localizedDescription
            store.show(error.localizedDescription, error: true)
            saving = false
            return false
        }
    }

    private func testConnection() async {
        guard let api = store.api else { return }
        testing = true
        result = nil
        resultStatus = ""
        let saved = await saveEndpoint(showNotice: false)
        guard saved else {
            testing = false
            return
        }
        do {
            let discovered: AgentRecord = try await api.post(
                "/api/managed-agents/\(agent.id)/discover"
            )
            endpoint = discovered.mcpEndpoint ?? ""
            result = "Connected to \(discovered.mcpServerName ?? "MCP server")."
            resultStatus = "passed"
            try await store.refresh()
            store.show("Discovered \(discovered.mcpTools.count) live MCP tools.")
        } catch {
            resultStatus = "failed"
            result = error.localizedDescription
            store.show(error.localizedDescription, error: true)
        }
        testing = false
    }
}

private func updateRequest(
    _ agent: AgentRecord,
    endpoint: String?,
    model: String?,
    reasoning: String?
) -> AgentUpdateRequest {
    AgentUpdateRequest(
        name: agent.name,
        description: agent.description,
        owner: agent.owner,
        mcpEndpoint: endpoint,
        instructions: agent.instructions,
        features: agent.features,
        responseStyle: agent.responseStyle,
        toolPolicy: agent.toolPolicy,
        enabledTools: agent.enabledTools,
        verificationMode: agent.verificationMode,
        memoryEnabled: agent.memoryEnabled,
        openaiModel: model,
        openaiReasoningEffort: reasoning
    )
}

struct FlowLayout: Layout {
    let spacing: CGFloat

    func sizeThatFits(
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0
        var y: CGFloat = 0
        var lineHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > width, x > 0 {
                x = 0
                y += lineHeight + spacing
                lineHeight = 0
            }
            x += size.width + spacing
            lineHeight = max(lineHeight, size.height)
        }
        return CGSize(width: width.isFinite ? width : x, height: y + lineHeight)
    }

    func placeSubviews(
        in bounds: CGRect,
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) {
        var x = bounds.minX
        var y = bounds.minY
        var lineHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX, x > bounds.minX {
                x = bounds.minX
                y += lineHeight + spacing
                lineHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: .unspecified)
            x += size.width + spacing
            lineHeight = max(lineHeight, size.height)
        }
    }
}
