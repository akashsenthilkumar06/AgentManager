import SwiftUI

struct WorkspaceView: View {
    @EnvironmentObject private var store: AppStore
    @State private var showingAgentPicker = false

    var body: some View {
        VStack(spacing: 0) {
            header
            if let agent = store.selectedAgent {
                if store.workspaceMode == "edit" {
                    ManagerWorkspaceView(agent: agent)
                        .id(agent.id)
                } else {
                    TestWorkspaceView(
                        agent: agent,
                        requestedConversationID: store.requestedConversationID,
                        requestedTool: store.workspaceTool
                    )
                    .id("\(agent.id)-\(store.requestedConversationID ?? "")-\(store.workspaceTool ?? "")")
                }
            }
        }
    }

    private var header: some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Agent Studio")
                    .font(.headline)
                Text(store.workspaceMode == "edit" ? "Build with your Manager" : "Test the client agent")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)
            }
            .frame(minWidth: 170, alignment: .leading)

            Divider().frame(height: 32)
            agentSwitcher
            modeSwitcher
            Spacer()
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 10)
        .background(AppTheme.surface)
        .overlay(alignment: .bottom) { Divider() }
    }

    private var agentSwitcher: some View {
        Button {
            showingAgentPicker.toggle()
        } label: {
            HStack(spacing: 10) {
                Circle()
                    .fill(AppTheme.accent.opacity(0.15))
                    .frame(width: 32, height: 32)
                    .overlay(
                        Text(String(store.selectedAgent?.name.prefix(1) ?? "A"))
                            .font(.caption.weight(.bold))
                            .foregroundStyle(AppTheme.accent)
                    )
                VStack(alignment: .leading, spacing: 1) {
                    Text("CLIENT AGENT")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(AppTheme.secondaryText)
                    Text(store.selectedAgent?.name ?? "Select an agent")
                        .font(.callout.weight(.semibold))
                        .lineLimit(1)
                }
                Spacer(minLength: 8)
                StatusDot(status: store.selectedAgent?.status ?? "offline")
                Image(systemName: "chevron.up.chevron.down")
                    .font(.caption2)
                    .foregroundStyle(AppTheme.secondaryText)
            }
            .padding(.horizontal, 11)
            .padding(.vertical, 7)
            .frame(width: 265)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .liquidGlass(cornerRadius: 13, interactive: true)
        .help("Switch client agent")
        .popover(isPresented: $showingAgentPicker, arrowEdge: .top) {
            agentPickerPopover
        }
    }

    private var agentPickerPopover: some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Switch client agent")
                    .font(.headline)
                Text("\(store.agents.count) agents available")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)
            }
            .padding(.horizontal, 4)
            .padding(.bottom, 3)

            ForEach(store.agents) { agent in
                Button {
                    store.selectedAgentID = agent.id
                    store.requestedConversationID = nil
                    store.workspaceTool = nil
                    showingAgentPicker = false
                } label: {
                    HStack(spacing: 11) {
                        Circle()
                            .fill(AppTheme.accent.opacity(0.14))
                            .frame(width: 34, height: 34)
                            .overlay(
                                Text(String(agent.name.prefix(1)))
                                    .font(.caption.weight(.bold))
                                    .foregroundStyle(AppTheme.accent)
                            )
                        VStack(alignment: .leading, spacing: 2) {
                            Text(agent.name)
                                .font(.callout.weight(.semibold))
                            Text(agent.description)
                                .font(.caption2)
                                .foregroundStyle(AppTheme.secondaryText)
                                .lineLimit(1)
                        }
                        Spacer()
                        StatusDot(status: agent.status)
                        if store.selectedAgentID == agent.id {
                            Image(systemName: "checkmark")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(AppTheme.accent)
                        }
                    }
                    .padding(9)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .background(
                    store.selectedAgentID == agent.id
                        ? AppTheme.accent.opacity(0.1)
                        : Color.clear
                )
                .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            }
        }
        .padding(12)
        .frame(width: 350)
    }

    private var modeSwitcher: some View {
        HStack(spacing: 4) {
            modeButton("Manager", symbol: "wand.and.stars", mode: "edit")
            modeButton("Test", symbol: "play.fill", mode: "test")
        }
        .padding(4)
        .liquidGlass(cornerRadius: 13, interactive: true)
    }

    private func modeButton(
        _ title: String,
        symbol: String,
        mode: String
    ) -> some View {
        Button {
            withAnimation(.easeInOut(duration: 0.16)) {
                store.workspaceMode = mode
            }
        } label: {
            Label(title, systemImage: symbol)
                .font(.callout.weight(.semibold))
                .padding(.horizontal, 12)
                .padding(.vertical, 7)
                .background(
                    store.workspaceMode == mode
                        ? AppTheme.accent.opacity(0.88)
                        : Color.clear
                )
                .foregroundStyle(
                    store.workspaceMode == mode
                        ? Color.black.opacity(0.82)
                        : Color.primary
                )
                .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

struct ManagerWorkspaceView: View {
    @EnvironmentObject private var store: AppStore
    let agent: AgentRecord

    @State private var conversations: [ManagerConversation] = []
    @State private var conversation: ManagerConversation?
    @State private var prompt = ""
    @State private var autonomy = "review"
    @State private var working = false
    @State private var applying = false
    @State private var historyPanel = false
    @State private var livePanel = false

    private let starters = [
        "Review this agent's architecture and suggest the most important improvement.",
        "Make this agent verify its answer against tool evidence before responding.",
        "Check whether this agent is running and discover the tools it exposes.",
        "Should we redesign how this agent uses its current tool?"
    ]

    var body: some View {
        HStack(spacing: 0) {
            if historyPanel {
                historyRail
                    .frame(width: 238)
                    .transition(.move(edge: .leading).combined(with: .opacity))
                Divider()
            }
            chat
                .frame(minWidth: 480)
            if livePanel {
                Divider()
                liveWork
                    .frame(width: 326)
                    .transition(.move(edge: .trailing).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.2), value: historyPanel)
        .animation(.easeInOut(duration: 0.2), value: livePanel)
        .task { await load() }
    }

    private var historyRail: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Button {
                    conversation = nil
                } label: {
                    Label("New Task", systemImage: "square.and.pencil")
                }
                .buttonStyle(.borderedProminent)
                Spacer()
                Button {
                    withAnimation { historyPanel = false }
                } label: {
                    Image(systemName: "xmark")
                }
                .buttonStyle(.plain)
            }
            .padding([.horizontal, .top], 12)

            Text("MANAGER CONVERSATIONS")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(AppTheme.secondaryText)
                .padding(.horizontal, 13)
                .padding(.top, 8)

            ScrollView {
                LazyVStack(spacing: 4) {
                    ForEach(conversations) { item in
                        Button {
                            conversation = item
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(item.title)
                                    .font(.callout.weight(.medium))
                                    .lineLimit(2)
                                Text("\(item.messages.count) messages · \(item.autonomy)")
                                    .font(.caption2)
                                    .foregroundStyle(AppTheme.secondaryText)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(10)
                            .background(
                                conversation?.id == item.id
                                ? Color.white.opacity(0.08)
                                : .clear
                            )
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 7)
            }
        }
        .background(AppTheme.sidebar)
    }

    private var chat: some View {
        VStack(spacing: 0) {
            HStack {
                Button {
                    withAnimation(.easeInOut(duration: 0.18)) {
                        historyPanel.toggle()
                    }
                } label: {
                    Image(systemName: "clock.arrow.circlepath")
                }
                .buttonStyle(.plain)
                .help("Conversation history")
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 7) {
                        StatusDot(status: "healthy")
                        Text("Manager Agent").font(.headline)
                    }
                    Text(
                        "Working on \(agent.name) · "
                        + "\(agent.openaiModel ?? store.overview?.openai.model ?? "app default") / "
                        + "\(agent.openaiReasoningEffort ?? store.overview?.openai.reasoningEffort ?? "provider default")"
                    )
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                }
                Spacer()
                Button {
                    withAnimation(.easeInOut(duration: 0.18)) { livePanel.toggle() }
                } label: {
                    Label(
                        livePanel ? "Hide Work" : "Live Work",
                        systemImage: "point.3.connected.trianglepath.dotted"
                    )
                }
                .buttonStyle(.borderless)
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 12)
            .background(AppTheme.surface)

            ScrollView {
                if let conversation {
                    LazyVStack(alignment: .leading, spacing: 18) {
                        ForEach(conversation.messages) { message in
                            ManagerMessageView(
                                message: message,
                                applying: applying,
                                onApply: applyChanges
                            )
                        }
                        if working {
                            HStack(spacing: 10) {
                                ProgressView().controlSize(.small)
                                Text("Manager is selecting tools and inspecting the agent…")
                                    .foregroundStyle(AppTheme.secondaryText)
                            }
                            .padding()
                        }
                    }
                    .padding(22)
                } else {
                    managerWelcome
                }
            }
            .defaultScrollAnchor(.bottom)

            composer
        }
        .background(AppTheme.background)
    }

    private var managerWelcome: some View {
        VStack(spacing: 14) {
            RoundedRectangle(cornerRadius: 12)
                .fill(AppTheme.accent.opacity(0.14))
                .frame(width: 52, height: 52)
                .overlay(
                    Image(systemName: "wand.and.stars")
                        .font(.title2)
                        .foregroundStyle(AppTheme.accent)
                )
            Text("YOUR AGENTIC MANAGER")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(AppTheme.accent)
            Text("What should the Manager do with \(agent.name)?")
                .font(.title.weight(.semibold))
            Text("Ask it to inspect or change the agent—or, for imported agents, launch the runtime, discover MCP tools, and prove a real tool call.")
                .foregroundStyle(AppTheme.secondaryText)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 580)
            VStack(spacing: 8) {
                ForEach(starters, id: \.self) { starter in
                    Button {
                        Task { await send(starter) }
                    } label: {
                        HStack {
                            Text(starter).multilineTextAlignment(.leading)
                            Spacer()
                            Image(systemName: "arrow.right")
                        }
                        .padding(12)
                    }
                    .buttonStyle(.plain)
                    .background(AppTheme.surface)
                    .overlay(RoundedRectangle(cornerRadius: 7).stroke(AppTheme.border))
                    .clipShape(RoundedRectangle(cornerRadius: 7))
                }
            }
            .frame(maxWidth: 620)
        }
        .padding(36)
        .frame(maxWidth: .infinity, minHeight: 480)
    }

    private var composer: some View {
        VStack(spacing: 8) {
            ZStack(alignment: .topLeading) {
                if prompt.isEmpty {
                    Text("Ask the Manager to inspect, change, or run this agent…")
                        .foregroundStyle(AppTheme.secondaryText)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 8)
                        .allowsHitTesting(false)
                }
                TextEditor(text: $prompt)
                    .font(.body)
                    .scrollContentBackground(.hidden)
                    .frame(minHeight: 58, maxHeight: 108)
                    .padding(.horizontal, 1)
            }

            HStack(spacing: 9) {
                Menu {
                    Button {
                        autonomy = "review"
                    } label: {
                        Label("Review changes", systemImage: "checkmark.shield")
                    }
                    Button {
                        autonomy = "auto"
                    } label: {
                        Label("Automatic actions", systemImage: "bolt.shield.fill")
                    }
                } label: {
                    Label(
                        autonomy == "auto" ? "Auto" : "Review",
                        systemImage: autonomy == "auto" ? "bolt.shield.fill" : "checkmark.shield"
                    )
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .background(Color.white.opacity(0.07))
                    .clipShape(Capsule())
                }
                .menuStyle(.borderlessButton)

                Label(
                    agent.openaiModel ?? store.overview?.openai.model ?? "App default",
                    systemImage: "sparkles"
                )
                .font(.caption.monospaced())
                .foregroundStyle(AppTheme.secondaryText)

                Text(
                    autonomy == "auto"
                        ? "May run tools and apply validated changes"
                        : "Edits wait for your review"
                )
                .font(.caption)
                .foregroundStyle(AppTheme.secondaryText)
                .lineLimit(1)
                Spacer()

                Button {
                    Task { await send(prompt) }
                } label: {
                    ZStack {
                        Circle()
                            .fill(
                                prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                    ? Color.white.opacity(0.09)
                                    : AppTheme.accent
                            )
                            .frame(width: 38, height: 38)
                        if working {
                            ProgressView().controlSize(.small)
                        } else {
                            Image(systemName: "arrow.up")
                                .font(.callout.weight(.bold))
                                .foregroundStyle(
                                    prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                        ? AppTheme.secondaryText
                                        : Color.black.opacity(0.82)
                                )
                        }
                    }
                }
                .buttonStyle(.plain)
                .disabled(working || prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .keyboardShortcut(.return, modifiers: .command)
                .help("Send to Manager")
            }
        }
        .padding(14)
        .frame(maxWidth: 900)
        .liquidGlass(cornerRadius: 22, interactive: true)
        .padding(.horizontal, 22)
        .padding(.vertical, 14)
    }

    private var liveWork: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Live work").font(.headline)
                    Text(working ? "Orchestrating now" : "Latest run")
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                }
                Spacer()
                Button {
                    withAnimation { livePanel = false }
                } label: {
                    Image(systemName: "sidebar.trailing")
                }
                .buttonStyle(.plain)
            }
            .padding(15)
            Divider()

            ScrollView {
                if working {
                    VStack(alignment: .leading, spacing: 10) {
                        ProgressView()
                        Text("Understanding request").font(.headline)
                        Text("The Manager is deciding which MCP specialist to call first.")
                            .foregroundStyle(AppTheme.secondaryText)
                    }
                    .padding(18)
                } else if let message = conversation?.messages.last(where: { $0.role == "manager" }) {
                    VStack(alignment: .leading, spacing: 18) {
                        panelLabel("TOOL ROUTE")
                        ForEach(Array(message.actions.enumerated()), id: \.element.id) { index, action in
                            HStack(alignment: .top, spacing: 10) {
                                Text("\(index + 1)")
                                    .font(.caption.weight(.bold))
                                    .frame(width: 22, height: 22)
                                    .background(AppTheme.accent.opacity(0.15))
                                    .clipShape(Circle())
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(action.title).font(.callout.weight(.semibold))
                                    Text("\(action.server) MCP · \(action.tool)")
                                        .font(.caption2)
                                        .foregroundStyle(AppTheme.accent)
                                    Text(action.detail)
                                        .font(.caption)
                                        .foregroundStyle(AppTheme.secondaryText)
                                }
                                Spacer()
                                StatusDot(status: action.status)
                            }
                        }

                        panelLabel("OUTCOME")
                        Label("\(message.changes.count) changes", systemImage: "doc.badge.gearshape")
                        if let evaluation = message.evaluation {
                            VStack(alignment: .leading, spacing: 5) {
                                StatusPill(status: evaluation.status)
                                Text(evaluation.summary)
                                    .font(.caption)
                                    .foregroundStyle(AppTheme.secondaryText)
                                ForEach(evaluation.checks, id: \.self) { check in
                                    Label(check, systemImage: "checkmark")
                                        .font(.caption)
                                }
                            }
                        }
                    }
                    .padding(16)
                } else {
                    ContentUnavailableView(
                        "Waiting for a Task",
                        systemImage: "point.3.connected.trianglepath.dotted",
                        description: Text("The Manager's tool route appears here.")
                    )
                    .padding(.top, 80)
                }
            }
        }
        .background(AppTheme.sidebar)
    }

    private func panelLabel(_ value: String) -> some View {
        Text(value)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(AppTheme.secondaryText)
    }

    private func load() async {
        guard let api = store.api else { return }
        do {
            let items: [ManagerConversation] = try await api.get(
                "/api/manager/conversations",
                query: [URLQueryItem(name: "agent_id", value: agent.id)]
            )
            conversations = items
        } catch {
            store.show(error.localizedDescription, error: true)
        }
    }

    private func send(_ value: String) async {
        let outgoing = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !outgoing.isEmpty, !working, let api = store.api else { return }
        working = true
        if value == prompt { prompt = "" }
        do {
            let next: ManagerConversation = try await api.post(
                "/api/manager/message",
                body: ManagerChatRequest(
                    agentId: agent.id,
                    message: outgoing,
                    conversationId: conversation?.id,
                    autonomy: autonomy
                )
            )
            conversation = next
            conversations = [next] + conversations.filter { $0.id != next.id }
            if autonomy == "auto" { try await store.refresh() }
        } catch {
            prompt = outgoing
            store.show(error.localizedDescription, error: true)
        }
        working = false
    }

    private func applyChanges() {
        Task {
            guard let conversation, !applying, let api = store.api else { return }
            applying = true
            do {
                let next: ManagerConversation = try await api.post(
                    "/api/manager/conversations/\(conversation.id)/apply"
                )
                self.conversation = next
                conversations = [next] + conversations.filter { $0.id != next.id }
                try await store.refresh()
                store.show("Reviewed change applied to the client agent.")
            } catch {
                store.show(error.localizedDescription, error: true)
            }
            applying = false
        }
    }
}

