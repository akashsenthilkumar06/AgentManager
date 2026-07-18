import Foundation

enum JSONValue: Codable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else {
            self = .array(try container.decode([JSONValue].self))
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }

    var foundationValue: Any {
        switch self {
        case .string(let value): value
        case .number(let value): value
        case .bool(let value): value
        case .object(let value): value.mapValues(\.foundationValue)
        case .array(let value): value.map(\.foundationValue)
        case .null: NSNull()
        }
    }

    var prettyPrinted: String {
        guard JSONSerialization.isValidJSONObject(foundationValue),
              let data = try? JSONSerialization.data(
                withJSONObject: foundationValue,
                options: [.prettyPrinted, .sortedKeys]
              )
        else { return String(describing: foundationValue) }
        return String(decoding: data, as: UTF8.self)
    }
}

struct Overview: Decodable {
    let architecture: Architecture
    let recentBuilds: [BuildRecord]
    let recentBenchmarks: [BenchmarkRun]
    let recentConversations: [AgentConversation]
    let standingFindings: [ReconciliationFinding]
    let reconciliation: ReconciliationOverview
    let openai: OpenAIStatus
    let mcpServers: [MCPServer]
}

struct Architecture: Decodable {
    let agents: [AgentRecord]
    let tools: [ToolRecord]
    let endpoints: [EndpointRecord]
    let dataSources: [DataSourceRecord]
    let indexedAt: String
}

struct MCPServer: Decodable, Identifiable {
    let id: String
    let name: String
    let status: String
    let tools: Int
}

struct AgentRecord: Codable, Identifiable {
    let id: String
    var name: String
    var description: String
    var owner: String
    var toolIds: [String]
    var status: String
    var mcpEndpoint: String?
    var mcpServerName: String?
    var mcpTools: [MCPToolCapability]
    var attachedTools: [MCPToolCapability]
    var mcpPrompts: [String]
    var mcpResources: [String]
    var features: [String]
    var lastDiscoveredAt: String?
    var instructions: String
    var responseStyle: String
    var toolPolicy: String
    var enabledTools: [String]
    var verificationMode: String
    var memoryEnabled: Bool
    var openaiModel: String?
    var openaiReasoningEffort: String?
    var imported: Bool
    var workspaceId: String?
    var workspaceRoot: String?
    var runCommand: String?
    var detectedEntrypoints: [String]
}

struct MCPToolCapability: Codable, Identifiable {
    var id: String { name }
    let name: String
    let description: String
    let inputSchema: [String: JSONValue]
    let toolId: String?
    let provider: String
    let providerEndpoint: String?
}

struct ToolRecord: Decodable, Identifiable {
    let id: String
    let name: String
    let description: String
    let owner: String
    let endpointIds: [String]
    let inputSchema: [String: JSONValue]
    let outputSchema: [String: JSONValue]
    let generated: Bool
    let status: String
    let version: String
    let createdAt: String
    let sourceFile: String?
    let operation: String?
    let probeInput: [String: JSONValue]
}

struct EndpointRecord: Decodable, Identifiable {
    let id: String
    let name: String
    let method: String
    let path: String
    let description: String
    let owner: String
    let tags: [String]
    let status: String
    let latencyMs: Int
}

struct DataSourceRecord: Decodable, Identifiable {
    let id: String
    let name: String
    let kind: String
    let description: String
    let owner: String
    let status: String
}

struct HealthReport: Decodable {
    let status: String
    let healthy: Int
    let total: Int
    let results: [HealthResult]
    let openai: OpenAIStatus
}

struct OpenAIModelOption: Decodable, Identifiable {
    let id: String
    let label: String
    let role: String
    let description: String
    let reasoningEfforts: [String]
}

struct OpenAIStatus: Decodable {
    let configured: Bool
    let status: String
    let model: String
    let responseModel: String?
    let baseUrl: String
    let reasoningEffort: String?
    let projectConfigured: Bool
    let organizationConfigured: Bool
    let lastCheckedAt: String?
    let lastError: String?
    let lastRequestId: String?
    let modelOptions: [OpenAIModelOption]?

    var effectiveModel: String { responseModel ?? model }
}

struct HealthResult: Decodable, Identifiable {
    var id: String { "\(kind)-\(rawID)" }
    private let rawID: String
    var backendID: String { rawID }
    let kind: String
    let name: String
    let status: String
    let latencyMs: Int
    let checkedAt: String
    let message: String

