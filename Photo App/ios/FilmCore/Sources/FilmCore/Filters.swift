import Foundation

/// Ports of the two filters `raw_look.py` borrows from numpy and Pillow, with their exact conventions
/// (APP_SPEC.md §5.2 step 4): numpy's separable Gaussian with edge padding, and Pillow's two-pass
/// float resampler (horizontal pass first, double accumulation, float32 between passes).
enum Filters {
    /// `raw_look.blur`: separable Gaussian cut at `truncation`·σ (radius at least 1), kernel normalised to 1,
    /// edge-replicate padding, vertical pass then horizontal, double precision in between.
    static func gaussianBlur(_ src: [Float], width w: Int, height h: Int, sigma: Double, truncation: Int) -> [Float] {
        let k = gaussianKernel(sigma: sigma, truncation: truncation)
        let r = k.count / 2

        var mid = [Double](repeating: 0, count: w * h)
        src.withUnsafeBufferPointer { s in
            mid.withUnsafeMutableBufferPointer { m in
                parallelRows(h) { y in
                    for x in 0..<w {
                        var acc = 0.0
                        for i in 0...(2 * r) {
                            acc += Double(s[min(max(y + i - r, 0), h - 1) * w + x]) * k[i]
                        }
                        m[y * w + x] = acc
                    }
                }
            }
        }
        var out = [Float](repeating: 0, count: w * h)
        mid.withUnsafeBufferPointer { m in
            out.withUnsafeMutableBufferPointer { o in
                parallelRows(h) { y in
                    let row = y * w
                    for x in 0..<w {
                        var acc = 0.0
                        for i in 0...(2 * r) { acc += m[row + min(max(x + i - r, 0), w - 1)] * k[i] }
                        o[row + x] = Float(acc)
                    }
                }
            }
        }
        return out
    }

    /// The normalised 1-D kernel `raw_look.blur` uses: radius max(1, int(truncation·σ)).
    static func gaussianKernel(sigma: Double, truncation: Int) -> [Double] {
        let r = max(1, Int(Double(truncation) * sigma))
        let k = (-r...r).map { exp(-0.5 * pow(Double($0) / sigma, 2)) }
        let sum = k.reduce(0, +)
        return k.map { $0 / sum }
    }

    enum Kernel { case box, bilinear }

    /// Pillow's `Image.resize` on a mode "F" image with BOX or BILINEAR.
    static func pilResize(_ src: [Float], width: Int, height: Int, to outW: Int, _ outH: Int, kernel: Kernel) -> [Float] {
        let (hb, hk, hn) = coefficients(inSize: width, outSize: outW, kernel: kernel)
        var tmp = [Float](repeating: 0, count: outW * height)
        src.withUnsafeBufferPointer { s in
            tmp.withUnsafeMutableBufferPointer { t in
                parallelRows(height) { y in
                    for x in 0..<outW {
                        var ss = 0.0
                        for i in 0..<hn[x] { ss += Double(s[y * width + hb[x] + i]) * hk[x * 8 + i] }
                        t[y * outW + x] = Float(ss)
                    }
                }
            }
        }
        let (vb, vk, vn) = coefficients(inSize: height, outSize: outH, kernel: kernel)
        var out = [Float](repeating: 0, count: outW * outH)
        tmp.withUnsafeBufferPointer { t in
            out.withUnsafeMutableBufferPointer { o in
                parallelRows(outH) { y in
                    for x in 0..<outW {
                        var ss = 0.0
                        for i in 0..<vn[y] { ss += Double(t[(vb[y] + i) * outW + x]) * vk[y * 8 + i] }
                        o[y * outW + x] = Float(ss)
                    }
                }
            }
        }
        return out
    }

    /// Pillow's `precompute_coeffs` (Resample.c): per output index, the first source index, up to 8
    /// normalised weights, and their count. Support is 0.5 (box) or 1 (bilinear), times the scale when reducing.
    private static func coefficients(inSize: Int, outSize: Int, kernel: Kernel) -> ([Int], [Double], [Int]) {
        let scale = Double(inSize) / Double(outSize)
        let filterscale = max(scale, 1)
        let support = (kernel == .box ? 0.5 : 1.0) * filterscale
        let ss = 1 / filterscale
        var bounds = [Int](repeating: 0, count: outSize), counts = bounds
        var weights = [Double](repeating: 0, count: outSize * 8)
        for xx in 0..<outSize {
            let center = (Double(xx) + 0.5) * scale
            let xmin = max(Int(center - support + 0.5), 0)   // C casts truncate toward zero, like Int()
            let xmax = min(Int(center + support + 0.5), inSize) - xmin
            precondition(xmax <= 8, "resample support wider than this port handles")
            var ww = 0.0
            for x in 0..<xmax {
                let t = (Double(x + xmin) - center + 0.5) * ss
                let w: Double = switch kernel {
                case .box: (t > -0.5 && t <= 0.5) ? 1 : 0
                case .bilinear: abs(t) < 1 ? 1 - abs(t) : 0
                }
                weights[xx * 8 + x] = w
                ww += w
            }
            if ww != 0 { for x in 0..<xmax { weights[xx * 8 + x] /= ww } }
            bounds[xx] = xmin
            counts[xx] = xmax
        }
        return (bounds, weights, counts)
    }
}

/// Runs `body(row)` for every row in 0..<rows, spread across cores in contiguous bands.
func parallelRows(_ rows: Int, _ body: (Int) -> Void) {
    let bands = min(rows, ProcessInfo.processInfo.activeProcessorCount * 4)
    DispatchQueue.concurrentPerform(iterations: bands) { band in
        for y in (rows * band / bands)..<(rows * (band + 1) / bands) { body(y) }
    }
}
