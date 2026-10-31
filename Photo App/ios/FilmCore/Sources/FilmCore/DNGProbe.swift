import Foundation

/// Minimal TIFF reader for the ProRAW gate (APP_SPEC.md §5.1.1) and for the colour tags behind the print
/// timing (§5.1.7). ImageIO only describes the IFD0 preview of a DNG, so this walks IFD0's SubIFDs itself and
/// looks for LinearRaw (Photometric 34892). It reads IFD0's rational colour tags itself too: ImageIO's `{DNG}`
/// dictionary hands them back as float32 numbers, and the as-shot white must be the exact
/// numerator / denominator doubles that Pillow gives numpy.
public enum DNGProbe {
    static let photometric: UInt16 = 262, subIFDs: UInt16 = 330, linearRaw = 34892
    static let colorMatrix2: UInt16 = 50722, analogBalance: UInt16 = 50727, asShotNeutral: UInt16 = 50728

    /// IFD0's colour tags for `Decoder.asShotWhite` (`raw_look.as_shot_white`): ColorMatrix2 (XYZ -> camera,
    /// row-major), AnalogBalance (identity when absent, per the DNG spec) and AsShotNeutral (nil when absent).
    public struct ColorTags: Sendable {
        public let colorMatrix2: [[Double]]
        public let analogBalance: [Double]
        public let asShotNeutral: [Double]?
    }

    /// True if IFD0 or one of its SubIFDs is LinearRaw (demosaiced, as Apple ProRAW is).
    public static func isLinearRaw(_ url: URL) -> Bool {
        withTIFF(url) { tiff, ifd0 -> Bool? in
            guard let entries = tiff.entries(at: ifd0) else { return false }
            if entries[photometric]?.first == UInt32(linearRaw) { return true }
            for offset in entries[subIFDs] ?? [] {
                if tiff.entries(at: UInt64(offset))?[photometric]?.first == UInt32(linearRaw) { return true }
            }
            return false
        } ?? false
    }

    /// IFD0's colour tags, or nil if the file isn't a TIFF or has no 3×3 ColorMatrix2.
    public static func colorTags(_ url: URL) -> ColorTags? {
        withTIFF(url) { tiff, ifd0 -> ColorTags? in
            guard let rationals = tiff.rationals(at: ifd0), let m = rationals[colorMatrix2], m.count == 9 else { return nil }
            let balance = rationals[analogBalance] ?? [1, 1, 1]
            let neutral = rationals[asShotNeutral]
            guard balance.count == 3, neutral == nil || neutral?.count == 3 else { return nil }
            return ColorTags(colorMatrix2: [Array(m[0..<3]), Array(m[3..<6]), Array(m[6..<9])],
                             analogBalance: balance, asShotNeutral: neutral)
        }
    }

    /// Opens `url`, checks the TIFF header and calls `body` with a reader and IFD0's offset; nil if not a TIFF.
    static func withTIFF<T>(_ url: URL, _ body: (Reader, UInt64) -> T?) -> T? {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return nil }
        defer { try? handle.close() }
        guard let header = read(handle, 0, 8), header.count == 8 else { return nil }
        let little: Bool
        switch (header[0], header[1]) {
        case (0x49, 0x49): little = true
        case (0x4d, 0x4d): little = false
        default: return nil
        }
        let tiff = Reader(handle: handle, little: little)
        guard tiff.u16(at: header, 2) == 42, let ifd0 = tiff.u32(at: header, 4) else { return nil }
        return body(tiff, UInt64(ifd0))
    }

    static func read(_ handle: FileHandle, _ offset: UInt64, _ count: Int) -> [UInt8]? {
        guard (try? handle.seek(toOffset: offset)) != nil, let data = try? handle.read(upToCount: count) else { return nil }
        return [UInt8](data)
    }

    struct Reader {
        let handle: FileHandle
        let little: Bool

        /// One directory entry: its TIFF type, value count and all of its value bytes (inline, or read from
        /// the far offset when they don't fit the entry's 4 bytes).
        struct Entry {
            let type: UInt16
            let count: Int
            let bytes: [UInt8]
        }

        func u16(at b: [UInt8], _ i: Int) -> UInt16? {
            guard i + 2 <= b.count else { return nil }
            return little ? UInt16(b[i]) | UInt16(b[i + 1]) << 8 : UInt16(b[i]) << 8 | UInt16(b[i + 1])
        }

        func u32(at b: [UInt8], _ i: Int) -> UInt32? {
            guard let lo = u16(at: b, little ? i : i + 2), let hi = u16(at: b, little ? i + 2 : i) else { return nil }
            return UInt32(hi) << 16 | UInt32(lo)
        }

        /// The entries of the IFD at `offset` whose type is in `types`, with `size` bytes per value. Entries
        /// with more than 63 values or truncated bytes are skipped, so a damaged file fails the item instead
        /// of trapping; nil if the directory itself can't be read.
        func directory(at offset: UInt64, types: Set<UInt16>, size: (UInt16) -> Int) -> [UInt16: Entry]? {
            guard let countBytes = DNGProbe.read(handle, offset, 2), let count = u16(at: countBytes, 0),
                  let b = DNGProbe.read(handle, offset + 2, Int(count) * 12) else { return nil }
            var out: [UInt16: Entry] = [:]
            for e in 0..<Int(count) {
                let base = e * 12
                guard base + 12 <= b.count, let tag = u16(at: b, base), let type = u16(at: b, base + 2),
                      let n = u32(at: b, base + 4), types.contains(type), n > 0, n < 64 else { continue }
                let length = Int(n) * size(type)
                var bytes = Array(b[(base + 8)..<(base + 12)])
                if length > 4 {
                    guard let ptr = u32(at: b, base + 8), let far = DNGProbe.read(handle, UInt64(ptr), length),
                          far.count == length else { continue }
                    bytes = far
                }
                out[tag] = Entry(type: type, count: Int(n), bytes: bytes)
            }
            return out
        }

        /// Tag -> values, for SHORT (3) / LONG (4) / IFD (13) tags of the IFD at `offset`.
        func entries(at offset: UInt64) -> [UInt16: [UInt32]]? {
            directory(at: offset, types: [3, 4, 13]) { $0 == 3 ? 2 : 4 }?.mapValues { e in
                (0..<e.count).compactMap { e.type == 3 ? u16(at: e.bytes, $0 * 2).map(UInt32.init) : u32(at: e.bytes, $0 * 4) }
            }
        }

        /// Tag -> values, for RATIONAL (5) / SRATIONAL (10) tags of the IFD at `offset`, as doubles
        /// (`Double(numerator) / Double(denominator)`, as Pillow hands them to numpy).
        func rationals(at offset: UInt64) -> [UInt16: [Double]]? {
            directory(at: offset, types: [5, 10]) { _ in 8 }?.mapValues { e in
                (0..<e.count).compactMap { k -> Double? in
                    guard let num = u32(at: e.bytes, k * 8), let den = u32(at: e.bytes, k * 8 + 4) else { return nil }
                    return e.type == 5 ? Double(num) / Double(den) : Double(Int32(bitPattern: num)) / Double(Int32(bitPattern: den))
                }
            }
        }
    }
}