struct ManagerMessageView: View {
    let message: ManagerMessage
    let applying: Bool
    let onApply: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            RoundedRectangle(cornerRadius: 7)
                .fill(message.role == "user" ? Color.white.opacity(0.08) : AppTheme.accent.opacity(0.13))
                .frame(width: 34, height: 34)
                .overlay(
                    Text(message.role == "user" ? "You" : "M")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(message.role == "user" ? .white : AppTheme.accent)
                )

            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text(message.role == "user" ? "You" : "Manager Agent")
                        .font(.callout.weight(.semibold))
                    if message.role == "manager" {
                        Text(message.provider)
                            .font(.caption2)
                            .foregroundStyle(AppTheme.secondaryText)
                    }
                }
                Text(message.content)
                    .textSelection(.enabled)

                if !message.actions.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack {
                            ForEach(message.actions) { action in
                                HStack(spacing: 6) {
                                    StatusDot(status: action.status)
                                    Text(action.tool).font(.caption.monospaced())
                                }
                                .padding(.horizontal, 9)
                                .padding(.vertical, 6)
                                .background(Color.white.opacity(0.05))
                                .clipShape(Capsule())
                            }
                        }
                    }
                }

                let evidenceActions = message.actions.filter { !$0.evidence.isEmpty }
                if !evidenceActions.isEmpty {
                    DisclosureGroup {
                        VStack(alignment: .leading, spacing: 10) {
                            ForEach(evidenceActions) { action in
                                VStack(alignment: .leading, spacing: 6) {
                                    HStack {
                                        StatusDot(status: action.status)
                                        Text(action.tool)
                                            .font(.caption.monospaced().weight(.semibold))
                                        Spacer()
                                        Text(action.server)
                                            .font(.caption2)
                                            .foregroundStyle(AppTheme.secondaryText)
                                    }
                                    Text(JSONValue.object(action.evidence).prettyPrinted)
                                        .font(.caption.monospaced())
                                        .textSelection(.enabled)
                                        .padding(9)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        .background(Color.black.opacity(0.22))
                                        .clipShape(RoundedRectangle(cornerRadius: 6))
                                }
                            }
                        }
                        .padding(.top, 8)
                    } label: {
                        Label("Execution Evidence", systemImage: "checkmark.shield")
                            .font(.callout.weight(.semibold))
                    }
                    .padding(11)
                    .background(AppTheme.accent.opacity(0.055))
                    .overlay(RoundedRectangle(cornerRadius: 7).stroke(AppTheme.border))
                    .clipShape(RoundedRectangle(cornerRadius: 7))
                }

                ForEach(message.changes) { change in
                    DisclosureGroup {
                        VStack(alignment: .leading, spacing: 8) {
                            diffBlock("Before", text: change.before, color: AppTheme.danger)
                            diffBlock("After", text: change.after, color: AppTheme.accent)
                        }
                        .padding(.top, 8)
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(change.target).font(.callout.weight(.semibold))
                                Text(change.summary)
                                    .font(.caption)
                                    .foregroundStyle(AppTheme.secondaryText)
                            }
                            Spacer()
                            StatusPill(status: change.status)
                        }
                    }
                    .padding(12)
                    .background(Color.black.opacity(0.16))
                    .overlay(RoundedRectangle(cornerRadius: 7).stroke(AppTheme.border))
                    .clipShape(RoundedRectangle(cornerRadius: 7))
                }

                if let evaluation = message.evaluation {
                    HStack(alignment: .top, spacing: 10) {
                        StatusDot(status: evaluation.status)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Validation \(evaluation.status)")
                                .font(.callout.weight(.semibold))
                            Text(evaluation.summary)
                                .font(.caption)
                                .foregroundStyle(AppTheme.secondaryText)
                        }
                    }
                    .padding(11)
                    .background(AppTheme.accent.opacity(0.06))
                    .clipShape(RoundedRectangle(cornerRadius: 7))
                }

                if message.changes.contains(where: { $0.status == "pending" }) {
                    Button(applying ? "Applying…" : "Apply Reviewed Change", action: onApply)
                        .buttonStyle(.borderedProminent)
                        .disabled(applying)
                }
            }
            .frame(maxWidth: 720, alignment: .leading)
            Spacer(minLength: 0)
        }
    }

    private func diffBlock(_ title: String, text: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased())
                .font(.caption2.weight(.bold))
                .foregroundStyle(color)
            Text(text)
                .font(.caption.monospaced())
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(9)
                .background(Color.black.opacity(0.22))
                .clipShape(RoundedRectangle(cornerRadius: 5))
        }
    }
}

