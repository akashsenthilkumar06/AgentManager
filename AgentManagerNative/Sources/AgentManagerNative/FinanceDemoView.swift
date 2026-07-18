import SwiftUI

struct FinanceDemoView: View {
    @EnvironmentObject private var store: AppStore
    @State private var result: FinanceCorrectionResult?
    @State private var running = false

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .bottom) {
                PageTitle(
                    eyebrow: "SOURCE-BACKED DEMO",
                    title: "Finance correction",
                    detail: "Watch an employee agent make a measurable mistake, then see the Manager independently check the finance source and correct it."
                )
                Spacer()
                Button {
                    Task { await runDemo() }
                } label: {
                    Label(
                        running ? "Checking Finance Data…" : "Run Finance Demo",
                        systemImage: "play.fill"
                    )
                }
                .buttonStyle(.borderedProminent)
                .disabled(running)
            }
            .padding(22)
            .background(AppTheme.surface)

            ScrollView {
                if let result {
                    resultGrid(result)
                        .padding(24)
                        .frame(maxWidth: 1180)
                        .frame(maxWidth: .infinity)
                } else {
                    emptyState
                        .padding(24)
                        .frame(maxWidth: 920)
                        .frame(maxWidth: .infinity)
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 14) {
            Image(systemName: "dollarsign.circle")
                .font(.system(size: 38))
                .foregroundStyle(AppTheme.accent)
            Text("Ready for the Manager review")
                .font(.title2.weight(.semibold))
            Text("The run intentionally omits one overdue invoice when two or more are present. The Manager compares that answer with the same finance source and returns the corrected total.")
                .foregroundStyle(AppTheme.secondaryText)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 620)
            Button("Run Demo") {
                Task { await runDemo() }
            }
            .buttonStyle(.borderedProminent)
            .disabled(running)
        }
        .frame(maxWidth: .infinity, minHeight: 390)
        .liquidGlass(cornerRadius: 20, interactive: true)
    }

    private func resultGrid(_ result: FinanceCorrectionResult) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Label(
                    result.dataSource == "supabase" ? "Supabase connected" : "Local demo fallback",
                    systemImage: result.dataSource == "supabase" ? "cloud.fill" : "internaldrive"
                )
                .font(.headline)
                Spacer()
                Text("\(result.rowsReviewed) source rows")
                    .font(.caption.monospaced())
                    .foregroundStyle(AppTheme.secondaryText)
            }
            .padding(14)
            .liquidGlass(cornerRadius: 14)

            HStack(alignment: .top, spacing: 16) {
                sourceCard(result)
                analysisCard(
                    eyebrow: "2 · EMPLOYEE ANSWER",
                    title: "Incomplete analysis",
                    analysis: result.employeeAnalysis,
                    tone: AppTheme.danger,
                    footer: result.employeeAnalysis.recommendation
                )
                analysisCard(
                    eyebrow: "3 · MANAGER CORRECTION",
                    title: result.managerReview.status == "correction_required"
                        ? "Failure detected"
                        : "Answer verified",
                    analysis: result.correctedAnalysis,
                    tone: AppTheme.accent,
                    footer: result.managerReview.reason,
                    missed: result.managerReview.missedInvoiceIds
                )
            }
        }
    }

    private func sourceCard(_ result: FinanceCorrectionResult) -> some View {
        VStack(alignment: .leading, spacing: 13) {
            Text("1 · FINANCE SOURCE")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(AppTheme.accent)
            Text(result.dataSource == "supabase" ? "Supabase connected" : "Local demo fallback")
                .font(.title3.weight(.semibold))
            Text("Read \(result.rowsReviewed) rows from the source. The query runs server-side, so database secrets never enter the app UI.")
                .foregroundStyle(AppTheme.secondaryText)
            Text(result.table)
                .font(.callout.monospaced())
                .padding(9)
                .background(Color.black.opacity(0.18))
                .clipShape(RoundedRectangle(cornerRadius: 7))
            Spacer()
            Label("Data source: \(result.dataSource)", systemImage: "lock.shield")
                .font(.caption)
                .foregroundStyle(AppTheme.secondaryText)
        }
        .padding(20)
        .frame(maxWidth: .infinity, minHeight: 300, alignment: .topLeading)
        .surface()
    }

    private func analysisCard(
        eyebrow: String,
        title: String,
        analysis: FinanceAnalysis,
        tone: Color,
        footer: String,
        missed: [String] = []
    ) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(eyebrow)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(tone)
            Text(title).font(.title3.weight(.semibold))
            Text(currency(analysis.overdueTotal))
                .font(.system(size: 34, weight: .bold, design: .rounded))
                .foregroundStyle(tone)
            Text("Invoices: \(analysis.invoiceIds.joined(separator: ", "))")
                .font(.callout.monospaced())
            Text(footer)
                .font(.caption)
                .foregroundStyle(AppTheme.secondaryText)
            Spacer()
            if !missed.isEmpty {
                Label(
                    "Missed: \(missed.joined(separator: ", "))",
                    systemImage: "exclamationmark.triangle.fill"
                )
                .font(.caption.monospaced())
                .foregroundStyle(AppTheme.danger)
                .padding(9)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(AppTheme.danger.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 7))
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, minHeight: 300, alignment: .topLeading)
        .background(tone.opacity(0.045))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(tone.opacity(0.3)))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func currency(_ value: Double) -> String {
        value.formatted(.currency(code: "USD"))
    }

    private func runDemo() async {
        guard let api = store.api else { return }
        running = true
        do {
            let next: FinanceCorrectionResult = try await api.post(
                "/api/demos/finance-correction"
            )
            result = next
            store.show(
                next.dataSource == "supabase"
                    ? "Supabase finance demo completed."
                    : "Local finance demo completed."
            )
        } catch {
            store.show(error.localizedDescription, error: true)
        }
        running = false
    }
}
