// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "AgentManagerNative",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "AgentManagerNative", targets: ["AgentManagerNative"])
    ],
    targets: [
        .executableTarget(
            name: "AgentManagerNative",
            path: "Sources/AgentManagerNative"
        ),
        .testTarget(
            name: "AgentManagerNativeTests",
            dependencies: ["AgentManagerNative"],
            path: "Tests/AgentManagerNativeTests"
        )
    ]
)
