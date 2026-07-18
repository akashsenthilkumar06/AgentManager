import Darwin
import Foundation

@MainActor
final class BackendController {
    private var process: Process?
    private(set) var baseURL: URL?

    func start() async throws -> URL {
        if let baseURL { return baseURL }

        let environment = ProcessInfo.processInfo.environment
        let backendRoot = try findBackendRoot(environment: environment)
        let runtime = try runtimeRoot(environment: environment)
        let port = try availablePort(startingAt: Int(environment["AGENT_MANAGER_BACKEND_PORT"] ?? "8000") ?? 8000)
        let python = try findPython(backendRoot: backendRoot)

        try FileManager.default.createDirectory(
            at: runtime.appending(path: "data"),
            withIntermediateDirectories: true
        )
        try FileManager.default.createDirectory(
            at: runtime.appending(path: "generated_tools"),
            withIntermediateDirectories: true
        )

        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = [
            "-m", "uvicorn", "backend.app.main:app",
            "--host", "127.0.0.1",
            "--port", String(port)
        ]
        process.currentDirectoryURL = backendRoot
        var childEnvironment = environment
        childEnvironment["PYTHONUNBUFFERED"] = "1"
        childEnvironment["PYTHONDONTWRITEBYTECODE"] = "1"
        if childEnvironment["AGENT_MANAGER_ENV_FILE"] == nil,
           let envFile = defaultEnvFile(runtime: runtime) {
            childEnvironment["AGENT_MANAGER_ENV_FILE"] = envFile.path
        }
        childEnvironment["AGENT_MANAGER_DATA_DIR"] = runtime.appending(path: "data").path
        childEnvironment["AGENT_MANAGER_GENERATED_DIR"] = runtime.appending(path: "generated_tools").path
        childEnvironment["AGENT_MANAGER_WORKSPACE_ROOT"] =
            environment["AGENT_MANAGER_WORKSPACE_ROOT"] ?? backendRoot.path
        process.environment = childEnvironment
        process.standardOutput = FileHandle.standardError
        process.standardError = FileHandle.standardError
        try process.run()
        self.process = process

        let url = URL(string: "http://127.0.0.1:\(port)")!
        for _ in 0..<80 {
            if !process.isRunning {
                throw APIError(message: "The Agent Manager backend stopped during startup.")
            }
            if let (_, response) = try? await URLSession.shared.data(
                from: url.appending(path: "/api/health")
            ), let http = response as? HTTPURLResponse, http.statusCode == 200 {
                baseURL = url
                return url
            }
            try await Task.sleep(for: .milliseconds(125))
        }
        stop()
        throw APIError(message: "Timed out while starting the Agent Manager backend.")
    }

    func stop() {
        guard let process else { return }
        if process.isRunning {
            process.terminate()
        }
        self.process = nil
        baseURL = nil
    }

    private func findBackendRoot(environment: [String: String]) throws -> URL {
        var candidates: [URL] = []
        if let configured = environment["AGENT_MANAGER_PROJECT_ROOT"] {
            candidates.append(URL(fileURLWithPath: configured))
        }
        if let bundled = Bundle.main.resourceURL?.appending(path: "Backend") {
            candidates.append(bundled)
        }
        candidates.append(URL(fileURLWithPath: FileManager.default.currentDirectoryPath))

        for candidate in candidates {
            if FileManager.default.fileExists(
                atPath: candidate.appending(path: "backend/app/main.py").path
            ) {
                return candidate.standardizedFileURL
            }
        }
        throw APIError(
            message: "The bundled Agent Manager backend could not be found. Rebuild the app with scripts/package_native_app.sh."
        )
    }

    private func runtimeRoot(environment: [String: String]) throws -> URL {
        if let configured = environment["AGENT_MANAGER_NATIVE_ROOT"] {
            return URL(fileURLWithPath: configured).appending(path: "Runtime")
        }
        let applicationSupport = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        return applicationSupport.appending(path: "Agent Manager", directoryHint: .isDirectory)
    }

    private func defaultEnvFile(runtime: URL) -> URL? {
        let candidates = [
            runtime.appending(path: ".env"),
            Bundle.main.bundleURL
                .deletingLastPathComponent()
                .appending(path: ".env"),
        ]
        return candidates.first {
            FileManager.default.fileExists(atPath: $0.path)
        }
    }

    private func findPython(backendRoot: URL) throws -> String {
        let environment = ProcessInfo.processInfo.environment
        var candidates = [
            environment["AGENT_MANAGER_PYTHON"],
            backendRoot.appending(path: ".venv/bin/python").path,
            "/opt/homebrew/bin/python3",
            "/opt/anaconda3/bin/python",
            "/usr/local/bin/python3",
            "/usr/bin/python3"
        ].compactMap { $0 }

        if let path = environment["PATH"] {
            for directory in path.split(separator: ":") {
                candidates.append(URL(fileURLWithPath: String(directory)).appending(path: "python3").path)
                candidates.append(URL(fileURLWithPath: String(directory)).appending(path: "python").path)
            }
        }

        for candidate in Array(Set(candidates)) where FileManager.default.isExecutableFile(atPath: candidate) {
            let probe = Process()
            probe.executableURL = URL(fileURLWithPath: candidate)
            probe.arguments = ["-c", "import fastapi, uvicorn, httpx, dotenv"]
            probe.standardOutput = FileHandle.nullDevice
            probe.standardError = FileHandle.nullDevice
            do {
                try probe.run()
                probe.waitUntilExit()
                if probe.terminationStatus == 0 { return candidate }
            } catch {
                continue
            }
        }
        throw APIError(message: "No Python interpreter with FastAPI and Uvicorn was found.")
    }

    private func availablePort(startingAt preferred: Int) throws -> Int {
        for port in preferred..<(preferred + 50) {
            let descriptor = socket(AF_INET, SOCK_STREAM, 0)
            guard descriptor >= 0 else { continue }
            var address = sockaddr_in()
            address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
            address.sin_family = sa_family_t(AF_INET)
            address.sin_port = in_port_t(port).bigEndian
            address.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))
            let result = withUnsafePointer(to: &address) {
                $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    bind(descriptor, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
                }
            }
            close(descriptor)
            if result == 0 { return port }
        }
        throw APIError(message: "No local backend port is available.")
    }

    deinit {
        if let process, process.isRunning {
            process.terminate()
        }
    }
}
