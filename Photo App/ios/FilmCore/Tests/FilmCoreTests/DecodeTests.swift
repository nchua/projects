import CoreImage
import ImageIO
import Foundation
import XCTest
@testable import FilmCore

/// M2: Core Image decode vs rawpy (tests C and D run in compare.py via ios/scripts/parity.sh).
/// DNGs come from PRINT_DNG_DIR (default ~/Downloads) and must have a fixture directory.
final class DecodeTests: XCTestCase {
    static var dngDir: URL {
        ProcessInfo.processInfo.environment["PRINT_DNG_DIR"].map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Downloads")
    }

    func dngs() throws -> [(URL, URL)] {
        let pairs = try Fixtures.stems().compactMap { stem -> (URL, URL)? in
            let dng = Self.dngDir.appendingPathComponent("\(stem).DNG")
            return FileManager.default.fileExists(atPath: dng.path) ? (dng, Fixtures.dir.appendingPathComponent(stem)) : nil
        }
        if pairs.isEmpty { throw XCTSkip("no DNGs with fixtures in \(Self.dngDir.path)") }
        return pairs
    }

    func testProbeGate() throws {
        for (dng, fixture) in try dngs() {
            XCTAssertTrue(DNGProbe.isLinearRaw(dng), dng.lastPathComponent)
            XCTAssertTrue(Decoder.isProRAW(dng), dng.lastPathComponent)
            XCTAssertFalse(Decoder.isProRAW(fixture.appendingPathComponent("out.png")))
        }
    }

    func testDecodeWritesParityOutputs() throws {
        let model = try FilmModel.bundled()
        let decoder = Decoder(params: model.params)
        for (dng, fixture) in try dngs() {
            let start = Date()
            let photo = try decoder.decode(dng)
            let seconds = Date().timeIntervalSince(start)
            let film = try model.render(photo.linear, noise: .none)
            print(String(format: "%@: decode %.2f s  %d×%d  k %.6f (%@)  notes: %@", dng.lastPathComponent, seconds,
                         photo.linear.width, photo.linear.height, film.k, film.metering,
                         photo.notes.isEmpty ? "none" : photo.notes.joined(separator: "; ")))
            XCTAssertNotNil(photo.preview)
            let out = fixture.appendingPathComponent("swift")
            try FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
            try Fixtures.writePlanar(photo.linear, to: out.appendingPathComponent("decoded6mp.f32"))
            try Fixtures.writePlanar(film.image, to: out.appendingPathComponent("decoded_out_nograin.f32"))
        }
    }

    func testStripsMatchSingleRender() throws {
        guard let (dng, _) = try dngs().first else { return }
        let decoder = try Decoder(params: FilmModel.bundled().params)
        let a = try decoder.decode(dng, strips: 1).linear, b = try decoder.decode(dng, strips: 8).linear
        XCTAssertEqual(a.planes, b.planes, "strip rendering changes values")
    }
}

/// The app's whole path on the Mac (decode, app grain, JPEG): what M4 repeats on the phone.
final class EncodeTests: XCTestCase {
    func testEndToEndJPEGKeepsCaptureMetadata() throws {
        let model = try FilmModel.bundled()
        let decoder = Decoder(params: model.params)
        let pairs = try DecodeTests().dngs()
        for (dng, fixture) in pairs {
            let photo = try decoder.decode(dng)
            let seed = Grain.seed(fileName: dng.lastPathComponent, dateTimeOriginal: Encoder.dateTimeOriginal(photo.properties))
            let film = try model.render(photo.linear, noise: .seeded(seed))
            let jpeg = try Encoder.jpeg(XCTUnwrap(Encoder.cgImage(film.image)), source: photo.properties, software: "Print test")
            try FileManager.default.createDirectory(at: fixture.appendingPathComponent("swift"), withIntermediateDirectories: true)
            try jpeg.write(to: fixture.appendingPathComponent("swift/app.jpg"))

            let src = try XCTUnwrap(CGImageSourceCreateWithData(jpeg as CFData, nil))
            let props = try XCTUnwrap(CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [String: Any])
            XCTAssertEqual(props[kCGImagePropertyPixelWidth as String] as? Int, film.image.width)
            XCTAssertEqual(props[kCGImagePropertyOrientation as String] as? Int, 1)
            XCTAssertEqual(Encoder.dateTimeOriginal(props), Encoder.dateTimeOriginal(photo.properties))
            XCTAssertNotNil(Encoder.captureDate(photo.properties))
            let tiff = props[kCGImagePropertyTIFFDictionary as String] as? [String: Any]
            XCTAssertEqual(tiff?[kCGImagePropertyTIFFSoftware as String] as? String, "Print test")
            print("\(dng.lastPathComponent): JPEG \(jpeg.count / 1024) KB, captured \(Encoder.captureDate(photo.properties)!), "
                  + "GPS \(Encoder.location(photo.properties).map { "\($0.coordinate)" } ?? "none")")
        }
    }
}

final class CaptureDateTests: XCTestCase {
    func props(offset: String? = nil, gps: (String, String)? = nil) -> [String: Any] {
        var exif: [String: Any] = [kCGImagePropertyExifDateTimeOriginal as String: "2026:10:29 16:58:01",
                                   kCGImagePropertyExifSubsecTimeOriginal as String: "384"]
        if let offset { exif[kCGImagePropertyExifOffsetTimeOriginal as String] = offset }
        var out: [String: Any] = [kCGImagePropertyExifDictionary as String: exif]
        if let gps {
            out[kCGImagePropertyGPSDictionary as String] = [kCGImagePropertyGPSDateStamp as String: gps.0,
                                                            kCGImagePropertyGPSTimeStamp as String: gps.1]
        }
        return out
    }

    /// 2026-10-29 23:58:01.384 UTC, IMG_2725's shutter time.
    let shutter = Date(timeIntervalSince1970: 1_793_318_281.384)

    func testOffsetWins() {
        XCTAssertEqual(Encoder.captureDate(props(offset: "-07:00", gps: ("2026:10:29", "23:58:00")))!.timeIntervalSince1970,
                       shutter.timeIntervalSince1970, accuracy: 1e-3)
    }

    func testOffsetBeatsDisagreeingGPS() {
        // GPS says UTC−5; the explicit offset (+05:30, east, half-hour) must win
        let date = Encoder.captureDate(props(offset: "+05:30", gps: ("2026:10:29", "21:58:00")))!
        XCTAssertEqual(date.timeIntervalSince1970, shutter.timeIntervalSince1970 - 12.5 * 3600, accuracy: 1e-3)
    }

    func testPaddedSubsec() {
        var p = props(offset: "-07:00")
        var exif = p[kCGImagePropertyExifDictionary as String] as! [String: Any]
        exif[kCGImagePropertyExifSubsecTimeOriginal as String] = "384 "
        p[kCGImagePropertyExifDictionary as String] = exif
        XCTAssertEqual(Encoder.captureDate(p)!.timeIntervalSince1970, shutter.timeIntervalSince1970, accuracy: 1e-3)
    }

    func testOffsetInferredFromGPS() {
        XCTAssertEqual(Encoder.captureDate(props(gps: ("2026:10:29", "23:57:59.50")))!.timeIntervalSince1970,
                       shutter.timeIntervalSince1970, accuracy: 1e-3)
    }

    func testDeviceZoneLast() {
        let zone = TimeZone(secondsFromGMT: -7 * 3600)!
        XCTAssertEqual(Encoder.captureDate(props(), timeZone: zone)!.timeIntervalSince1970,
                       shutter.timeIntervalSince1970, accuracy: 1e-3)
    }
}
