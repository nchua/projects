// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "FilmCore",
    platforms: [.iOS(.v26), .macOS(.v26)],
    products: [.library(name: "FilmCore", targets: ["FilmCore"])],
    targets: [
        .target(
            name: "FilmCore",
            resources: [.copy("Resources/film_params.json"), .copy("Resources/print_lut.bin")],
            // The per-pixel loops are ~400× slower unoptimised (film model 91 s vs 0.2 s), which makes Debug
            // runs of the app look hung; FilmCore is always built optimised
            swiftSettings: [.unsafeFlags(["-O"], .when(configuration: .debug))]
        ),
        .testTarget(name: "FilmCoreTests", dependencies: ["FilmCore"]),
    ],
    swiftLanguageModes: [.v5]
)
