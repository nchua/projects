import Foundation

/// Planar Float32 image, row-major, channel planes R, G, B (APP_SPEC.md §5).
public struct PlanarImage: Sendable {
    public let width: Int
    public let height: Int
    public var planes: [[Float]]

    public init(width: Int, height: Int, planes: [[Float]]) {
        self.width = width
        self.height = height
        self.planes = planes
    }
}

/// Where the grain comes from: none, a field injected by a test (already unit std), or the app's own.
public enum Noise: Sendable {
    case none
    case injected([Float])
    case seeded(UInt64)
}

/// The film model's output plus what parity tests and the app's metadata need.
public struct FilmResult: Sendable {
    /// Display sRGB, clipped to [0, 1] on the encoded branch exactly as `raw_look.film` does.
    public var image: PlanarImage
    public var kHighlight: Double
    public var kAverage: Double
    public var percentile: Double
    /// Halation glow and pre-grain stops (only when `captureStages`).
    public var glow: [Float]?
    public var stopsPregrain: [[Float]]?

    public var k: Double { min(kHighlight, kAverage) }
    public var metering: String { kHighlight <= kAverage ? "highlight" : "average" }
}

/// `raw_look.film()`: 6 MP scene-linear sRGB -> display sRGB. A line-by-line port of APP_SPEC.md §5.2.
public struct FilmModel: Sendable {
    public let params: FilmParams
    public let lut: PrintLUT
    /// The print timing's fixed matrices (`raw_look.print_timing`): linear sRGB -> Bradford cones and back,
    /// and daylight's cone responses. Computed once here so a corrupt params file fails at load, not per photo.
    let toLMS: [[Double]]
    let fromLMS: [[Double]]
    let daylightLMS: [Double]

    public init(params: FilmParams, lut: PrintLUT) throws {
        self.params = params
        self.lut = lut
        guard let srgbToXYZ = Matrix3.inverse(params.xyzToSrgb) else { throw FilmCoreError.invalidParams("xyz_to_srgb is singular") }
        toLMS = Matrix3.multiply(params.bradford, srgbToXYZ)
        guard let fromLMS = Matrix3.inverse(toLMS) else { throw FilmCoreError.invalidParams("bradford · xyz_to_srgb⁻¹ is singular") }
        self.fromLMS = fromLMS
        daylightLMS = Matrix3.apply(toLMS, [1, 1, 1])
    }

    public static func bundled() throws -> FilmModel {
        let (params, lut) = try FilmParams.bundled()
        return try FilmModel(params: params, lut: lut)
    }

