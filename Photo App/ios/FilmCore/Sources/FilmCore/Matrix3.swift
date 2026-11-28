import Foundation

/// 3×3 matrices and vectors as `[[Double]]` / `[Double]` (row-major, as numpy and film_params.json hold
/// them), for the as-shot white and the print timing. Everything is Double: the result feeds the crosstalk,
/// whose cancellation in deep shadows amplifies rounding (APP_SPEC.md §11, M1 fix).
enum Matrix3 {
    static let identity: [[Double]] = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

    static func diagonal(_ d: [Double]) -> [[Double]] {
        [[d[0], 0, 0], [0, d[1], 0], [0, 0, d[2]]]
    }

    /// a · b, each term summed left to right like a plain triple loop.
    static func multiply(_ a: [[Double]], _ b: [[Double]]) -> [[Double]] {
        (0..<3).map { i in (0..<3).map { j in a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j] } }
    }

    static func apply(_ m: [[Double]], _ v: [Double]) -> [Double] {
        (0..<3).map { i in m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] }
    }

    static func dot(_ a: [Double], _ b: [Double]) -> Double {
        a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    }

    /// The inverse by cofactors (adjugate / determinant); nil when singular or non-finite.
    static func inverse(_ m: [[Double]]) -> [[Double]]? {
        let (a, b, c) = (m[0][0], m[0][1], m[0][2])
        let (d, e, f) = (m[1][0], m[1][1], m[1][2])
        let (g, h, i) = (m[2][0], m[2][1], m[2][2])
        let c00 = e * i - f * h, c01 = f * g - d * i, c02 = d * h - e * g
        let det = a * c00 + b * c01 + c * c02
        guard det != 0, det.isFinite else { return nil }
        let c10 = c * h - b * i, c11 = a * i - c * g, c12 = b * g - a * h
        let c20 = b * f - c * e, c21 = c * d - a * f, c22 = a * e - b * d
        return [[c00 / det, c10 / det, c20 / det],
                [c01 / det, c11 / det, c21 / det],
                [c02 / det, c12 / det, c22 / det]]
    }
}
