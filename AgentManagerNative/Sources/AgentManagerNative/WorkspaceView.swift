import AppKit
import SwiftUI

private struct AgentThinkingView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    let initial: String
    let title: String
    let stages: [String]
    let detail: String

    @State private var stage = 0
    @State private var animating = false

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .stroke(AppTheme.accent.opacity(0.5), lineWidth: 1.5)
                    .frame(width: 36, height: 36)
                    .scaleEffect(animating && !reduceMotion ? 1.42 : 0.92)
                    .opacity(animating && !reduceMotion ? 0 : 0.55)
                    .animation(
                        .easeOut(duration: 1.45)
                            .repeatForever(autoreverses: false),
                        value: animating
                    )
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(AppTheme.accent.opacity(0.14))
                    .frame(width: 36, height: 36)
                    .overlay(
                        Text(initial)
                            .font(.caption.weight(.bold))
                            .foregroundStyle(AppTheme.accent)
                    )
            }

            VStack(alignment: .leading, spacing: 7) {
                Text(title)
                    .font(.callout.weight(.semibold))

                HStack(spacing: 8) {
                    HStack(spacing: 4) {
                        ForEach(0..<3, id: \.self) { index in
                            Circle()
                                .fill(AppTheme.accent)
                                .frame(width: 5, height: 5)
                                .offset(
                                    y: animating && !reduceMotion
                                    ? -3
                                    : 2
                                )
                                .opacity(
                                    animating && !reduceMotion
                                    ? 0.35
                                    : 1
                                )
                                .animation(
                                    .easeInOut(duration: 0.58)
                                        .repeatForever(autoreverses: true)
                                        .delay(Double(index) * 0.13),
                                    value: animating
                                )
                        }
                    }

                    Text(stages[stage])
                        .id(stage)
                        .font(.callout.weight(.medium))
                        .contentTransition(.opacity)
                        .transition(
                            .opacity.combined(
                                with: .move(edge: .bottom)
                            )
                        )
                }

                Text(detail)
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)
            }
            Spacer(minLength: 0)
        }
        .padding(14)
        .frame(maxWidth: 680, alignment: .leading)
        .background(AppTheme.surface.opacity(0.8))
        .overlay {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(AppTheme.border)
        }
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .transition(.opacity.combined(with: .move(edge: .bottom)))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title) is working. \(stages[stage])")
        .onAppear {
            animating = true
        }
        .task {
            guard !reduceMotion, stages.count > 1 else { return }
            while !Task.isCancelled {
                do {
                    try await Task.sleep(for: .seconds(1.65))
                } catch {
                    return
                }
                withAnimation(.easeInOut(duration: 0.28)) {
                    stage = (stage + 1) % stages.count
                }
            }
        }
    }
}

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
    @FocusState private var composerFocused: Bool

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
        .task {
            await load()
            composerFocused = true
        }
        .onReceive(NotificationCenter.default.publisher(
            for: NSWindow.didBecomeKeyNotification
        )) { _ in
            composerFocused = true
        }
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
                            managerThinking
                        }
                    }
                    .padding(22)
                } else if working {
                    managerThinking
                        .padding(22)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    managerWelcome
                }
            }
            .defaultScrollAnchor(.bottom)

            composer
        }
        .background(AppTheme.background)
    }

    private var managerThinking: some View {
        AgentThinkingView(
            initial: "M",
            title: "Manager Agent",
            stages: [
                "Understanding your request",
                "Inspecting fleet and agent context",
                "Selecting MCP specialist tools",
                "Validating the result"
            ],
            detail: "Coordinating live work for \(agent.name)."
        )
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
            TextField(
                "Ask the Manager to inspect, change, or run this agent…",
                text: $prompt,
                axis: .vertical
            )
            .textFieldStyle(.plain)
            .lineLimit(1...3)
            .focused($composerFocused)
            .padding(.horizontal, 3)
            .padding(.vertical, 5)
            .frame(minHeight: 30, maxHeight: 72)

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

                WorkspaceModelMenu(agent: agent)

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
        .padding(10)
        .frame(maxWidth: 860)
        .background(AppTheme.raised)
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(AppTheme.border)
        )
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .padding(.horizontal, 22)
        .padding(.vertical, 10)
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

struct WorkspaceModelMenu: View {
    @EnvironmentObject private var store: AppStore
    let agent: AgentRecord

    @State private var saving = false

    private var provider: OpenAIStatus? { store.overview?.openai }
    private var models: [OpenAIModelOption] {
        provider?.modelOptions ?? []
    }
    private var effectiveModel: String {
        agent.openaiModel ?? provider?.model ?? "App default"
    }
    private var effectiveReasoning: String {
        agent.openaiReasoningEffort
            ?? provider?.reasoningEffort
            ?? "default"
    }
    private var reasoningOptions: [String] {
        let selected = agent.openaiModel ?? provider?.model
        return models.first(where: { $0.id == selected })?.reasoningEfforts
            ?? ["none", "low", "medium", "high", "xhigh", "max"]
    }

