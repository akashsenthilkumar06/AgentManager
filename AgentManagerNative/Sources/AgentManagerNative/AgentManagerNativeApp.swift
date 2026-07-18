import SwiftUI

@main
struct AgentManagerNativeApp: App {
    @StateObject private var store = AppStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .preferredColorScheme(.dark)
                .task {
                    await store.start()
                    if ProcessInfo.processInfo.environment["AGENT_MANAGER_INITIAL_SECTION"] != nil {
                        await Task.yield()
                        NSApp.windows.first?.center()
                        NSApp.windows.first?.makeKeyAndOrderFront(nil)
                        NSApp.activate(ignoringOtherApps: true)
                    }
                }
                .onReceive(NotificationCenter.default.publisher(
                    for: NSApplication.willTerminateNotification
                )) { _ in
                    store.stop()
                }
        }
        .defaultSize(width: 1380, height: 860)
        .windowStyle(.hiddenTitleBar)
        .commands {
            CommandGroup(after: .sidebar) {
                Button("Refresh All") {
                    Task { await store.refreshShowingErrors() }
                }
                .keyboardShortcut("r", modifiers: [.command])
            }
        }
    }
}
