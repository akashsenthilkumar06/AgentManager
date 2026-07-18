import SwiftUI

struct BenchmarksView: View {
    @EnvironmentObject private var store: AppStore

    @State private var runs: [BenchmarkRun] = []
    @State private var selectedRunID: String?
    @State private var running = false
    @State private var loading = false

    private var agentID: String {
        store.selectedAgentID ?? store.agents.first?.id ?? ""
    }

    private var agentRuns: [BenchmarkRun] {
        runs.filter { $0.agentId == agentID }
    }

    private var run: BenchmarkRun? {
        agentRuns.first { $0.id == selectedRunID } ?? agentRuns.first
    }

    private var score: BenchmarkMetric? {
        run?.metrics.first { $0.id == "overall_score" }
    }

    var body: some View {
        VStack(spacing: 0) {
            compactHeader
            if loading {
                Spacer()
                ProgressView("Loading benchmark history…")
                Spacer()
            } else {
                ScrollView {
                    if let run {
                        results(run)
                    } else {
                        emptyState
                    }
                }
            }
        }
        .task { await load() }
    }

    private var compactHeader: some View {
        HStack(spacing: 12) {
            Image(systemName: "chart.bar.xaxis")
                .font(.title3)
                .foregroundStyle(AppTheme.accent)
            VStack(alignment: .leading, spacing: 1) {
                Text("Agent benchmarks").font(.headline)
                Text("Measured baseline versus Manager-enhanced behavior")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondaryText)
            }
            Spacer()
            Picker("Agent", selection: Binding(
                get: { agentID },
                set: {
                    store.selectedAgentID = $0
                    let selectedAgentID = $0
                    selectedRunID = runs.first {
                        $0.agentId == selectedAgentID
                    }?.id
                }
            )) {
                ForEach(store.agents) { agent in
                    Text(agent.name).tag(agent.id)
                }
            }
            .labelsHidden()
            .frame(width: 220)

            if !agentRuns.isEmpty {
                Picker("Run", selection: Binding(
                    get: { selectedRunID ?? agentRuns.first?.id ?? "" },
                    set: { selectedRunID = $0 }
                )) {
                    ForEach(agentRuns) { item in
                        Text(item.createdAt.shortTimestamp).tag(item.id)
                    }
                }
                .labelsHidden()
                .frame(width: 170)
            }

            Button {
                Task { await runBenchmark() }
            } label: {
                Label(running ? "Running…" : "Run Benchmark", systemImage: "play.fill")
            }
            .buttonStyle(.borderedProminent)
            .disabled(running || agentID.isEmpty)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 11)
        .background(.ultraThinMaterial)
    }

    private func results(_ run: BenchmarkRun) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top, spacing: 18) {
                VStack(alignment: .leading, spacing: 10) {
                    Text("LATEST COMPARISON")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(AppTheme.accent)
                    Text(run.agentName).font(.title2.weight(.semibold))
                    Text(run.summary).foregroundStyle(AppTheme.secondaryText)
                    FlowLayout(spacing: 7) {
                        ForEach(run.evidence, id: \.self) { item in
                            Label(item, systemImage: "checkmark")
                                .font(.caption)
                                .padding(.horizontal, 9)
                                .padding(.vertical, 6)
                                .background(Color.white.opacity(0.05))
                                .clipShape(Capsule())
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                if let score {
                    HStack(spacing: 22) {
                        scoreValue(run.baselineLabel, score.baseline)
                        Image(systemName: "arrow.right")
                            .foregroundStyle(AppTheme.secondaryText)
                        scoreValue(run.managedLabel, score.managed)
                    }
                }
            }
            .padding(20)
            .liquidGlass(cornerRadius: 18)

            Text("Measured performance")
                .font(.title3.weight(.semibold))

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 250), spacing: 12)],
                spacing: 12
            ) {
                ForEach(run.metrics.filter { $0.id != "overall_score" }) { metric in
                    metricCard(metric)
                }
            }

            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("Scenario evidence").font(.title3.weight(.semibold))
                    Spacer()
                    Text("\(run.scenarios.count) identical probes")
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                }

                ForEach(run.scenarios) { scenario in
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(scenario.requiredTool)
                                    .font(.callout.monospaced().weight(.semibold))
                                Text(scenario.objective)
                                    .font(.caption)
                                    .foregroundStyle(AppTheme.secondaryText)
                            }
                            Spacer()
                            Text(JSONValue.object(scenario.probeInput).prettyPrinted)
                                .font(.caption2.monospaced())
                                .foregroundStyle(AppTheme.secondaryText)
                                .lineLimit(2)
                        }
                        HStack(spacing: 10) {
                            sideResult(run.baselineLabel, scenario.baseline)
                            sideResult(run.managedLabel, scenario.managed)
                        }
                    }
                    .surface(14)
                }
            }
        }
        .padding(22)
        .frame(maxWidth: 1180)
        .frame(maxWidth: .infinity)
    }

    private var emptyState: some View {
        ContentUnavailableView {
            Label("Measure the Manager’s Effect", systemImage: "chart.bar.xaxis")
        } description: {
            Text("Run identical executable scenarios against the original and current agent configurations.")
        } actions: {
            Button("Run First Benchmark") {
                Task { await runBenchmark() }
            }
            .buttonStyle(.borderedProminent)
            .disabled(running || agentID.isEmpty)
        }
        .frame(maxWidth: .infinity, minHeight: 560)
    }

    private func scoreValue(_ label: String, _ value: Double) -> some View {
        VStack(spacing: 4) {
            Text(label)
                .font(.caption)
                .foregroundStyle(AppTheme.secondaryText)
                .lineLimit(1)
            Text("\(Int(value.rounded()))")
                .font(.system(size: 42, weight: .semibold, design: .rounded))
            Text("score").font(.caption2).foregroundStyle(AppTheme.secondaryText)
        }
        .frame(width: 150)
    }

    private func metricCard(_ metric: BenchmarkMetric) -> some View {
        let delta = metric.managed - metric.baseline
        let improved = metric.higherIsBetter ? delta > 0 : delta < 0
        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(metric.label).font(.callout.weight(.semibold))
                Spacer()
                Text(delta == 0 ? "No change" : String(format: "%+.1f", delta))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(improved ? AppTheme.accent : AppTheme.secondaryText)
            }
            ProgressView(value: normalized(metric.baseline, metric: metric))
                .tint(Color.white.opacity(0.3))
            HStack {
                Text("Baseline \(formatted(metric.baseline, unit: metric.unit))")
                Spacer()
                Text("Managed \(formatted(metric.managed, unit: metric.unit))")
            }
            .font(.caption)
            .foregroundStyle(AppTheme.secondaryText)
            ProgressView(value: normalized(metric.managed, metric: metric))
                .tint(AppTheme.accent)
        }
        .surface(14)
    }

    private func sideResult(_ label: String, _ result: BenchmarkSideResult) -> some View {
        HStack {
            StatusDot(status: result.status)
            VStack(alignment: .leading, spacing: 2) {
                Text(label).font(.caption.weight(.semibold)).lineLimit(1)
                Text(result.status == "passed"
                     ? "\(result.toolName) · \(result.latencyMs) ms"
                     : result.error ?? result.status.capitalized)
                    .font(.caption2)
                    .foregroundStyle(AppTheme.secondaryText)
                    .lineLimit(2)
            }
            Spacer()
        }
        .padding(10)
        .frame(maxWidth: .infinity)
        .background(Color.white.opacity(0.035))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func normalized(_ value: Double, metric: BenchmarkMetric) -> Double {
        if metric.unit == "milliseconds" {
            return max(0, min(1, value / max(metric.baseline, metric.managed, 1)))
        }
        return max(0, min(1, value / 100))
    }

    private func formatted(_ value: Double, unit: String) -> String {
        unit == "milliseconds" ? "\(Int(value.rounded())) ms" : "\(Int(value.rounded()))%"
    }

    private func load() async {
        guard let api = store.api else { return }
        loading = true
        do {
            let loaded: [BenchmarkRun] = try await api.get("/api/benchmarks")
            runs = loaded
            selectedRunID = loaded.first { $0.agentId == agentID }?.id
        } catch {
            store.show(error.localizedDescription, error: true)
        }
        loading = false
    }

    private func runBenchmark() async {
        guard let api = store.api, !agentID.isEmpty else { return }
        running = true
        do {
            let next: BenchmarkRun = try await api.post(
                "/api/benchmarks",
                body: BenchmarkRequest(agentId: agentID)
            )
            runs = [next] + runs.filter { $0.id != next.id }
            selectedRunID = next.id
            try await store.refresh()
            store.show("Benchmark completed for \(next.agentName).")
        } catch {
            store.show(error.localizedDescription, error: true)
        }
        running = false
    }
}