struct TestWorkspaceView: View {
    @EnvironmentObject private var store: AppStore
    let agent: AgentRecord
    let requestedConversationID: String?
    let requestedTool: String?

    @State private var conversations: [AgentConversation] = []
    @State private var conversation: AgentConversation?
    @State private var message = ""
    @State private var contextMode = "minimal"
    @State private var sending = false
    @State private var historyPanel = false
    @State private var contextPanelVisible = false

    private var starters: [String] {
        if let requestedTool {
            return ["Test \(requestedTool) with a representative request and include the proof values."]
        }
        switch agent.id {
        case "finance-agent":
            return ["What is the status of INV-2048?", "Summarize the payment risk for INV-2048."]
        case "coding-agent":
            return ["Review REPO-1 for release risk.", "Summarize test and coverage health for REPO-1."]
        case "support-agent":
            return ["Look up support ticket TCK-9001.", "What is the next action for TCK-9001?"]
        default:
            return ["Summarize this agent’s current capabilities.", "Run a representative request using available evidence."]
        }
    }

    var body: some View {
        HStack(spacing: 0) {
            if historyPanel {
                conversationRail
                    .frame(width: 238)
                    .transition(.move(edge: .leading).combined(with: .opacity))
                Divider()
            }
            chat.frame(minWidth: 480)
            if contextPanelVisible {
                Divider()
                contextPanel
                    .frame(width: 306)
                    .transition(.move(edge: .trailing).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.2), value: historyPanel)
        .animation(.easeInOut(duration: 0.2), value: contextPanelVisible)
        .task { await load() }
    }

    private var conversationRail: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Test conversations").font(.headline)
                    Text("\(conversations.count) with this agent")
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                }
                Spacer()
                Button {
                    conversation = nil
                } label: {
                    Image(systemName: "square.and.pencil")
                }
                .buttonStyle(.plain)
                Button {
                    withAnimation { historyPanel = false }
                } label: {
                    Image(systemName: "xmark")
                }
                .buttonStyle(.plain)
            }
            .padding(13)

            ScrollView {
                LazyVStack(spacing: 4) {
                    ForEach(conversations) { item in
                        Button {
                            conversation = item
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(item.title).font(.callout.weight(.medium)).lineLimit(2)
                                Text("\(item.messages.count) messages · \(item.updatedAt.shortTimestamp)")
                                    .font(.caption2)
                                    .foregroundStyle(AppTheme.secondaryText)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(10)
                            .background(conversation?.id == item.id ? Color.white.opacity(0.08) : .clear)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 7)
            }
        }
        .background(AppTheme.sidebar)
    }

    private var chat: some View {
        VStack(spacing: 0) {
            HStack {
                HStack(spacing: 7) {
                    StatusDot(status: agent.status)
                    Text("Testing \(agent.name)").font(.headline)
                }
                Spacer()
                Button {
                    withAnimation(.easeInOut(duration: 0.18)) {
                        historyPanel.toggle()
                    }
                } label: {
                    Label("History", systemImage: "clock.arrow.circlepath")
                }
                .buttonStyle(.borderless)
                Button {
                    withAnimation(.easeInOut(duration: 0.18)) {
                        contextPanelVisible.toggle()
                    }
                } label: {
                    Label(
                        contextPanelVisible ? "Hide Context" : "Context",
                        systemImage: "sidebar.trailing"
                    )
                }
                .buttonStyle(.borderless)
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 12)
            .background(AppTheme.surface)

            ScrollView {
                if let conversation {
                    LazyVStack(alignment: .leading, spacing: 20) {
                        ForEach(conversation.messages) { item in
                            ChatMessageView(message: item)
                        }
                        if sending {
                            HStack(spacing: 10) {
                                ProgressView().controlSize(.small)
                                Text("Client agent is working…")
                                    .foregroundStyle(AppTheme.secondaryText)
                            }
                        }
                    }
                    .padding(22)
                } else {
                    VStack(spacing: 15) {
                        Image(systemName: "play.square.stack")
                            .font(.system(size: 38))
                            .foregroundStyle(AppTheme.accent)
                        Text("Test \(agent.name)")
                            .font(.title.weight(.semibold))
                        Text("Talk directly to the client agent and inspect its tool use and verification evidence.")
                            .foregroundStyle(AppTheme.secondaryText)
                            .multilineTextAlignment(.center)
                        ForEach(starters, id: \.self) { starter in
                            Button {
                                Task { await send(starter) }
                            } label: {
                                HStack {
                                    Text(starter)
                                    Spacer()
                                    Image(systemName: "arrow.right")
                                }
                                .padding(12)
                            }
                            .buttonStyle(.plain)
                            .background(AppTheme.surface)
                            .overlay(RoundedRectangle(cornerRadius: 7).stroke(AppTheme.border))
                            .clipShape(RoundedRectangle(cornerRadius: 7))
                        }
                    }
                    .frame(maxWidth: 580)
                    .padding(36)
                    .frame(maxWidth: .infinity, minHeight: 460)
                }
            }
            .defaultScrollAnchor(.bottom)

            VStack(spacing: 8) {
                ZStack(alignment: .topLeading) {
                    if message.isEmpty {
                        Text("Message \(agent.name)…")
                            .foregroundStyle(AppTheme.secondaryText)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 8)
                            .allowsHitTesting(false)
                    }
                    TextEditor(text: $message)
                        .scrollContentBackground(.hidden)
                        .frame(minHeight: 58, maxHeight: 104)
                }
                HStack(spacing: 9) {
                    Menu {
                        Button {
                            contextMode = "minimal"
                        } label: {
                            Label("Focused context", systemImage: "scope")
                        }
                        Button {
                            contextMode = "full"
                        } label: {
                            Label("Import all context", systemImage: "square.stack.3d.up")
                        }
                    } label: {
                        Label(
                            contextMode == "full" ? "Full context" : "Focused",
                            systemImage: contextMode == "full" ? "square.stack.3d.up" : "scope"
                        )
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 7)
                        .background(Color.white.opacity(0.07))
                        .clipShape(Capsule())
                    }
                    .menuStyle(.borderlessButton)

                    Label(
                        agent.openaiModel ?? store.overview?.openai.model ?? "App default",
                        systemImage: "sparkles"
                    )
                    .font(.caption.monospaced())
                    .foregroundStyle(AppTheme.secondaryText)

                    Text(contextMode == "full" ? "All agent context included" : "Only relevant context included")
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                    Spacer()
                    Button {
                        Task { await send(message) }
                    } label: {
                        ZStack {
                            Circle()
                                .fill(
                                    message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                        ? Color.white.opacity(0.09)
                                        : AppTheme.accent
                                )
                                .frame(width: 38, height: 38)
                            if sending {
                                ProgressView().controlSize(.small)
                            } else {
                                Image(systemName: "arrow.up")
                                    .font(.callout.weight(.bold))
                                    .foregroundStyle(
                                        message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                            ? AppTheme.secondaryText
                                            : Color.black.opacity(0.82)
                                    )
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(sending || message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .keyboardShortcut(.return, modifiers: .command)
                    .help("Run client test")
                }
            }
            .padding(14)
            .frame(maxWidth: 900)
            .liquidGlass(cornerRadius: 22, interactive: true)
            .padding(.horizontal, 22)
            .padding(.vertical, 14)
        }
    }

    private var contextPanel: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Test context").font(.headline)
                        Text(contextMode == "full" ? "Full import" : "Focused import")
                            .font(.caption)
                            .foregroundStyle(AppTheme.secondaryText)
                    }
                    Spacer()
                    Button {
                        withAnimation { contextPanelVisible = false }
                    } label: {
                        Image(systemName: "xmark")
                    }
                    .buttonStyle(.plain)
                }
                Divider()
                contextBlock("EXECUTION PATH") {
                    Text(agent.mcpEndpoint?.hasPrefix("http") == true ? "External MCP" : "Local demo")
                        .font(.callout.weight(.semibold))
                    Text(agent.mcpEndpoint ?? "No endpoint configured")
                        .font(.caption.monospaced())
                        .foregroundStyle(AppTheme.secondaryText)
                        .textSelection(.enabled)
                }
                contextBlock("OPENAI MODEL") {
                    Text(agent.openaiModel ?? store.overview?.openai.model ?? "Application default")
                        .font(.callout.monospaced().weight(.semibold))
                    Text(
                        "\(agent.openaiReasoningEffort ?? store.overview?.openai.reasoningEffort ?? "provider default") reasoning · "
                        + (agent.openaiModel == nil ? "app default" : "agent override")
                    )
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)
                }
                contextBlock("ACTIVE CONFIGURATION") {
                    Text("\(agent.responseStyle.capitalized) responses")
                        .font(.callout.weight(.semibold))
                    Text("\(agent.verificationMode) verification · memory \(agent.memoryEnabled ? "on" : "off")")
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                }
                contextBlock("ENABLED TOOLS") {
                    ForEach(agent.mcpTools.filter {
                        agent.enabledTools.isEmpty || agent.enabledTools.contains($0.name)
                    }) { tool in
                        HStack(spacing: 7) {
                            StatusDot(status: requestedTool == tool.name ? "degraded" : "healthy")
                            Text(tool.name).font(.caption.monospaced())
                        }
                    }
                }
                contextBlock("INSTRUCTIONS") {
                    Text(agent.instructions)
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                        .textSelection(.enabled)
                }
            }
            .padding(16)
        }
        .background(AppTheme.sidebar)
    }

    private func contextBlock<Content: View>(
        _ title: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(AppTheme.secondaryText)
            content()
        }
    }

    private func load() async {
        guard let api = store.api else { return }
        do {
            let items: [AgentConversation] = try await api.get(
                "/api/conversations",
                query: [URLQueryItem(name: "agent_id", value: agent.id)]
            )
            conversations = items
            conversation = items.first { $0.id == requestedConversationID }
        } catch {
            store.show(error.localizedDescription, error: true)
        }
    }

    private func send(_ value: String) async {
        let outgoing = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !outgoing.isEmpty, !sending, let api = store.api else { return }
        sending = true
        if value == message { message = "" }
        do {
            let next: AgentConversation = try await api.post(
                "/api/conversations/message",
                body: AgentChatRequest(
                    agentId: agent.id,
                    message: outgoing,
                    conversationId: conversation?.id,
                    contextMode: contextMode,
                    toolName: requestedTool
                )
            )
            conversation = next
            conversations = [next] + conversations.filter { $0.id != next.id }
            try await store.refresh()
        } catch {
            message = outgoing
            store.show(error.localizedDescription, error: true)
        }
        sending = false
    }
}

