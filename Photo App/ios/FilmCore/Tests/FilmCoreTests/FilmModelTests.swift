import Foundation
import XCTest
@testable import FilmCore

/// M1: the film model against Python's stage-by-stage fixtures (APP_SPEC.md §6). These tests only
/// produce outputs and check stage values; the image metrics live in prototype/compare.py, which
/// ios/scripts/parity.sh runs on what is written to fixtures/<stem>/swift/.
final class FilmModelTests: XCTestCase {
    func testParamsMatchExportedJSON() throws {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "film_params", withExtension: "json"))
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        XCTAssertEqual(Set(json.keys), FilmParams.keys, "every exported key is read, and nothing else")
        let (params, lut) = try FilmParams.bundled()   // throws on a sha256 mismatch
        XCTAssertEqual(lut.values.count, params.lutSize * 3)
    }

    func testPercentileMatchesSortedDefinition() {
        var rng = SystemRandomNumberGenerator()
        let values = (0..<10_001).map { _ in Float.random(in: 0..<1, using: &rng) }
        let sorted = values.sorted()
        for pct in [0.0, 12.5, 50.0, 99.5, 100.0] {
            let q = Double(values.count - 1) * pct / 100
            let lo = Int(q), t = q - Double(lo)
            let hi = min(lo + 1, values.count - 1)
            let expected = Double(sorted[lo]) + (Double(sorted[hi]) - Double(sorted[lo])) * t
            var copy = values
            XCTAssertEqual(FilmModel.percentile(&copy, pct), expected, accuracy: 1e-7, "p\(pct)")
        }
    }

    func testGrainFieldStatistics() throws {
        let (params, _) = try FilmParams.bundled()
        let (w, h) = (1024, 1024)
        let n = Grain.field(seed: 42, width: w, height: h, params: params).map(Double.init)
        let mean = n.reduce(0, +) / Double(n.count)
        let variance = n.map { ($0 - mean) * ($0 - mean) }.reduce(0, +) / Double(n.count)
        var lag = 0.0
        for y in 0..<h { for x in 0..<(w - 1) { lag += (n[y * w + x] - mean) * (n[y * w + x + 1] - mean) } }
        let autocorrelation = lag / Double(h * (w - 1)) / variance
        print(String(format: "grain field: mean %.5f  std %.5f  lag-1 %.5f  (analytic std %.5f)",
                     mean, variance.squareRoot(), autocorrelation, Grain.analyticStd(params)))
        XCTAssertLessThan(abs(mean), 0.01)
        XCTAssertEqual(variance.squareRoot(), 1, accuracy: 0.01)
        XCTAssertEqual(autocorrelation, 0.0875, accuracy: 0.005)
        XCTAssertNotEqual(Grain.field(seed: 43, width: 8, height: 8, params: params),
                          Grain.field(seed: 42, width: 8, height: 8, params: params))
    }

    func testMatrix3Inverse() throws {
        let m = try FilmModel.bundled().params.xyzToSrgb
        let product = Matrix3.multiply(m, try XCTUnwrap(Matrix3.inverse(m)))
        for i in 0..<3 { for j in 0..<3 { XCTAssertEqual(product[i][j], Matrix3.identity[i][j], accuracy: 1e-14) } }
        XCTAssertNil(Matrix3.inverse([[1, 2, 3], [2, 4, 6], [0, 0, 1]]))
    }

    /// `raw_look.print_timing`'s properties: identity without a white or at D65; otherwise the white keeps its
    /// luminance and its cone ratios move white_balance of the way (in log) to daylight's.
    func testPrintTiming() throws {
        let model = try FilmModel.bundled()
        let p = model.params
        XCTAssertEqual(model.printTiming(nil), Matrix3.identity, "no white: a daylight print")
        let daylight = model.printTiming([1, 1, 1])
        for i in 0..<3 { for j in 0..<3 { XCTAssertEqual(daylight[i][j], Matrix3.identity[i][j], accuracy: 1e-12, "D65") } }

        let w: [Double] = [2.2871, 1.0, 0.2003]   // IMG_2732's tungsten white
        let timed = Matrix3.apply(model.printTiming(w), w)
        XCTAssertEqual(Matrix3.dot(p.luma, timed), Matrix3.dot(p.luma, w), accuracy: 1e-12, "luminance kept")
        let toLMS = Matrix3.multiply(p.bradford, try XCTUnwrap(Matrix3.inverse(p.xyzToSrgb)))
        let (light, d65, after) = (Matrix3.apply(toLMS, w), Matrix3.apply(toLMS, [1, 1, 1]), Matrix3.apply(toLMS, timed))
        for c in [0, 2] {
            let expected = (1 - p.whiteBalance) * log(light[c] / light[1]) + p.whiteBalance * log(d65[c] / d65[1])
            XCTAssertEqual(log(after[c] / after[1]), expected, accuracy: 1e-9, "cone ratio \(c)")
        }
    }

    /// Tests A and B plus the app-grain render, for every fixture directory present.
    func testFixtureParity() throws {
        let stems = try Fixtures.stems()
        let model = try FilmModel.bundled()
        for stem in stems {
            let dir = Fixtures.dir.appendingPathComponent(stem)
            let meta = try Fixtures.meta(dir)
            let (w, h) = (meta["W"] as! Int, meta["H"] as! Int)
            let linear = try Fixtures.readPlanar(dir.appendingPathComponent("linear6mp.f32"), width: w, height: h)
            let noise = try Fixtures.readF32(dir.appendingPathComponent("noise.f32"))
            let white = meta["white"] as? [Double]   // JSON null -> nil: a daylight print

            let start = Date()
            let a = try model.render(linear, noise: .injected(noise), white: white, captureStages: true)
            let seconds = Date().timeIntervalSince(start)
            let k = meta["k"] as! Double
            print(String(format: "%@: film model %.2f s  k %.6f vs %.6f (%@)  p %.6g  white %@", stem, seconds, a.k, k,
                         a.metering, a.percentile, white.map { "\($0)" } ?? "none"))
            XCTAssertEqual(a.metering, meta["metering"] as? String, stem)
            XCTAssertLessThanOrEqual(abs(a.k / k - 1), 1e-6, "\(stem): k")
            try Fixtures.assertClose(a.glow!, dir.appendingPathComponent("glow.f32"), stem: stem, name: "glow")
            try Fixtures.assertClose(a.stopsPregrain!.flatMap { $0 }, dir.appendingPathComponent("stops_pregrain.f32"),
                                     stem: stem, name: "stops_pregrain")

            let out = dir.appendingPathComponent("swift")
            try FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
            try Fixtures.writeMeta(out, width: w, height: h, result: a)
            try Fixtures.writePlanar(a.image, to: out.appendingPathComponent("out.f32"))
            try Fixtures.writePlanar(model.render(linear, noise: .none, white: white).image,
                                     to: out.appendingPathComponent("out_nograin.f32"))
            let seed = Grain.seed(fileName: meta["dng"] as! String, dateTimeOriginal: nil)
            try Fixtures.writePlanar(model.render(linear, noise: .seeded(seed), white: white).image,
                                     to: out.appendingPathComponent("out_appgrain.f32"))
        }
    }
}

