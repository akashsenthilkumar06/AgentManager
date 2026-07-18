import SwiftUI

struct RootView: View {
    @EnvironmentObject private var store: AppStore
    @State private var showingResetConfirmation = false
    @State private var columnVisibility: NavigationSplitViewVisibility = .all

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Group {
                if store.loading {
                    loadingView
                } else if store.overview == nil {
                    connectionError
                } else {
                    appShell
                }
            }

            if let notice = store.notice {
                toast(notice, isError: false)
                    .padding(18)
                    .transition(.move(edge: .top).combined(with: .opacity))
            } else if let error = store.errorMessage, store.overview != nil {
                toast(error, isError: true)
                    .padding(18)
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .onTapGesture { store.errorMessage = nil }
            }
        }
        .background(AppTheme.background)
        .tint(AppTheme.accent)
        .confirmationDialog(
            "Reset the native demo workspace?",
            isPresented: $showingResetConfirmation
        ) {
            Button("Reset Demo", role: .destructive) {
                Task { await store.resetDemo() }
            }
        } message: {
            Text("This removes conversations, connected workspaces, and generated tools from the native app's isolated runtime only.")
        }
        .task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(15))
                if store.overview != nil {
                    try? await store.refresh()
                }
            }
        }
    }

    private var appShell: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            appSidebar
                .navigationSplitViewColumnWidth(min: 205, ideal: 224, max: 248)
        } detail: {
            detailView
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(AppTheme.background)
        }
        .navigationSplitViewStyle(.balanced)
    }

    private var appSidebar: some View {
        VStack(spacing: 0) {
            HStack(spacing: 11) {
                RoundedRectangle(cornerRadius: 9)
                    .fill(Color.white.opacity(0.1))
                    .frame(width: 34, height: 34)
                    .overlay(
                        Image(systemName: "wand.and.stars")
                            .foregroundStyle(.white.opacity(0.9))
                    )
                VStack(alignment: .leading, spacing: 1) {
                    Text("Agent Manager")
                        .font(.headline)
                    Text("Native workspace")
                        .font(.caption2)
                        .foregroundStyle(AppTheme.secondaryText)
                }
                Spacer()
            }
            .padding(.horizontal, 14)
            .padding(.top, 18)
            .padding(.bottom, 20)

            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(AppSection.allCases) { section in
                        sidebarButton(section)
                    }
                }
                .padding(.horizontal, 9)
            }

            Spacer()
            HStack(spacing: 9) {
                StatusDot(status: store.health?.status ?? "degraded")
                Text(store.health?.status == "healthy" ? "Systems operational" : "Needs attention")
                    .font(.caption.weight(.medium))
                Spacer()
                Menu {
                    Button {
                        Task { await store.refreshShowingErrors() }
                    } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                    Button(role: .destructive) {
                        showingResetConfirmation = true
                    } label: {
                        Label("Reset Workspace", systemImage: "arrow.counterclockwise")
                    }
                } label: {
                    Image(systemName: "ellipsis")
                        .foregroundStyle(AppTheme.secondaryText)
                        .frame(width: 24, height: 24)
                }
                .menuStyle(.borderlessButton)
            }
            .padding(14)
            .overlay(alignment: .top) { Divider() }
        }
        .background(AppTheme.sidebar)
    }

    private func sidebarButton(_ section: AppSection) -> some View {
        Button {
            store.section = section
        } label: {
            HStack(spacing: 11) {
                Image(systemName: section.symbol)
                    .frame(width: 18)
                    .foregroundStyle(
                        store.section == section
                            ? Color.white
                            : AppTheme.secondaryText
                    )
                Text(section.title)
                    .font(.callout.weight(store.section == section ? .semibold : .regular))
                Spacer()
            }
            .padding(.horizontal, 11)
            .padding(.vertical, 9)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .background(
            store.section == section
                ? Color.white.opacity(0.09)
                : Color.clear
        )
        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
    }

    @ViewBuilder
    private var detailView: some View {
        switch store.section ?? .dashboard {
        case .dashboard:
            DashboardView()
        case .workspace:
            WorkspaceView()
        case .agents:
            AgentsView()
        case .benchmarks:
            BenchmarksView()
        case .activity:
            ActivityView()
        case .health:
            HealthView()
        }
    }

    private var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView().controlSize(.large)
            Text("Starting native Agent Manager")
                .font(.headline)
            Text("Connecting the isolated backend and loading your agents.")
                .foregroundStyle(AppTheme.secondaryText)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var connectionError: some View {
        VStack(spacing: 14) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 34))
                .foregroundStyle(AppTheme.warning)
            Text("Could not start Agent Manager")
                .font(.title2.weight(.semibold))
            Text(store.errorMessage ?? "Unknown startup error")
                .foregroundStyle(AppTheme.secondaryText)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 520)
            Button("Try Again") {
                store.errorMessage = nil
                Task { await store.start() }
            }
            .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func toast(_ message: String, isError: Bool) -> some View {
        HStack(spacing: 9) {
            Image(systemName: isError ? "exclamationmark.circle.fill" : "checkmark.circle.fill")
                .foregroundStyle(isError ? AppTheme.danger : AppTheme.accent)
            Text(message).font(.callout)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .background(.regularMaterial)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(AppTheme.border))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .shadow(radius: 16)
    }
}
