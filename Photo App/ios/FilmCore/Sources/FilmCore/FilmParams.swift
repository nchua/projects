import CryptoKit
import Foundation

/// Codable mirror of `film_params.json`, written by `prototype/export_film.py` from `raw_look.py`.
/// Every film constant comes from here; Swift holds only the structural literals APP_SPEC.md §2 allows.
public struct FilmParams: Codable, Sendable {
    public let version: Int
    public let outLongSide: Int
    public let luma: [Double]
    public let midGrey: Double
    public let highlightPercentile: Double
    public let highlightStops: Double
    public let averageStops: Double
    public let meterFloor: Double
    public let crosstalk: [[Double]]
    /// Print timing (`raw_look.print_timing`): the share of the light's colour the lab takes out, Bradford's
    /// XYZ -> cone matrix, and XYZ -> linear sRGB (the as-shot white uses it too)
    public let whiteBalance: Double
    public let bradford: [[Double]]
    public let xyzToSrgb: [[Double]]
    public let clampFloor: Double
    /// Lens softness before metering (`raw_look.soften`), in output px
    public let softenSigma: Double
    public let vignetteStops: Double
    public let vignetteStart: Double
    public let vignetteEnd: Double
    public let vignettePower: Double
    public let halationStops: Double
    public let halationSigma: Double
    public let halationStrength: Double
    public let halationTint: [Double]
    public let halationDownsample: Int
    public let blurTruncation: Int
    public let grainStops: Double
    public let grainSigma: Double
    /// Colour moves with density (`raw_look.density`): tables by luminance in stops from mid grey, the unit
    /// vector from magenta to green in stops, and the cap on a colour's size
    public let densityStops: [Double]
    public let chromaGain: [Double]
    public let shiftDense: [Double]
    public let shiftSaturated: [Double]
    public let greenMagenta: [Double]
    public let densityChromaCap: Double
    public let lutMin: Double
    public let lutMax: Double
    public let lutSize: Int
    public let lutSha256: String

    enum CodingKeys: String, CodingKey, CaseIterable {
        case version, luma, crosstalk, bradford
        case outLongSide = "out_long_side", midGrey = "mid_grey"
        case whiteBalance = "white_balance", xyzToSrgb = "xyz_to_srgb"
        case highlightPercentile = "highlight_percentile", highlightStops = "highlight_stops"
        case averageStops = "average_stops", meterFloor = "meter_floor", clampFloor = "clamp_floor"
        case softenSigma = "soften_sigma"
        case vignetteStops = "vignette_stops", vignetteStart = "vignette_start"
        case vignetteEnd = "vignette_end", vignettePower = "vignette_power"
        case halationStops = "halation_stops", halationSigma = "halation_sigma"
        case halationStrength = "halation_strength", halationTint = "halation_tint"
        case halationDownsample = "halation_downsample", blurTruncation = "blur_truncation"
        case grainStops = "grain_stops", grainSigma = "grain_sigma"
        case densityStops = "density_stops", chromaGain = "chroma_gain", shiftDense = "shift_dense"
        case shiftSaturated = "shift_saturated", greenMagenta = "green_magenta", densityChromaCap = "density_chroma_cap"
        case lutMin = "lut_min", lutMax = "lut_max", lutSize = "lut_size", lutSha256 = "lut_sha256"
    }

    /// The JSON keys this struct reads (a test checks the exported file has exactly these).
    public static var keys: Set<String> { Set(CodingKeys.allCases.map(\.rawValue)) }
}

/// The print curve: `size` rows of linear (R, G, B), sampled at stops linspace(min, max, size).
public struct PrintLUT: Sendable {
    public let values: [Float]
}

public enum FilmCoreError: Error, CustomStringConvertible {
    case missingResource(String)
    case lutMismatch(expected: String, actual: String)
    case badSize(String)
    case invalidParams(String)
    case nonFinite
    case encodeFailed(String)

    public var description: String {
        switch self {
        case .missingResource(let name): "FilmCore resource \(name) not found"
        case .lutMismatch(let e, let a): "print_lut.bin sha256 \(a) does not match film_params.json (\(e))"
        case .badSize(let s): s
        case .invalidParams(let s): "film_params.json is invalid: \(s)"
        case .nonFinite: "The decoded photo has non-finite pixels"
        case .encodeFailed(let s): "Encoding failed: \(s)"
        }
    }
}

extension FilmParams {
    /// Loads the bundled params and LUT, verifying the LUT against `lut_sha256`.
    public static func bundled() throws -> (FilmParams, PrintLUT) {
        guard let json = Bundle.module.url(forResource: "film_params", withExtension: "json") else {
            throw FilmCoreError.missingResource("film_params.json")
        }
        guard let bin = Bundle.module.url(forResource: "print_lut", withExtension: "bin") else {
            throw FilmCoreError.missingResource("print_lut.bin")
        }
        let params = try JSONDecoder().decode(FilmParams.self, from: Data(contentsOf: json))
        let data = try Data(contentsOf: bin)
        let sha = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        guard sha == params.lutSha256 else { throw FilmCoreError.lutMismatch(expected: params.lutSha256, actual: sha) }
        guard data.count == params.lutSize * 3 * MemoryLayout<Float>.size else {
            throw FilmCoreError.badSize("print_lut.bin has \(data.count) bytes, expected \(params.lutSize) × 3 float32")
        }
        let values = data.withUnsafeBytes { raw in
            raw.bindMemory(to: UInt32.self).map { Float(bitPattern: UInt32(littleEndian: $0)) }
        }
        return (params, PrintLUT(values: values))
    }
}
