import AppKit
import SwiftUI

struct FilesView: View {
    @EnvironmentObject private var store: AppStore

    @State private var workspaces: [ConnectedWorkspace] = []
    @State private var workspaceID = "default"
    @State private var summary: WorkspaceSummary?
    @State private var listing: WorkspaceListing?
    @State private var selected: WorkspaceFileContent?
    @State private var loading = false
    @State private var connecting = false
    @State private var connectPanel = false
    @State private var path = ""
    @State private var name = ""
    @State private var agentID = ""
    @State private var query = ""
    @State private var type = "all"
    @State private var splitPreview = true

    private var filtered: [WorkspaceEntry] {
        (listing?.entries ?? []).filter { entry in
            (query.isEmpty || entry.name.localizedCaseInsensitiveContains(query))
                && (type == "all"
                    || type == entry.kind
                    || (type == "previewable" && entry.previewable))
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if connectPanel { connectionPanel }
            workspaceBar
            filterBar
            HSplitView {
                fileList.frame(minWidth: 340, idealWidth: 440)
                if splitPreview {
                    preview.frame(minWidth: 420)
                }
            }
        }
        .task {
            await loadWorkspaces()
            await loadDirectory(workspaceID: workspaceID, path: "")
        }
    }

    private var header: some View {
        HStack(alignment: .bottom) {
            PageTitle(
                eyebrow: "LOCAL AGENT CONTEXT",
                title: "Connected workspaces",
                detail: "Connect local directories, browse safe source files, and keep access read-only."
            )
            Spacer()
            Label("READ ONLY", systemImage: "lock.fill")
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppTheme.accent)
            Button {
                withAnimation(.easeInOut(duration: 0.18)) { connectPanel.toggle() }
            } label: {
                Label("Connect Workspace", systemImage: "folder.badge.plus")
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(22)
        .background(AppTheme.surface)
    }

    private var connectionPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .bottom, spacing: 10) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Local folder").font(.caption)
                    Button {
                        chooseFolder()
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: path.isEmpty ? "folder.badge.plus" : "folder.fill")
                                .foregroundStyle(AppTheme.accent)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(path.isEmpty ? "Choose Folder…" : URL(fileURLWithPath: path).lastPathComponent)
                                    .font(.callout.weight(.medium))
                                if !path.isEmpty {
                                    Text(path)
                                        .font(.caption2.monospaced())
                                        .foregroundStyle(AppTheme.secondaryText)
                                        .lineLimit(1)
                                }
                            }
                            Spacer()
                        }
                        .frame(minWidth: 260, alignment: .leading)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                    }
                    .buttonStyle(.bordered)
                    .help(path.isEmpty ? "Choose a local folder in Finder" : "Change the selected folder")
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("Name").font(.caption)
                    TextField("Support agent workspace", text: $name)
                        .textFieldStyle(.roundedBorder)
                }
                .frame(width: 210)
                VStack(alignment: .leading, spacing: 5) {
                    Text("Agent").font(.caption)
                    Picker("Agent", selection: $agentID) {
                        Text("Unassigned").tag("")
                        ForEach(store.agents) { agent in
                            Text(agent.name).tag(agent.id)
                        }
                    }
                    .labelsHidden()
                }
                .frame(width: 190)
                Button(connecting ? "Connecting…" : "Connect") {
                    Task { await connectWorkspace() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(connecting || path.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            Text("The native backend resolves the selected path locally and applies the same secret-file and traversal protections as the website.")
                .font(.caption)
                .foregroundStyle(AppTheme.secondaryText)
        }
        .padding(15)
        .background(AppTheme.raised)
    }

    private var workspaceBar: some View {
        HStack(spacing: 12) {
            Picker("Workspace", selection: $workspaceID) {
                ForEach(workspaces) { workspace in
                    Text(workspace.name ?? workspace.rootName ?? workspace.id)
                        .tag(workspace.id)
                }
            }
            .frame(width: 250)
            .onChange(of: workspaceID) { _, newValue in
                Task { await loadDirectory(workspaceID: newValue, path: "") }
            }

            if let summary {
                Divider().frame(height: 26)
                VStack(alignment: .leading, spacing: 2) {
                    Text(summary.name ?? summary.rootName ?? summary.id)
                        .font(.callout.weight(.semibold))
                    Text(summary.rootPath)
                        .font(.caption.monospaced())
                        .foregroundStyle(AppTheme.secondaryText)
                        .lineLimit(1)
                }
                Spacer()
                Label("\(summary.files) files", systemImage: "doc")
                Label("\(summary.directories) folders", systemImage: "folder")
            } else {
                Spacer()
            }
        }
        .font(.caption)
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(AppTheme.sidebar)
    }

    private var filterBar: some View {
        HStack {
            TextField("Filter this folder", text: $query)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 330)
            Picker("Type", selection: $type) {
                Text("All").tag("all")
                Text("Folders").tag("directory")
                Text("Files").tag("file")
                Text("Previewable").tag("previewable")
            }
            .frame(width: 145)
            Spacer()
            Text("\(filtered.count) results")
                .font(.caption)
                .foregroundStyle(AppTheme.secondaryText)
            Picker("View", selection: $splitPreview) {
                Image(systemName: "rectangle.split.2x1").tag(true)
                Image(systemName: "list.bullet").tag(false)
            }
            .pickerStyle(.segmented)
            .frame(width: 90)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 9)
        .background(AppTheme.surface)
    }

    private var fileList: some View {
        VStack(spacing: 0) {
            breadcrumbs
            Divider()
            if loading {
                Spacer()
                ProgressView("Loading directory…")
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(spacing: 2) {
                        if let parent = listing?.parent {
                            Button {
                                Task { await loadDirectory(workspaceID: workspaceID, path: parent) }
                            } label: {
                                fileRow(
                                    symbol: "arrow.turn.up.left",
                                    name: "Parent directory",
                                    detail: "",
                                    trailing: ""
                                )
                            }
                            .buttonStyle(.plain)
                        }

                        ForEach(filtered) { entry in
                            Button {
                                Task { await open(entry) }
                            } label: {
                                fileRow(
                                    symbol: entry.kind == "directory" ? "folder.fill" : "doc.text",
                                    name: entry.name,
                                    detail: entry.kind == "directory" ? "Folder" : formatSize(entry.size),
                                    trailing: entry.kind == "directory" ? "" : entry.previewable ? "Preview" : "Restricted"
                                )
                            }
                            .buttonStyle(.plain)
                            .background(selected?.path == entry.path ? Color.white.opacity(0.075) : .clear)
                            .clipShape(RoundedRectangle(cornerRadius: 5))
                        }

                        if filtered.isEmpty {
                            ContentUnavailableView.search(text: query)
                                .padding(.top, 80)
                        }
                    }
                    .padding(8)
                }
            }
        }
        .background(AppTheme.background)
    }

    private var breadcrumbs: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 4) {
                Button(listing?.rootName ?? "Workspace") {
                    Task { await loadDirectory(workspaceID: workspaceID, path: "") }
                }
                .buttonStyle(.plain)
                .fontWeight(.semibold)
                let crumbs = listing?.path.split(separator: "/").map(String.init) ?? []
                ForEach(Array(crumbs.enumerated()), id: \.offset) { index, crumb in
                    Image(systemName: "chevron.right")
                        .font(.caption2)
                        .foregroundStyle(AppTheme.secondaryText)
                    Button(crumb) {
                        Task {
                            await loadDirectory(
                                workspaceID: workspaceID,
                                path: crumbs.prefix(index + 1).joined(separator: "/")
                            )
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
            .font(.caption)
            .padding(12)
        }
    }

    private var preview: some View {
        VStack(spacing: 0) {
            if let selected {
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(selected.language.uppercased())
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(AppTheme.accent)
                        Text(selected.name).font(.title3.weight(.semibold))
                        Text("\(selected.path) · \(formatSize(selected.size))\(selected.truncated ? " · truncated" : "")")
                            .font(.caption)
                            .foregroundStyle(AppTheme.secondaryText)
                    }
                    Spacer()
                }
                .padding(15)
                .background(AppTheme.surface)
                Divider()
                ScrollView([.vertical, .horizontal]) {
                    Text(selected.content)
                        .font(.system(size: 12, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .topLeading)
                        .padding(16)
                }
            } else {
                ContentUnavailableView(
                    "Select a File",
                    systemImage: "doc.text",
                    description: Text("Supported text files are shown here. Sensitive filenames remain hidden.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(Color.black.opacity(0.14))
    }

    private func fileRow(
        symbol: String,
        name: String,
        detail: String,
        trailing: String
    ) -> some View {
        HStack(spacing: 10) {
            Image(systemName: symbol)
                .frame(width: 22)
                .foregroundStyle(symbol.contains("folder") ? AppTheme.accent : AppTheme.secondaryText)
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(.callout.weight(.medium))
                if !detail.isEmpty {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondaryText)
                }
            }
            Spacer()
            Text(trailing)
                .font(.caption)
                .foregroundStyle(AppTheme.secondaryText)
            Image(systemName: symbol.contains("folder") ? "chevron.right" : "none")
                .font(.caption)
                .foregroundStyle(AppTheme.secondaryText)
                .opacity(symbol.contains("folder") ? 1 : 0)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .contentShape(Rectangle())
    }

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.canCreateDirectories = false
        panel.resolvesAliases = true
        panel.message = "Choose the local project folder to connect."
        panel.prompt = "Choose Workspace"
        if !path.isEmpty {
            panel.directoryURL = URL(fileURLWithPath: path)
        }
        if panel.runModal() == .OK, let url = panel.url {
            path = url.path
            if name.isEmpty { name = url.lastPathComponent }
        }
    }

    private func loadWorkspaces() async {
        guard let api = store.api else { return }
        do {
            let envelope: WorkspaceEnvelope = try await api.get("/api/workspaces")
            workspaces = envelope.workspaces
            if !workspaces.contains(where: { $0.id == workspaceID }) {
                workspaceID = "default"
            }
        } catch {
            store.show(error.localizedDescription, error: true)
        }
    }

    private func loadDirectory(workspaceID: String, path: String) async {
        guard let api = store.api else { return }
        loading = true
        do {
            async let nextSummary: WorkspaceSummary = api.get("/api/workspaces/\(workspaceID)")
            async let nextListing: WorkspaceListing = api.get(
                "/api/workspaces/\(workspaceID)/files",
                query: [URLQueryItem(name: "path", value: path)]
            )
            summary = try await nextSummary
            listing = try await nextListing
            selected = nil
            query = ""
        } catch {
            store.show(error.localizedDescription, error: true)
        }
        loading = false
    }

    private func connectWorkspace() async {
        guard let api = store.api else { return }
        connecting = true
        do {
            let connected: ConnectedWorkspace = try await api.post(
                "/api/workspaces/connect",
                body: ConnectWorkspaceRequest(
                    path: path,
                    name: name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : name,
                    agentId: agentID.isEmpty ? nil : agentID,
                    writable: false
                )
            )
            await loadWorkspaces()
            workspaceID = connected.id
            path = ""
            name = ""
            agentID = ""
            connectPanel = false
            await loadDirectory(workspaceID: connected.id, path: "")
            store.show("Connected \(connected.name ?? connected.rootName ?? "workspace").")
        } catch {
            store.show(error.localizedDescription, error: true)
        }
        connecting = false
    }

    private func open(_ entry: WorkspaceEntry) async {
        if entry.kind == "directory" {
            await loadDirectory(workspaceID: workspaceID, path: entry.path)
            return
        }
        guard entry.previewable else {
            store.show("This file type is not available for safe preview.", error: true)
            return
        }
        guard let api = store.api else { return }
        do {
            selected = try await api.get(
                "/api/workspaces/\(workspaceID)/file",
                query: [URLQueryItem(name: "path", value: entry.path)]
            )
            splitPreview = true
        } catch {
            store.show(error.localizedDescription, error: true)
        }
    }

    private func formatSize(_ bytes: Int) -> String {
        if bytes == 0 { return "-" }
        if bytes < 1024 { return "\(bytes) B" }
        if bytes < 1_048_576 { return String(format: "%.1f KB", Double(bytes) / 1024) }
        return String(format: "%.1f MB", Double(bytes) / 1_048_576)
    }
}
