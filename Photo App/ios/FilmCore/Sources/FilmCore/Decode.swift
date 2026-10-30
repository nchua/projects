import CoreImage
import Foundation
import ImageIO
import UniformTypeIdentifiers

/// One decoded ProRAW photo: upright linear sRGB at 6 MP, Apple's own rendering for comparison,
/// and the source metadata for Encode.
public struct DecodedPhoto: @unchecked Sendable {
    public var linear: PlanarImage
    /// The DNG's embedded preview (Apple's SDR JPEG), upright and scaled to the same long side.
    public var preview: CGImage?
    public var properties: [String: Any]

    /// Hands over the linear image, leaving this photo without it, so the film model owns its buffers.
    public mutating func takeLinear() -> PlanarImage {
        defer { linear.planes = [] }
        return linear
    }
    /// Settings read back from the filter and `is…Supported` flags that were false (R2).
    public var notes: [String]
}

public enum DecodeError: Error, CustomStringConvertible {
    case notProRAW, unreadable, decoderUnavailable(String), renderFailed

    public var description: String {
        switch self {
        case .notProRAW: "Not ProRAW (or edited in Photos) — skipped"
        case .unreadable: "Couldn't read the file"
        case .decoderUnavailable(let v): "RAW decoder \(v) isn't available on this OS"
        case .renderFailed: "Core Image couldn't render the photo"
        }
    }
}

/// DNG -> linear sRGB with Core Image (APP_SPEC.md §5.1). Owns one CIContext; not reentrant.
public final class Decoder: @unchecked Sendable {
    public static let decoderVersion = CIRAWDecoderVersion(rawValue: "8.dng")
    let context = CIContext(options: [
        .workingColorSpace: CGColorSpace(name: CGColorSpace.extendedLinearSRGB)!,
        .workingFormat: CIFormat.RGBAf,
        .cacheIntermediates: false,
    ])
    let longSide: Int
    let multiple: Int

    /// Output size and divisibility come from FilmParams (out_long_side, halation_downsample).
    public init(params: FilmParams) {
        longSide = params.outLongSide
        multiple = params.halationDownsample
    }

    /// `extent` scaled so its long side is `longSide`, rounded.
    func fit(_ extent: CGRect) -> (Int, Int) {
        let s = Double(longSide) / Double(max(extent.width, extent.height))
        return (Int((Double(extent.width) * s).rounded()), Int((Double(extent.height) * s).rounded()))
    }

    /// Gate (§5.1.1): RAW type, made by Apple, and LinearRaw in the file's IFDs.
    public static func isProRAW(_ url: URL) -> Bool {
        guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
              let type = CGImageSourceGetType(src) as String?, UTType(type)?.conforms(to: .rawImage) == true,
              let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [String: Any],
              let tiff = props[kCGImagePropertyTIFFDictionary as String] as? [String: Any],
              (tiff[kCGImagePropertyTIFFMake as String] as? String)?.hasPrefix("Apple") == true
        else { return false }
        return DNGProbe.isLinearRaw(url)
    }

    /// Pixel count of the raw image (12 or 48 MP for ProRAW), without decoding it.
    public static func nativePixelCount(_ url: URL) -> Int? {
        guard let size = CIRAWFilter(imageURL: url)?.nativeSize, size.width > 0 else { return nil }
        return Int(size.width * size.height)
    }

    /// Gates on ProRAW itself (§5.1.1), so callers don't need to.
    public func decode(_ url: URL, strips: Int = 8) throws -> DecodedPhoto {
        guard Self.isProRAW(url) else { throw DecodeError.notProRAW }
        guard let filter = CIRAWFilter(imageURL: url) else { throw DecodeError.unreadable }
        defer { context.clearCaches() }
        let notes = try configure(filter)
        guard let raw = filter.outputImage else { throw DecodeError.renderFailed }

        let (tw, th) = fit(raw.extent)
        guard tw % multiple == 0, th % multiple == 0 else {
            throw FilmCoreError.badSize("\(tw)×\(th) is not divisible by \(multiple)")
        }
        let linear = render(Self.lanczos(raw, to: tw, th), width: tw, height: th, strips: strips)

        var preview: CGImage?
        if let p = filter.previewImage {
            let orientation = (filter.properties[kCGImagePropertyOrientation as String] as? UInt32)
                .flatMap(CGImagePropertyOrientation.init) ?? .up
            let upright = p.oriented(orientation)
            let (pw, ph) = fit(upright.extent)
            preview = context.createCGImage(Self.lanczos(upright, to: pw, ph), from: CGRect(x: 0, y: 0, width: pw, height: ph),
                                            format: .RGBA8, colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!)
        }
        let source = CGImageSourceCreateWithURL(url as CFURL, nil)
        let properties = source.flatMap { CGImageSourceCopyPropertiesAtIndex($0, 0, nil) as? [String: Any] } ?? [:]
        return DecodedPhoto(linear: linear, preview: preview, properties: properties, notes: notes)
    }

