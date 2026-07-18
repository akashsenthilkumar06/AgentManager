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
                    await Task.yield()
                    NSApp.setActivationPolicy(.regular)
                    NSApp.activate(ignoringOtherApps: true)
                    if ProcessInfo.processInfo.environment["AGENT_MANAGER_INITIAL_SECTION"] != nil {
                        NSApp.windows.first(where: { $0.canBecomeKey })?.center()
                    }
                    if let window = NSApp.windows.first(where: { $0.canBecomeKey }) {
                        window.makeMain()
                        window.makeKeyAndOrderFront(nil)
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
