import CoreLocation
import FilmCore
import Foundation
import os

/// One finished render: the JPEGs in tmp until saved or cleared, plus what Save and the Debug overlay need.
struct Rendered: Sendable {
    let renderURL: URL
    let comparisonURL: URL?
    let captureDate: Date?
    let location: CLLocation?
    let metering: String
    let decodeSeconds: Double
    let filmSeconds: Double
    let encodeSeconds: Double
    let megapixels: Double
    let peakFootprint: UInt64
}

enum RenderError: Error, CustomStringConvertible {
    case insufficientMemory(needed: UInt64, available: UInt64)

    var description: String {
        switch self {
        case .insufficientMemory(let needed, let available):
            "Not enough free memory (needs \(needed >> 20) MB, \(available >> 20) MB available) — skipped"
        }
    }
}

/// Owns the Core Image context, film params and LUT; renders one photo at a time (APP_SPEC.md M3).
actor Renderer {
    static let software = "Print \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0")"
    /// §7 peak-footprint budgets, used as the free-memory pre-check.
    static let budget12MP: UInt64 = 600 << 20, budget48MP: UInt64 = 1536 << 20
    static let stripsPer12MP = 16   // Mac proxy: 8 strips peaked at 683 MB on 12 MP (budget 600), 16 at 576

    let model: FilmModel
    let decoder: Decoder

    init() throws {
        model = try FilmModel.bundled()
        decoder = Decoder(params: model.params)
    }

    func render(dng: URL, into dir: URL) throws -> Rendered {
        let pixels = Decoder.nativePixelCount(dng) ?? 12_000_000
        let large = pixels > 20_000_000
        try Self.checkMemory(needed: large ? Self.budget48MP : Self.budget12MP)
        // Strip count scales with the source size: 16 per 12 MP (64 for 48 MP)
        let strips = Self.stripsPer12MP * max(1, Int((Double(pixels) / 12_200_000).rounded(.up)))

        return try autoreleasepool {
            let t0 = Date()
            var photo = try decoder.decode(dng, strips: strips)   // gates on ProRAW
            let t1 = Date()
            let seed = Grain.seed(fileName: dng.lastPathComponent, dateTimeOriginal: Encoder.dateTimeOriginal(photo.properties))
            let film = try model.render(photo.takeLinear(), noise: .seeded(seed), white: photo.white)
            let t2 = Date()

            let stem = dng.deletingPathExtension().lastPathComponent
            let renderURL = dir.appendingPathComponent("\(stem)-print.jpg")
            guard let image = Encoder.cgImage(film.image) else { throw FilmCoreError.encodeFailed("couldn't build the image") }
            try Encoder.jpeg(image, source: photo.properties, software: Self.software).write(to: renderURL)
            var comparisonURL: URL?
            if let preview = photo.preview {
                let url = dir.appendingPathComponent("\(stem)-apple.jpg")
                try Encoder.jpeg(preview, source: nil, software: Self.software).write(to: url)
                comparisonURL = url
            }
            let t3 = Date()
            for note in photo.notes { Logger.render.notice("\(stem, privacy: .public): \(note, privacy: .public)") }
            return Rendered(renderURL: renderURL, comparisonURL: comparisonURL,
                            captureDate: Encoder.captureDate(photo.properties), location: Encoder.location(photo.properties),
                            metering: film.metering, decodeSeconds: t1.timeIntervalSince(t0),
                            filmSeconds: t2.timeIntervalSince(t1), encodeSeconds: t3.timeIntervalSince(t2),
                            megapixels: Double(pixels) / 1e6, peakFootprint: Diagnostics.peakFootprint())
        }
    }

    static func checkMemory(needed: UInt64) throws {
        #if !targetEnvironment(simulator)   // the simulator reports 0
        let available = UInt64(os_proc_available_memory())
        if available < needed { throw RenderError.insufficientMemory(needed: needed, available: available) }
        #endif
    }
}

extension Logger {
    static let render = Logger(subsystem: "com.nickchua.print", category: "render")
}
