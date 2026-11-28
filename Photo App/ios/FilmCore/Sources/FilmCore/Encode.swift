import CoreLocation
import Foundation
import ImageIO
import UniformTypeIdentifiers

/// Render -> JPEG with the original's capture metadata (APP_SPEC.md §5.3).
public enum Encoder {
    public static let quality = 0.95

    /// Float display sRGB -> 8-bit sRGB CGImage, quantised as round(clip(x) · 255) like raw_look.develop()
    /// (numpy rounds half to even).
    public static func cgImage(_ image: PlanarImage) -> CGImage? {
        let (w, h) = (image.width, image.height)
        guard let data = CFDataCreateMutable(nil, w * h * 3) else { return nil }
        CFDataSetLength(data, w * h * 3)
        let bytes = CFDataGetMutableBytePtr(data)!
        image.planes[0].withUnsafeBufferPointer { r in
            image.planes[1].withUnsafeBufferPointer { g in
                image.planes[2].withUnsafeBufferPointer { b in
                    parallelRows(h) { y in
                        for i in (y * w)..<(y * w + w) {
                            bytes[i * 3] = quantise(r[i])
                            bytes[i * 3 + 1] = quantise(g[i])
                            bytes[i * 3 + 2] = quantise(b[i])
                        }
                    }
                }
            }
        }
        guard let provider = CGDataProvider(data: data) else { return nil }
        return CGImage(width: w, height: h, bitsPerComponent: 8, bitsPerPixel: 24, bytesPerRow: w * 3,
                       space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGBitmapInfo(rawValue: 0),
                       provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent)
    }

    @inline(__always)
    static func quantise(_ x: Float) -> UInt8 { UInt8((min(max(x, 0), 1) * 255).rounded(.toNearestOrEven)) }

    /// JPEG q0.95, upright, with the capture metadata copied from `source` (nil for the comparison image).
    public static func jpeg(_ image: CGImage, source: [String: Any]?, software: String) throws -> Data {
        let data = NSMutableData()
        guard let dest = CGImageDestinationCreateWithData(data, UTType.jpeg.identifier as CFString, 1, nil) else {
            throw FilmCoreError.encodeFailed("couldn't create a JPEG destination")
        }
        var props = source.map { metadata(from: $0, software: software) } ?? [:]
        props[kCGImageDestinationLossyCompressionQuality as String] = quality
        props[kCGImagePropertyOrientation as String] = 1
        CGImageDestinationAddImage(dest, image, props as CFDictionary)
        guard CGImageDestinationFinalize(dest) else { throw FilmCoreError.encodeFailed("JPEG") }
        return data as Data
    }

    /// The subset of the source's EXIF/TIFF/GPS kept on the render; no thumbnail, MakerNote, orientation or sizes.
    static func metadata(from source: [String: Any], software: String) -> [String: Any] {
        func pick(_ dict: CFString, _ keys: [CFString]) -> [String: Any] {
            let d = source[dict as String] as? [String: Any] ?? [:]
            return d.filter { entry in keys.contains { $0 as String == entry.key } }
        }
        var tiff = pick(kCGImagePropertyTIFFDictionary, [kCGImagePropertyTIFFMake, kCGImagePropertyTIFFModel])
        tiff[kCGImagePropertyTIFFSoftware as String] = software
        let exif = pick(kCGImagePropertyExifDictionary, [
            kCGImagePropertyExifDateTimeOriginal, kCGImagePropertyExifSubsecTimeOriginal,
            kCGImagePropertyExifOffsetTimeOriginal, kCGImagePropertyExifLensModel, kCGImagePropertyExifISOSpeedRatings,
            kCGImagePropertyExifExposureTime, kCGImagePropertyExifFNumber, kCGImagePropertyExifFocalLength,
        ])
        var out: [String: Any] = [kCGImagePropertyTIFFDictionary as String: tiff, kCGImagePropertyExifDictionary as String: exif]
        if let gps = source[kCGImagePropertyGPSDictionary as String] { out[kCGImagePropertyGPSDictionary as String] = gps }
        return out
    }