    enum CodingKeys: String, CodingKey {
        case rawID = "id"
        case kind, name, status, latencyMs, checkedAt, message
    }
}

struct ReconciliationOverview: Decodable {
    let mode: String
    let intervalSeconds: Int
    let lastCheckedAt: String?
    let lastError: String?
    let summary: [String: JSONValue]
}

struct FindingTrigger: Decodable {
    let agent: String
    let action: String
    let status: String
    let detail: String
    let relatedComponentIds: [String]
}

struct ReconciliationFinding: Decodable, Identifiable {
    let id: String
    let key: String
    let kind: String
    let severity: String
    let status: String
    let origin: String
    let title: String
    let detail: String
    let whyItMatters: String
    let agentIds: [String]
    let toolNames: [String]
    let detectedAt: String
    let lastSeenAt: String
    let resolvedAt: String?
    let occurrences: Int
    let trigger: FindingTrigger?
}

struct AgentConversation: Decodable, Identifiable {
    let id: String
    let agentId: String
    let title: String
    let createdAt: String
    let updatedAt: String
    let messages: [ChatMessage]
}

struct ChatMessage: Decodable, Identifiable {
    let id: String
    let role: String
    let content: String
    let createdAt: String
    let toolCalls: [ToolCallRecord]
    let verification: OutputVerification?
    let contextUsed: [String]
    let executionMode: String
    let provider: String
    let endpoint: String?
    let fallbackReason: String?
}

struct ToolCallRecord: Decodable, Identifiable {
    let id: String
    let toolName: String
    let toolId: String?
    let status: String
    let input: [String: JSONValue]
    let output: [String: JSONValue]
    let durationMs: Int
    let provider: String
    let endpoint: String?
}

struct OutputVerification: Decodable {
    let status: String
    let confidence: Double
    let summary: String
    let criteria: [String]
    let evidence: [String]
}

struct ManagerConversation: Decodable, Identifiable {
    let id: String
    let agentId: String
    let title: String
    let autonomy: String
    let createdAt: String
    let updatedAt: String
    let messages: [ManagerMessage]
}

struct ManagerMessage: Decodable, Identifiable {
    let id: String
    let role: String
    let content: String
    let createdAt: String
    let actions: [ManagerAction]
    let changes: [ManagerChange]
    let evaluation: ManagerEvaluation?
    let provider: String
}

struct ManagerAction: Decodable, Identifiable {
    let id: String
    let server: String
    let tool: String
    let status: String
    let title: String
    let detail: String
    let durationMs: Int
    let evidence: [String: JSONValue]
}

struct ManagerChange: Decodable, Identifiable {
    let id: String
    let target: String
    let kind: String
    let summary: String
    let before: String
    let after: String
    let status: String
}

struct ManagerEvaluation: Decodable {
    let status: String
    let summary: String
    let checks: [String]
}

struct BuildRecord: Decodable, Identifiable {
    let id: String
    let prompt: String
    let status: String
    let createdAt: String
    let completedAt: String?
    let tool: ToolRecord?
    let error: String?
}

struct BenchmarkMetric: Decodable, Identifiable {
    let id: String
    let label: String
    let unit: String
    let higherIsBetter: Bool
    let baseline: Double
    let managed: Double
}

struct BenchmarkSideResult: Decodable {
    let status: String
    let toolName: String
    let provider: String?
    let latencyMs: Int
    let outputKeys: [String]
    let error: String?
}

struct BenchmarkScenarioResult: Decodable, Identifiable {
    let id: String
    let title: String
    let objective: String
    let requiredTool: String
    let probeInput: [String: JSONValue]
    let baseline: BenchmarkSideResult
    let managed: BenchmarkSideResult
}

struct BenchmarkRun: Decodable, Identifiable {
    let id: String
    let agentId: String
    let agentName: String
    let status: String
    let createdAt: String
    let baselineLabel: String
    let managedLabel: String
    let summary: String
    let metrics: [BenchmarkMetric]
    let scenarios: [BenchmarkScenarioResult]
    let evidence: [String]
    let error: String?
}

struct WorkspaceEnvelope: Decodable {
    let workspaces: [ConnectedWorkspace]
}