    /// Every setting explicit (§5.1.2); returns notes on read-back mismatches and unsupported controls.
    func configure(_ f: CIRAWFilter) throws -> [String] {
        guard f.supportedDecoderVersions.contains(Self.decoderVersion) else {
            throw DecodeError.decoderUnavailable(Self.decoderVersion.rawValue)
        }
        f.decoderVersion = Self.decoderVersion
        f.neutralChromaticity = CGPoint(x: 0.3127, y: 0.3290)   // D65
        f.boostAmount = 0
        f.boostShadowAmount = 0
        f.localToneMapAmount = 0
        f.extendedDynamicRangeAmount = 0
        f.isGamutMappingEnabled = false
        f.isHighlightRecoveryEnabled = false
        f.shadowBias = 0
        f.sharpnessAmount = 0
        f.contrastAmount = 0
        f.detailAmount = 0
        f.luminanceNoiseReductionAmount = 0
        f.colorNoiseReductionAmount = 0
        f.moireReductionAmount = 0
        f.exposure = 0
        f.isDraftModeEnabled = false
        f.scaleFactor = 1

        var notes: [String] = []
        let readBack: [(String, Float)] = [
            ("boostAmount", f.boostAmount), ("boostShadowAmount", f.boostShadowAmount),
            ("localToneMapAmount", f.localToneMapAmount), ("extendedDynamicRangeAmount", f.extendedDynamicRangeAmount),
            ("shadowBias", f.shadowBias), ("sharpnessAmount", f.sharpnessAmount), ("contrastAmount", f.contrastAmount),
            ("detailAmount", f.detailAmount), ("luminanceNoiseReductionAmount", f.luminanceNoiseReductionAmount),
            ("colorNoiseReductionAmount", f.colorNoiseReductionAmount), ("moireReductionAmount", f.moireReductionAmount),
            ("exposure", f.exposure),
        ]
        notes += readBack.filter { $0.1 != 0 }.map { "\($0.0) reads back \($0.1)" }
        if f.scaleFactor != 1 { notes.append("scaleFactor reads back \(f.scaleFactor)") }
        if f.isGamutMappingEnabled { notes.append("isGamutMappingEnabled reads back true") }
        if f.isHighlightRecoveryEnabled { notes.append("isHighlightRecoveryEnabled reads back true") }
        if f.isDraftModeEnabled { notes.append("isDraftModeEnabled reads back true") }
        if f.decoderVersion != Self.decoderVersion { notes.append("decoderVersion reads back \(f.decoderVersion.rawValue)") }
        let n = f.neutralChromaticity
        if abs(n.x - 0.3127) > 1e-4 || abs(n.y - 0.3290) > 1e-4 { notes.append("neutralChromaticity reads back \(n)") }
        let supported: [(String, Bool)] = [
            ("localToneMap", f.isLocalToneMapSupported), ("highlightRecovery", f.isHighlightRecoverySupported),
            ("sharpness", f.isSharpnessSupported), ("contrast", f.isContrastSupported), ("detail", f.isDetailSupported),
            ("luminanceNoiseReduction", f.isLuminanceNoiseReductionSupported),
            ("colorNoiseReduction", f.isColorNoiseReductionSupported), ("moireReduction", f.isMoireReductionSupported),
        ]
        notes += supported.filter { !$0.1 }.map { "\($0.0) not supported" }
        return notes
    }

    /// Lanczos to exactly tw × th, origin at (0, 0).
    static func lanczos(_ image: CIImage, to tw: Int, _ th: Int) -> CIImage {
        let image = image.transformed(by: CGAffineTransform(translationX: -image.extent.minX, y: -image.extent.minY))
        let scale = Double(th) / image.extent.height
        let aspect = (Double(tw) / image.extent.width) / scale
        let f = CIFilter(name: "CILanczosScaleTransform", parameters: [
            kCIInputImageKey: image, kCIInputScaleKey: scale, kCIInputAspectRatioKey: aspect,
        ])!
        return f.outputImage!
    }

    /// Renders in horizontal strips (§5.1.4), each into a strip-sized RGBAf buffer that is de-interleaved
    /// straight into the planes, so the full interleaved frame never exists.
    func render(_ image: CIImage, width w: Int, height h: Int, strips: Int) -> PlanarImage {
        let n = w * h
        let space = CGColorSpace(name: CGColorSpace.extendedLinearSRGB)!
        let rgba = UnsafeMutableBufferPointer<Float>.allocate(capacity: (h + strips - 1) / strips * w * 4)
        defer { rgba.deallocate() }
        var planes = (0..<3).map { _ in [Float](unsafeUninitializedCapacity: n) { _, count in count = n } }
        for i in 0..<strips {
            let (top, bottom) = (h * i / strips, h * (i + 1) / strips)
            // Core Image's origin is bottom-left; bitmap row 0 is the top of the bounds
            context.render(image, toBitmap: rgba.baseAddress!, rowBytes: w * 16,
                           bounds: CGRect(x: 0, y: h - bottom, width: w, height: bottom - top),
                           format: .RGBAf, colorSpace: space)
            for c in 0..<3 {
                planes[c].withUnsafeMutableBufferPointer { p in
                    for j in 0..<((bottom - top) * w) { p[top * w + j] = rgba[j * 4 + c] }
                }
            }
        }
        return PlanarImage(width: w, height: h, planes: planes)
    }
}
