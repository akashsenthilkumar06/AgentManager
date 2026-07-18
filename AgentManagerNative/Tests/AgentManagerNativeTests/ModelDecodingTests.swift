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
    func decodesFinanceCorrection() throws {
        let data = Data(
            """
            {
              "data_source": "local-demo-data",
              "table": "finance_invoices",
              "rows_reviewed": 3,
              "employee_analysis": {
                "invoice_ids": ["INV-2048"],
                "overdue_total": 1840.5,
                "highest_priority_invoice": "INV-2048",
                "recommendation": "Contact Acme first.",
                "mode": "intentional-demo-failure"
              },
              "manager_review": {
                "status": "correction_required",
                "missed_invoice_ids": ["INV-3019"],
                "expected_overdue_total": 4090.5,
                "reported_overdue_total": 1840.5,
                "reason": "Missing overdue invoice."
              },
              "corrected_analysis": {
                "invoice_ids": ["INV-2048", "INV-3019"],
                "overdue_total": 4090.5,
                "highest_priority_invoice": "INV-3019",
                "recommendation": "Contact Northstar first."
              }
            }
            """.utf8
        )

        let result = try decoder.decode(FinanceCorrectionResult.self, from: data)
        #expect(result.managerReview.status == "correction_required")
        #expect(result.correctedAnalysis.invoiceIds.count == 2)
    }
}