    /// Consumes `input` so its planes are reused as the working buffers (no 72 MB copy at 6 MP).
    public func render(_ input: consuming PlanarImage, noise: Noise, white: [Double]?,
                       captureStages: Bool = false) throws -> FilmResult {
        let p = params
        let (w, h, n) = (input.width, input.height, input.width * input.height)
        let d = p.halationDownsample
        guard w % d == 0, h % d == 0 else {
            throw FilmCoreError.badSize("\(w)×\(h) is not divisible by \(d); the halation downsample needs it")
        }
        // Take the planes out of `input` so each array is uniquely owned and mutated in place
        var planes = input.planes
        input.planes = []
        var b = planes.removeLast(), g = planes.removeLast(), r = planes.removeLast()
        let luma = p.luma.map(Float.init)

        // 1. Meter: highlights, capped at a normal average exposure
        var lum = [Float](repeating: 0, count: n)
        for i in 0..<n { lum[i] = luma[0] * r[i] + luma[1] * g[i] + luma[2] * b[i] }
        guard lum.allSatisfy(\.isFinite) else { throw FilmCoreError.nonFinite }
        let floor = Float(p.meterFloor)
        let logSum = lum.withUnsafeBufferPointer { l in
            var s = 0.0
            for v in l { s += log(Double(max(v, floor))) }
            return s
        }
        // k must match numpy bit for bit: a 1-ulp difference moves near-black pixels, where the crosstalk
        // nearly cancels, visibly. k_highlight is formed in Float like numpy's float32 percentile. k_average's
        // log-average is accumulated and exponentiated in Double on both sides (numpy sums pairwise, this loop
        // sequentially: they agree to ~1e-13, far inside float32's 6e-8 step) and rounded to float32 once.
        let pct = Float(Self.percentile(&lum, p.highlightPercentile))   // reorders lum; it's reused below
        let kHighlight = Float(p.midGrey * pow(2, p.highlightStops)) / max(pct, Float(p.meterFloor))
        let kAverage = Float(p.midGrey * pow(2, p.averageStops) / exp(logSum / Double(n)))
        let k = min(kHighlight, kAverage)

        // 2. Print timing, then dye crosstalk, on the exposed light as one 3×3, floored so log2 stays finite
        //    (in Double: the matrix's negative terms cancel almost all of a deep shadow's light, and Float32
        //    loses it there)
        // 3. Vignette: 2^(−stops · smoothstep(r, start, end)^power), r the corner-normalised radius of
        //    integer pixel indices (np.ogrid, not pixel centres)
        let m = Matrix3.multiply(p.crosstalk, printTiming(white))
        let lumaD = p.luma
        let clampFloor = p.clampFloor
        let (cx, cy) = (Double(w) / 2, Double(h) / 2)
        var excess = lum   // lum's buffer, no longer needed, holds the excess
        lum = []
        let halationThreshold = p.midGrey * pow(2, p.halationStops)
        r.withUnsafeMutableBufferPointer { r in
            g.withUnsafeMutableBufferPointer { g in
                b.withUnsafeMutableBufferPointer { b in
                    excess.withUnsafeMutableBufferPointer { e in
                        parallelRows(h) { y in
                            let dy = (Double(y) - cy) / cy
                            for x in 0..<w {
                                let i = y * w + x
                                let radius = hypot((Double(x) - cx) / cx, dy) / 2.0.squareRoot()
                                let t = min(max((radius - p.vignetteStart) / (p.vignetteEnd - p.vignetteStart), 0), 1)
                                let gain = pow(2, -p.vignetteStops * pow(t * t * (3 - 2 * t), p.vignettePower))
                                let (r0, g0, b0) = (Double(r[i] * k), Double(g[i] * k), Double(b[i] * k))
                                let r1 = max(m[0][0] * r0 + m[0][1] * g0 + m[0][2] * b0, clampFloor) * gain
                                let g1 = max(m[1][0] * r0 + m[1][1] * g0 + m[1][2] * b0, clampFloor) * gain
                                let b1 = max(m[2][0] * r0 + m[2][1] * g0 + m[2][2] * b0, clampFloor) * gain
                                (r[i], g[i], b[i]) = (Float(r1), Float(g1), Float(b1))
                                // 4a. Light over the halation threshold
                                e[i] = Float(max(lumaD[0] * r1 + lumaD[1] * g1 + lumaD[2] * b1 - halationThreshold, 0))
                            }
                        }
                    }
                }
            }
        }

        // 4b. Halation: the excess, blurred wide, returns mostly into red
        let glow = wideBlur(excess, width: w, height: h, sigma: p.halationSigma * Double(max(w, h)))
        excess = []
        let tint = p.halationTint.map(Float.init)
        let strength = Float(p.halationStrength)
        let midGrey = Float(p.midGrey)

        // 5. Negative: stops from mid grey, plus monochrome grain
        let grain: [Float]? = switch noise {
        case .none: nil
        case .injected(let field): field
        case .seeded(let seed): Grain.field(seed: seed, width: w, height: h, params: p)
        }
        if let grain, grain.count != n { throw FilmCoreError.badSize("noise has \(grain.count) values, expected \(n)") }
        let stages = (0..<3).map { _ in UnsafeMutableBufferPointer<Float>.allocate(capacity: captureStages ? n : 0) }
        defer { stages.forEach { $0.deallocate() } }
        let grainStops = Float(p.grainStops)

        // 6. Print curve per channel, 7. sRGB encode
        let lutStep = (p.lutMax - p.lutMin) / Double(p.lutSize - 1)
        r.withUnsafeMutableBufferPointer { r in
            g.withUnsafeMutableBufferPointer { g in
                b.withUnsafeMutableBufferPointer { b in
                    parallelRows(h) { y in
                        for i in (y * w)..<(y * w + w) {
                            let gl = strength * glow[i]
                            var s = (log2((r[i] + gl * tint[0]) / midGrey),
                                     log2((g[i] + gl * tint[1]) / midGrey),
                                     log2((b[i] + gl * tint[2]) / midGrey))
                            if captureStages { (stages[0][i], stages[1][i], stages[2][i]) = s }
                            if let grain {
                                let gs = grainStops * grain[i]
                                s = (s.0 + gs, s.1 + gs, s.2 + gs)
                            }
                            r[i] = Self.encode(lookup(s.0, channel: 0, step: lutStep))
                            g[i] = Self.encode(lookup(s.1, channel: 1, step: lutStep))
                            b[i] = Self.encode(lookup(s.2, channel: 2, step: lutStep))
                        }
                    }
                }
            }
        }
        return FilmResult(image: PlanarImage(width: w, height: h, planes: [r, g, b]),
                          kHighlight: Double(kHighlight), kAverage: Double(kAverage), percentile: Double(pct),
                          glow: captureStages ? glow : nil, stopsPregrain: captureStages ? stages.map(Array.init) : nil)
    }

