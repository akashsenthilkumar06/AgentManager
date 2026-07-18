import Foundation
import Testing
@testable import AgentManagerNative

struct ModelDecodingTests {
    private var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    @Test
    func decodesOpenAIProviderStatus() throws {
        let data = Data(
            """
            {
              "configured": false,
              "status": "not_configured",
              "model": "gpt-5.6-terra",
              "response_model": null,
              "base_url": "https://api.openai.com/v1",
              "reasoning_effort": "low",
              "project_configured": false,
              "organization_configured": false,
              "last_checked_at": null,
              "last_error": null,
              "last_request_id": null,
              "model_options": [
                {
                  "id": "gpt-5.6-sol",
                  "label": "GPT-5.6 Sol",
                  "role": "Frontier",
                  "description": "Quality-first agent work.",
                  "reasoning_efforts": ["none", "low", "high"]
                }
              ]
            }
            """.utf8
        )

        let status = try decoder.decode(OpenAIStatus.self, from: data)
        #expect(status.model == "gpt-5.6-terra")
        #expect(status.baseUrl == "https://api.openai.com/v1")
        #expect(status.modelOptions?.first?.id == "gpt-5.6-sol")
    }

    @Test
    func agentUpdateEncodesModelSelectionsAndExplicitDefaults() throws {
        let base = AgentUpdateRequest(
            name: "Finance Agent",
            description: "A realistic finance analysis agent.",
            owner: "Local workspace",
            mcpEndpoint: nil,
            instructions: "Use live evidence before answering.",
            features: ["Finance"],
            responseStyle: "balanced",
            toolPolicy: "automatic",
            enabledTools: [],
            verificationMode: "balanced",
            memoryEnabled: true,
            openaiModel: nil,
            openaiReasoningEffort: nil
        )
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let defaults = try JSONSerialization.jsonObject(
            with: encoder.encode(base)
        ) as? [String: Any]

        #expect(defaults?["openai_model"] is NSNull)
        #expect(defaults?["openai_reasoning_effort"] is NSNull)
        #expect(defaults?["mcp_endpoint"] is NSNull)

        let selected = AgentUpdateRequest(
            name: base.name,
            description: base.description,
            owner: base.owner,
            mcpEndpoint: "http://127.0.0.1:8080/mcp",
            instructions: base.instructions,
            features: base.features,
            responseStyle: base.responseStyle,
            toolPolicy: base.toolPolicy,
            enabledTools: base.enabledTools,
            verificationMode: base.verificationMode,
            memoryEnabled: base.memoryEnabled,
            openaiModel: "gpt-5.6-sol",
            openaiReasoningEffort: "high"
        )
        let choices = try JSONSerialization.jsonObject(
            with: encoder.encode(selected)
        ) as? [String: Any]

        #expect(choices?["openai_model"] as? String == "gpt-5.6-sol")
        #expect(choices?["openai_reasoning_effort"] as? String == "high")
    }
}