/// Fixture paths and little-endian float32 planar IO.
enum Fixtures {
    static var dir: URL {
        if let env = ProcessInfo.processInfo.environment["PRINT_FIXTURES_DIR"] { return URL(fileURLWithPath: env) }
        // Tests/FilmCoreTests/<file> -> Photo App/fixtures
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 { url.deleteLastPathComponent() }
        return url.appendingPathComponent("fixtures")
    }

    static func stems() throws -> [String] {
        let names = (try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? []
        let stems = names.filter { FileManager.default.fileExists(atPath: dir.appendingPathComponent("\($0)/meta.json").path) }
        if stems.isEmpty { throw XCTSkip("no fixtures in \(dir.path); run prototype/export_film.py --reference") }
        return stems.sorted()
    }

    static func meta(_ dir: URL) throws -> [String: Any] {
        try JSONSerialization.jsonObject(with: Data(contentsOf: dir.appendingPathComponent("meta.json"))) as! [String: Any]
    }

    static func readF32(_ url: URL) throws -> [Float] {
        let data = try Data(contentsOf: url)
        return data.withUnsafeBytes { $0.bindMemory(to: UInt32.self).map { Float(bitPattern: UInt32(littleEndian: $0)) } }
    }

    static func readPlanar(_ url: URL, width: Int, height: Int) throws -> PlanarImage {
        let all = try readF32(url)
        let n = width * height
        return PlanarImage(width: width, height: height, planes: (0..<3).map { Array(all[($0 * n)..<($0 * n + n)]) })
    }

    static func writePlanar(_ image: PlanarImage, to url: URL) throws {
        let all = image.planes.flatMap { $0 }
        try all.withUnsafeBufferPointer { Data(buffer: $0) }.write(to: url)
    }

    static func writeMeta(_ dir: URL, width: Int, height: Int, result: FilmResult) throws {
        let meta: [String: Any] = ["H": height, "W": width, "k": result.k, "k_highlight": result.kHighlight,
                                   "k_average": result.kAverage, "p": result.percentile, "metering": result.metering]
        try JSONSerialization.data(withJSONObject: meta, options: [.prettyPrinted, .sortedKeys])
            .write(to: dir.appendingPathComponent("meta.json"))
    }

    /// Stage check: max |Δ| ≤ 1e-4 of the reference's largest magnitude.
    static func assertClose(_ values: [Float], _ url: URL, stem: String, name: String) throws {
        let ref = try readF32(url)
        XCTAssertEqual(values.count, ref.count, "\(stem) \(name) size")
        var maxDiff: Float = 0, scale: Float = 0
        for i in 0..<min(values.count, ref.count) {
            maxDiff = max(maxDiff, abs(values[i] - ref[i]))
            scale = max(scale, abs(ref[i]))
        }
        print(String(format: "%@: %@ max |Δ| %.3g (relative %.3g)", stem, name, maxDiff, maxDiff / max(scale, 1e-30)))
        XCTAssertLessThanOrEqual(maxDiff, 1e-4 * scale, "\(stem): \(name)")
    }
}
