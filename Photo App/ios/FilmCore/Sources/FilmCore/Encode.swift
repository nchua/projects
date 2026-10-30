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

    /// Capture time: the GPS UTC stamp if present, else DateTimeOriginal in OffsetTimeOriginal (or `timeZone`).
    public static func captureDate(_ source: [String: Any], timeZone: TimeZone = .current) -> Date? {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        if let gps = source[kCGImagePropertyGPSDictionary as String] as? [String: Any],
           let day = gps[kCGImagePropertyGPSDateStamp as String] as? String,
           let time = gps[kCGImagePropertyGPSTimeStamp as String] as? String {
            f.timeZone = TimeZone(identifier: "UTC")
            f.dateFormat = time.contains(".") ? "yyyy:MM:dd HH:mm:ss.SS" : "yyyy:MM:dd HH:mm:ss"
            if let date = f.date(from: "\(day) \(time)") { return date }
        }
        guard let local = dateTimeOriginal(source) else { return nil }
        let exif = source[kCGImagePropertyExifDictionary as String] as? [String: Any]
        if let offset = exif?[kCGImagePropertyExifOffsetTimeOriginal as String] as? String {
            f.dateFormat = "yyyy:MM:dd HH:mm:ssxxx"
            if let date = f.date(from: local + offset) { return date }
        }
        f.timeZone = timeZone
        f.dateFormat = "yyyy:MM:dd HH:mm:ss"
        return f.date(from: local)
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
