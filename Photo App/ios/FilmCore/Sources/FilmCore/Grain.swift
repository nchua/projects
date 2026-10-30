import Foundation

/// The app's own grain (APP_SPEC.md §5.2 step 5): i.i.d. N(0, 1) from a counter-based hash of
/// (seed, x, y), blurred with raw_look's grain kernel and divided by the kernel's analytic std, so a
/// pixel's grain depends only on the seed and its position.
public enum Grain {
    public static func field(seed: UInt64, width w: Int, height h: Int, params: FilmParams) -> [Float] {
        var white = [Float](repeating: 0, count: w * h)
        white.withUnsafeMutableBufferPointer { out in
            parallelRows(h) { y in
                for x in 0..<w {
                    let i = UInt64(y * w + x)
                    let u1 = unit(mix(seed &+ 2 &* i))
                    let u2 = unit(mix(seed &+ 2 &* i &+ 1))
                    out[y * w + x] = Float((-2 * log(u1)).squareRoot() * cos(2 * Double.pi * u2))
                }
            }
        }
        var field = Filters.gaussianBlur(white, width: w, height: h, sigma: params.grainSigma,
                                         truncation: params.blurTruncation)
        let std = Float(analyticStd(params))
        field.withUnsafeMutableBufferPointer { f in
            for i in f.indices { f[i] /= std }
        }
        return field
    }

    /// Std of unit white noise after the separable 2-D blur: (Σk²)^(1/2) per axis, so Σk² over both.
    public static func analyticStd(_ params: FilmParams) -> Double {
        Filters.gaussianKernel(sigma: params.grainSigma, truncation: params.blurTruncation).map { $0 * $0 }.reduce(0, +)
    }

    /// Per-photo seed: FNV-1a 64 of the file name followed by DateTimeOriginal (D5).
    public static func seed(fileName: String, dateTimeOriginal: String?) -> UInt64 {
        var hash: UInt64 = 0xcbf2_9ce4_8422_2325
        for byte in (fileName + (dateTimeOriginal ?? "")).utf8 {
            hash = (hash ^ UInt64(byte)) &* 0x0000_0100_0000_01b3
        }
        return hash
    }

    /// SplitMix64's finaliser: a counter -> 64 well-mixed bits.
    @inline(__always)
    static func mix(_ v: UInt64) -> UInt64 {
        var z = v &+ 0x9e37_79b9_7f4a_7c15
        z = (z ^ (z >> 30)) &* 0xbf58_476d_1ce4_e5b9
        z = (z ^ (z >> 27)) &* 0x94d0_49bb_1331_11eb
        return z ^ (z >> 31)
    }

    /// 53 random bits -> (0, 1], so log() is finite.
    @inline(__always)
    static func unit(_ bits: UInt64) -> Double { Double((bits >> 11) + 1) * 0x1p-53 }
}