struct ChatMessageView: View {
    let message: ChatMessage

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            RoundedRectangle(cornerRadius: 7)
                .fill(message.role == "user" ? Color.white.opacity(0.08) : AppTheme.accent.opacity(0.13))
                .frame(width: 34, height: 34)
                .overlay(
                    Text(message.role == "user" ? "You" : "A")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(message.role == "user" ? .white : AppTheme.accent)
                )
            VStack(alignment: .leading, spacing: 10) {
                Text(message.role == "user" ? "You" : "Client agent")
                    .font(.callout.weight(.semibold))
                Text(message.content).textSelection(.enabled)

                if message.role == "agent" {
                    executionReceipt
                    HStack(spacing: 14) {
                        Label("Context scoped", systemImage: "checkmark")
                        Label("\(message.toolCalls.count) tools recorded", systemImage: "checkmark")
                        Label("Output checked", systemImage: "checkmark")
                    }
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)

                    if let verification = message.verification {
                        DisclosureGroup {
                            VStack(alignment: .leading, spacing: 12) {
                                Text(verification.summary)
                                evidenceColumn("ACCEPTANCE CRITERIA", values: verification.criteria)
                                evidenceColumn("GROUNDING EVIDENCE", values: verification.evidence)
                                if !message.contextUsed.isEmpty {
                                    evidenceColumn("CONTEXT USED", values: message.contextUsed)
                                }
                                ForEach(message.toolCalls) { call in
                                    DisclosureGroup {
                                        VStack(alignment: .leading, spacing: 8) {
                                            codeBlock("INPUT", call.input)
                                            codeBlock("OUTPUT", call.output)
                                        }
                                        .padding(.top, 7)
                                    } label: {
                                        HStack {
                                            StatusDot(status: call.status)
                                            Text(call.toolName).font(.caption.monospaced())
                                            Text(call.provider)
                                                .font(.caption2)
                                                .foregroundStyle(AppTheme.accent)
                                            Spacer()
                                            Text("\(call.durationMs) ms")
                                                .font(.caption)
                                                .foregroundStyle(AppTheme.secondaryText)
                                        }
                                        if let endpoint = call.endpoint {
                                            Text(endpoint)
                                                .font(.caption2.monospaced())
                                                .foregroundStyle(AppTheme.secondaryText)
                                                .lineLimit(1)
                                        }
                                    }
                                }
                            }
                            .padding(.top, 10)
                        } label: {
                            HStack {
                                Image(systemName: "checkmark.shield.fill")
                                    .foregroundStyle(AppTheme.accent)
                                VStack(alignment: .leading) {
                                    Text("Output \(verification.status)")
                                        .font(.callout.weight(.semibold))
                                    Text("\(Int(verification.confidence * 100))% confidence")
                                        .font(.caption)
                                        .foregroundStyle(AppTheme.secondaryText)
                                }
                            }
                        }
                        .padding(12)
                        .background(AppTheme.surface)
                        .overlay(RoundedRectangle(cornerRadius: 7).stroke(AppTheme.border))
                        .clipShape(RoundedRectangle(cornerRadius: 7))
                    }
                }
            }
            .frame(maxWidth: 760, alignment: .leading)
            Spacer(minLength: 0)
        }
    }

    private var executionReceipt: some View {
        HStack(spacing: 8) {
            StatusDot(status: message.executionMode == "fallback" ? "degraded" : "healthy")
            Text(message.executionMode == "live" ? "Live MCP" : message.executionMode == "fallback" ? "Fallback demo" : "Local demo")
                .font(.caption.weight(.semibold))
            Text(message.provider)
                .font(.caption.monospaced())
                .foregroundStyle(AppTheme.secondaryText)
            if let endpoint = message.endpoint {
                Text(endpoint)
                    .font(.caption2.monospaced())
                    .foregroundStyle(AppTheme.secondaryText)
                    .lineLimit(1)
            }
            if let reason = message.fallbackReason {
                Text(reason)
                    .font(.caption)
                    .foregroundStyle(AppTheme.warning)
                    .lineLimit(2)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(Color.white.opacity(0.045))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private func evidenceColumn(_ title: String, values: [String]) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(AppTheme.secondaryText)
            ForEach(values, id: \.self) {
                Label($0, systemImage: "checkmark")
                    .font(.caption)
            }
        }
    }

    private func codeBlock(_ title: String, _ value: [String: JSONValue]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(AppTheme.secondaryText)
            Text(JSONValue.object(value).prettyPrinted)
                .font(.caption.monospaced())
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(9)
                .background(Color.black.opacity(0.24))
                .clipShape(RoundedRectangle(cornerRadius: 5))
        }
    }
}