    /// `raw_look.print_timing`: a 3×3 on linear sRGB that adapts the light's colour `white` (G = 1)
    /// `whiteBalance` of the way to daylight in Bradford cone space, keeping the white's luminance. Identity
    /// without a white (a DNG with no AsShotNeutral prints with the daylight balance alone) or for a white
    /// whose cone responses aren't all positive and finite.
    public func printTiming(_ white: [Double]?) -> [[Double]] {
        guard let w = white else { return Matrix3.identity }
        let light = Matrix3.apply(toLMS, w)
        guard light.allSatisfy({ $0.isFinite && $0 > 0 }) else { return Matrix3.identity }
        let gain = (0..<3).map { pow(daylightLMS[$0] / light[$0], params.whiteBalance) }
        // numpy's association: (inv(to_lms) @ diag(gain)) @ to_lms
        let a = Matrix3.multiply(Matrix3.multiply(fromLMS, Matrix3.diagonal(gain)), toLMS)
        let scale = Matrix3.dot(params.luma, w) / Matrix3.dot(params.luma, Matrix3.apply(a, w))
        return a.map { row in row.map { $0 * scale } }
    }

    /// `raw_look.wide_blur`: Pillow BOX down by the halation factor, Gaussian at σ/factor, Pillow BILINEAR back up.
    func wideBlur(_ x: [Float], width w: Int, height h: Int, sigma: Double) -> [Float] {
        let d = params.halationDownsample
        let small = Filters.pilResize(x, width: w, height: h, to: w / d, h / d, kernel: .box)
        let blurred = Filters.gaussianBlur(small, width: w / d, height: h / d, sigma: sigma / Double(d),
                                           truncation: params.blurTruncation)
        return Filters.pilResize(blurred, width: w / d, height: h / d, to: w, h, kernel: .bilinear)
    }

    /// `np.interp(stops, linspace(lut_min, lut_max, lut_size), lut[:, c])`, clamped at both ends.
    @inline(__always)
    func lookup(_ stops: Float, channel c: Int, step: Double) -> Double {
        let x = Double(stops)
        let last = params.lutSize - 1
        if x <= params.lutMin { return Double(lut.values[c]) }
        if x >= params.lutMax { return Double(lut.values[last * 3 + c]) }
        var j = min(Int((x - params.lutMin) / step), last - 1)
        // linspace's own grid points (i·step + start, last = stop), so the bracket matches np.interp's search
        func xp(_ i: Int) -> Double { i == last ? params.lutMax : Double(i) * step + params.lutMin }
        while j > 0 && xp(j) > x { j -= 1 }
        while j < last - 1 && xp(j + 1) <= x { j += 1 }
        let (x0, x1) = (xp(j), xp(j + 1))
        let (y0, y1) = (Double(lut.values[j * 3 + c]), Double(lut.values[(j + 1) * 3 + c]))
        if x == x0 { return y0 }
        return (y1 - y0) / (x1 - x0) * (x - x0) + y0
    }

    /// sRGB OETF exactly as raw_look's last line: the linear branch unclipped, the power branch clipped.
    @inline(__always)
    static func encode(_ lin: Double) -> Float {
        Float(lin <= 0.0031308 ? lin * 12.92 : 1.055 * pow(min(max(lin, 0), 1), 1 / 2.4) - 0.055)
    }

    /// `np.percentile(values, pct)` with numpy's default linear method: the two order statistics around
    /// rank (N − 1)·pct/100 by quickselect, interpolated with numpy's `_lerp`.
    /// Reorders `a` (quickselect in place).
    static func percentile(_ a: inout [Float], _ pct: Double) -> Double {
        let q = Double(a.count - 1) * pct / 100
        let lo = Int(q.rounded(.down))
        let t = q - Double(lo)
        let (v0, v1): (Double, Double) = a.withUnsafeMutableBufferPointer { buf in
            quickselect(buf, lo)
            let next = lo + 1 < buf.count ? buf[(lo + 1)...].min()! : buf[lo]
            return (Double(buf[lo]), Double(next))
        }
        let diff = v1 - v0
        return t >= 0.5 ? v1 - diff * (1 - t) : v0 + diff * t
    }

    /// Puts the k-th smallest element at index k, with nothing smaller after it.
    static func quickselect(_ a: UnsafeMutableBufferPointer<Float>, _ k: Int) {
        var (lo, hi) = (0, a.count - 1)
        while hi > lo {
            let mid = lo + (hi - lo) / 2
            if a[mid] < a[lo] { a.swapAt(mid, lo) }
            if a[hi] < a[lo] { a.swapAt(hi, lo) }
            if a[hi] < a[mid] { a.swapAt(hi, mid) }
            let pivot = a[mid]
            var (i, j) = (lo, hi)
            while i <= j {
                while a[i] < pivot { i += 1 }
                while a[j] > pivot { j -= 1 }
                if i <= j {
                    a.swapAt(i, j)
                    i += 1
                    j -= 1
                }
            }
            if k <= j { hi = j } else if k >= i { lo = i } else { return }
        }
    }
}