    public static func dateTimeOriginal(_ source: [String: Any]) -> String? {
        (source[kCGImagePropertyExifDictionary as String] as? [String: Any])?[kCGImagePropertyExifDateTimeOriginal as String] as? String
    }

    /// Shutter time: DateTimeOriginal + SubsecTimeOriginal in OffsetTimeOriginal. Without an offset, the zone is
    /// inferred from the GPS UTC stamp (rounded to 15 min: the GPS fix is whole seconds and can lag the shutter),
    /// else `timeZone`. Using the GPS stamp itself put renders a second off their originals in Photos.
    public static func captureDate(_ source: [String: Any], timeZone: TimeZone = .current) -> Date? {
        let exif = source[kCGImagePropertyExifDictionary as String] as? [String: Any] ?? [:]
        let gps = source[kCGImagePropertyGPSDictionary as String] as? [String: Any] ?? [:]
        let utc = TimeZone(identifier: "UTC")!
        func parse(_ text: String, _ format: String, _ zone: TimeZone) -> Date? {
            let f = DateFormatter()
            f.locale = Locale(identifier: "en_US_POSIX")
            f.timeZone = zone
            f.dateFormat = format
            return f.date(from: text)
        }
        let gpsDate: Date? = {
            guard let day = gps[kCGImagePropertyGPSDateStamp as String] as? String,
                  let time = gps[kCGImagePropertyGPSTimeStamp as String] as? String else { return nil }
            return parse("\(day) \(time.prefix(8))", "yyyy:MM:dd HH:mm:ss", utc)
        }()
        guard let local = dateTimeOriginal(source), let wall = parse(local, "yyyy:MM:dd HH:mm:ss", utc) else { return gpsDate }
        let subsec = (exif[kCGImagePropertyExifSubsecTimeOriginal as String] as? String)   // EXIF may pad with spaces
            .flatMap { Double("0." + $0.trimmingCharacters(in: .whitespaces)) } ?? 0

        let offset: Int   // seconds east of UTC
        if let text = exif[kCGImagePropertyExifOffsetTimeOriginal as String] as? String,
           let zoned = parse(local + text, "yyyy:MM:dd HH:mm:ssxxx", utc) {
            offset = Int(wall.timeIntervalSince(zoned))
        } else if let gpsDate, case let inferred = Int((wall.timeIntervalSince(gpsDate) / 900).rounded()) * 900,
                  (-12 * 3600)...(14 * 3600) ~= inferred {   // a stale fix outside real zones falls through
            offset = inferred
        } else {
            // `wall` is the local time read as UTC; evaluate the zone at the real instant (matters near DST changes)
            offset = timeZone.secondsFromGMT(for: wall.addingTimeInterval(-Double(timeZone.secondsFromGMT(for: wall))))
        }
        return wall.addingTimeInterval(subsec - Double(offset))
    }

    public static func location(_ source: [String: Any]) -> CLLocation? {
        guard let gps = source[kCGImagePropertyGPSDictionary as String] as? [String: Any],
              let lat = gps[kCGImagePropertyGPSLatitude as String] as? Double,
              let lon = gps[kCGImagePropertyGPSLongitude as String] as? Double else { return nil }
        let latitude = (gps[kCGImagePropertyGPSLatitudeRef as String] as? String) == "S" ? -lat : lat
        let longitude = (gps[kCGImagePropertyGPSLongitudeRef as String] as? String) == "W" ? -lon : lon
        let altitude = gps[kCGImagePropertyGPSAltitude as String] as? Double ?? 0
        return CLLocation(coordinate: CLLocationCoordinate2D(latitude: latitude, longitude: longitude), altitude: altitude,
                          horizontalAccuracy: gps[kCGImagePropertyGPSHPositioningError as String] as? Double ?? -1,
                          verticalAccuracy: -1, timestamp: captureDate(source) ?? Date())
    }
}
