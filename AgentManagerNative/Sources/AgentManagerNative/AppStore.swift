import AppKit
import Combine
import Foundation

enum AppSection: String, CaseIterable, Identifiable {
    case dashboard
    case workspace
    case agents
    case benchmarks
    case activity
    case health

    var id: String { rawValue }
    var title: String {
        switch self {
        case .dashboard: "Dashboard"
        case .workspace: "Workspace"
        case .agents: "Managed agents"
        case .benchmarks: "Benchmarks"
        case .activity: "Activity"
        case .health: "System health"
        }
    }
    var symbol: String {
        switch self {
        case .dashboard: "square.grid.2x2"
        case .workspace: "wand.and.stars"
        case .agents: "person.3"
        case .benchmarks: "chart.bar.xaxis"
        case .activity: "clock.arrow.circlepath"
        case .health: "waveform.path.ecg"
        }
    }
}

@MainActor
final class AppStore: ObservableObject {
    @Published var section: AppSection? =
        AppSection(
            rawValue: ProcessInfo.processInfo.environment["AGENT_MANAGER_INITIAL_SECTION"] ?? ""
        ) ?? .dashboard
    @Published var overview: Overview?
    @Published var health: HealthReport?
    @Published var selectedAgentID: String?
    @Published var workspaceMode = "edit"
    @Published var workspaceTool: String?
    @Published var requestedConversationID: String?
    @Published var loading = true
    @Published var errorMessage: String?
    @Published var notice: String?

    private let backend = BackendController()
    private(set) var api: APIClient?

    var agents: [AgentRecord] { overview?.architecture.agents ?? [] }
    var selectedAgent: AgentRecord? {
        agents.first { $0.id == selectedAgentID } ?? agents.first
    }

    func start() async {
        loading = true
        do {
            let baseURL = try await backend.start()
            api = APIClient(baseURL: baseURL)
            try await refresh()
            if selectedAgentID == nil { selectedAgentID = agents.first?.id }
            if let requestedSection = ProcessInfo.processInfo.environment["AGENT_MANAGER_INITIAL_SECTION"],
               let initialSection = AppSection(rawValue: requestedSection) {
                section = initialSection
            }
            NSApp.activate(ignoringOtherApps: true)
        } catch {
            errorMessage = error.localizedDescription
            let diagnostic = "[Agent Manager] Startup failed: \(error.localizedDescription)\n"
            FileHandle.standardError.write(Data(diagnostic.utf8))
        }
        loading = false
    }

    func refresh() async throws {
        guard let api else { throw APIError(message: "Backend is not connected.") }
        let nextOverview: Overview = try await api.get("/api/overview")
        let nextHealth: HealthReport = try await api.get("/api/health")
        overview = nextOverview
        health = nextHealth
    }

    func refreshShowingErrors() async {
        do { try await refresh() }
        catch { show(error.localizedDescription, error: true) }
    }

    func resetDemo() async {
        guard let api else { return }
        do {
            let _: ResetResponse = try await api.post("/api/reset")
            try await refresh()
            show("Native demo workspace reset.")
        } catch {
            show(error.localizedDescription, error: true)
        }
    }

    func openWorkspace(
        agentID: String,
        mode: String = "edit",
        conversationID: String? = nil,
        tool: String? = nil
    ) {
        selectedAgentID = agentID
        workspaceMode = mode
        requestedConversationID = conversationID
        workspaceTool = tool
        section = .workspace
    }

    func show(_ message: String, error: Bool = false) {
        notice = error ? nil : message
        errorMessage = error ? message : nil
        Task {
            try? await Task.sleep(for: .seconds(3))
            if self.notice == message { self.notice = nil }
        }
    }

    func stop() {
        backend.stop()
    }
}
