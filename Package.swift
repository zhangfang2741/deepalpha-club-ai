// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "DeepAlphaCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "DeepAlphaCore", targets: ["Core"]),
    ],
    targets: [
        .target(
            name: "Core",
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
        .testTarget(
            name: "CoreTests",
            dependencies: ["Core"],
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
    ]
)