    var body: some View {
        Menu {
            Section("Model") {
                Button {
                    Task {
                        await save(
                            model: nil,
                            reasoning: agent.openaiReasoningEffort
                        )
                    }
                } label: {
                    menuLabel(
                        "App default (\(provider?.model ?? "configured model"))",
                        selected: agent.openaiModel == nil
                    )
                }
                ForEach(models) { option in
                    Button {
                        Task {
                            await save(
                                model: option.id,
                                reasoning: agent.openaiReasoningEffort
                            )
                        }
                    } label: {
                        menuLabel(
                            "\(option.label) · \(option.role)",
                            selected: agent.openaiModel == option.id
                        )
                    }
                }
            }

            Section("Reasoning effort") {
                Button {
                    Task {
                        await save(
                            model: agent.openaiModel,
                            reasoning: nil
                        )
                    }
                } label: {
                    menuLabel(
                        "App default (\(provider?.reasoningEffort ?? "configured effort"))",
                        selected: agent.openaiReasoningEffort == nil
                    )
                }
                ForEach(reasoningOptions, id: \.self) { effort in
                    Button {
                        Task {
                            await save(
                                model: agent.openaiModel,
                                reasoning: effort
                            )
                        }
                    } label: {
                        menuLabel(
                            effort.capitalized,
                            selected: agent.openaiReasoningEffort == effort
                        )
                    }
                }
            }
        } label: {
            HStack(spacing: 6) {
                if saving {
                    ProgressView().controlSize(.mini)
                } else {
                    Image(systemName: "sparkles")
                }
                Text("\(effectiveModel) · \(effectiveReasoning)")
                    .lineLimit(1)
                Image(systemName: "chevron.down")
                    .font(.system(size: 8, weight: .bold))
            }
            .font(.caption.monospaced())
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(Color.white.opacity(0.07))
            .clipShape(Capsule())
        }
        .menuStyle(.borderlessButton)
        .disabled(saving || models.isEmpty)
        .help("Change this agent's model or reasoning effort")
    }

    private func menuLabel(_ title: String, selected: Bool) -> some View {
        HStack {
            Text(title)
            if selected { Image(systemName: "checkmark") }
        }
    }

    private func save(model: String?, reasoning: String?) async {
        guard let api = store.api else { return }
        saving = true
        do {
            let request = AgentUpdateRequest(
                name: agent.name,
                description: agent.description,
                owner: agent.owner,
                mcpEndpoint: agent.mcpEndpoint,
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
            let _: AgentRecord = try await api.patch(
                "/api/managed-agents/\(agent.id)",
                body: request
            )
            try await store.refresh()
            store.show("Model settings updated for \(agent.name).")
        } catch {
            store.show(error.localizedDescription, error: true)
        }
        saving = false
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
    @FocusState private var composerFocused: Bool

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
        .task {
            await load()
            composerFocused = true
        }
        .onReceive(NotificationCenter.default.publisher(
            for: NSWindow.didBecomeKeyNotification
        )) { _ in
            composerFocused = true
        }
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
                            clientThinking
                        }
                    }
                    .padding(22)
                } else if sending {
                    clientThinking
                        .padding(22)
                        .frame(maxWidth: .infinity, alignment: .leading)
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
                TextField(
                    "Message \(agent.name)…",
                    text: $message,
                    axis: .vertical
                )
                .textFieldStyle(.plain)
                .lineLimit(1...3)
                .focused($composerFocused)
                .padding(.horizontal, 3)
                .padding(.vertical, 5)
                .frame(minHeight: 30, maxHeight: 72)
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

                    WorkspaceModelMenu(agent: agent)

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
            .padding(10)
            .frame(maxWidth: 860)
            .background(AppTheme.raised)
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(AppTheme.border)
            )
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .padding(.horizontal, 22)
            .padding(.vertical, 10)
        }
    }

    private var clientThinking: some View {
        AgentThinkingView(
            initial: "A",
            title: "\(agent.name) is working",
            stages: (
                agent.imported
                    && agent.mcpEndpoint?.hasPrefix("http") == true
            )
            ? [
                "Starting the managed runtime",
                "Discovering live MCP tools",
                "Calling the grounded tool",
                "Checking the returned evidence"
            ]
            : [
                "Reading agent context",
                "Selecting an available tool",
                "Running the request",
                "Checking the answer"
            ],
            detail: (
                agent.imported
                    && agent.mcpEndpoint?.hasPrefix("http") == true
            )
            ? "First startup can take a moment while MCP becomes ready."
            : "The test stays active while the agent produces and verifies its response."
        )
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
                    Text(
                        agent.imported && agent.mcpEndpoint?.hasPrefix("http") == true
                        ? "Managed local MCP · starts on demand"
                        : agent.mcpEndpoint?.hasPrefix("http") == true
                        ? "Remote MCP"
                        : "Local demo"
                    )
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
                                Image(
                                    systemName: verification.status == "failed"
                                    ? "xmark.shield.fill"
                                    : "checkmark.shield.fill"
                                )
                                .foregroundStyle(
                                    verification.status == "failed"
                                    ? AppTheme.danger
                                    : AppTheme.accent
                                )
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

    private var liveFailedWithoutMock: Bool {
        message.executionMode == "fallback"
            && message.provider == "local:error"
    }

    private var executionReceipt: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                StatusDot(
                    status: liveFailedWithoutMock
                    ? "failed"
                    : (message.executionMode == "fallback" ? "degraded" : "healthy")
                )
                Text(
                    message.executionMode == "live"
                    ? "Live agent + MCP"
                    : liveFailedWithoutMock
                    ? "Live agent failed · no mock response"
                    : message.executionMode == "fallback"
                    ? "Live unavailable · fallback used"
                    : "Local demo"
                )
                .font(.caption.weight(.semibold))
                Spacer()
                Text(message.provider)
                    .font(.caption.monospaced())
                    .foregroundStyle(AppTheme.secondaryText)
            }
            if let endpoint = message.endpoint {
                Text(endpoint)
                    .font(.caption2.monospaced())
                    .foregroundStyle(AppTheme.secondaryText)
                    .lineLimit(1)
            }
            if let reason = message.fallbackReason {
                Label(reason, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(AppTheme.warning)
                    .fixedSize(horizontal: false, vertical: true)
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
