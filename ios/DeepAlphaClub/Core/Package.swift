// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "DeepAlphaCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "DeepAlphaCore", targets: ["DeepAlphaCore"]),
    ],
    targets: [
        .target(
            name: "DeepAlphaCore",
            path: "Sources/Core",
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
        .testTarget(
            name: "CoreTests",
            dependencies: ["DeepAlphaCore"],
            path: "Tests/CoreTests",
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
    ]
)
