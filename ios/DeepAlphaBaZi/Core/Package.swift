// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "DeepAlphaBaZiCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "DeepAlphaBaZiCore", targets: ["DeepAlphaBaZiCore"]),
    ],
    targets: [
        .target(
            name: "DeepAlphaBaZiCore",
            path: "Sources/Core",
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
        .testTarget(
            name: "CoreTests",
            dependencies: ["DeepAlphaBaZiCore"],
            path: "Tests/CoreTests",
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
    ]
)