struct ConnectedWorkspace: Decodable, Identifiable {
    let id: String
    let name: String?
    let rootName: String?
    let rootPath: String
    let agentId: String?
    let writable: Bool
    let `default`: Bool
    let files: Int
    let directories: Int
}

struct WorkspaceSummary: Decodable {
    let id: String
    let name: String?
    let rootName: String?
    let rootPath: String
    let agentId: String?
    let writable: Bool?
    let `default`: Bool
    let files: Int
    let directories: Int
}

struct WorkspaceListing: Decodable {
    let rootName: String
    let path: String
    let parent: String?
    let entries: [WorkspaceEntry]
}

struct WorkspaceEntry: Decodable, Identifiable {
    var id: String { path }
    let path: String
    let name: String
    let kind: String
    let size: Int
    let modifiedAt: String?
    let previewable: Bool
}

struct WorkspaceFileContent: Decodable {
    let path: String
    let name: String
    let language: String
    let size: Int
    let content: String
    let truncated: Bool
}

struct DiscoverAllResponse: Decodable {
    let agents: [AgentRecord]
    let toolCount: Int
    let status: String
}

struct ResetResponse: Decodable {
    let status: String
}

struct AgentUpdateRequest: Encodable {
    let name: String
    let description: String
    let owner: String
    let mcpEndpoint: String?
    let instructions: String
    let features: [String]
    let responseStyle: String
    let toolPolicy: String
    let enabledTools: [String]
    let verificationMode: String
    let memoryEnabled: Bool
    let openaiModel: String?
    let openaiReasoningEffort: String?

    enum CodingKeys: String, CodingKey {
        case name, description, owner, mcpEndpoint, instructions, features
        case responseStyle, toolPolicy, enabledTools, verificationMode
        case memoryEnabled, openaiModel, openaiReasoningEffort
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(name, forKey: .name)
        try container.encode(description, forKey: .description)
        try container.encode(owner, forKey: .owner)
        if let mcpEndpoint {
            try container.encode(mcpEndpoint, forKey: .mcpEndpoint)
        } else {
            try container.encodeNil(forKey: .mcpEndpoint)
        }
        try container.encode(instructions, forKey: .instructions)
        try container.encode(features, forKey: .features)
        try container.encode(responseStyle, forKey: .responseStyle)
        try container.encode(toolPolicy, forKey: .toolPolicy)
        try container.encode(enabledTools, forKey: .enabledTools)
        try container.encode(verificationMode, forKey: .verificationMode)
        try container.encode(memoryEnabled, forKey: .memoryEnabled)
        if let openaiModel {
            try container.encode(openaiModel, forKey: .openaiModel)
        } else {
            try container.encodeNil(forKey: .openaiModel)
        }
        if let openaiReasoningEffort {
            try container.encode(
                openaiReasoningEffort,
                forKey: .openaiReasoningEffort
            )
        } else {
            try container.encodeNil(forKey: .openaiReasoningEffort)
        }
    }
}

struct AgentChatRequest: Encodable {
    let agentId: String
    let message: String
    let conversationId: String?
    let contextMode: String
    let toolName: String?
}

struct ManagerChatRequest: Encodable {
    let agentId: String
    let message: String
    let conversationId: String?
    let autonomy: String
}

struct ConnectWorkspaceRequest: Encodable {
    let path: String
    let name: String?
    let agentId: String?
    let writable: Bool
}

struct BenchmarkRequest: Encodable {
    let agentId: String
}

struct AgentImportRequest: Encodable {
    let path: String
    let name: String?
    let description: String?
    let owner: String
    let runCommand: String?
    let mcpEndpoint: String?
    let startAfterImport: Bool
}

struct ImportedAgentProfile: Decodable {
    let indexedFiles: Int
    let languages: [String]
    let detectedEntrypoints: [String]
}

struct AgentProcessStatus: Decodable {
    let agentId: String
    let status: String
    let pid: Int?
    let command: String?
    let startedAt: String?
    let exitCode: Int?
    let logs: [String]
}

struct AgentImportResponse: Decodable {
    let agent: AgentRecord
    let workspace: ConnectedWorkspace
    let profile: ImportedAgentProfile
    let process: AgentProcessStatus
    let alreadyImported: Bool
}

struct AgentProcessStartRequest: Encodable {
    let command: String?
}
