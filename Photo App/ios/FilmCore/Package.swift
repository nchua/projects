// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "FilmCore",
    platforms: [.iOS(.v26), .macOS(.v26)],
    products: [.library(name: "FilmCore", targets: ["FilmCore"])],
    targets: [
        .target(
            name: "FilmCore",
            resources: [.copy("Resources/film_params.json"), .copy("Resources/print_lut.bin")]
        ),
        .testTarget(name: "FilmCoreTests", dependencies: ["FilmCore"]),
    ],
    swiftLanguageModes: [.v5]
)
