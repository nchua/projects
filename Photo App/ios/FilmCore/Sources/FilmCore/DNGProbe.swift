import Foundation

/// Minimal TIFF reader for the ProRAW gate (APP_SPEC.md §5.1.1). ImageIO only describes the IFD0
/// preview of a DNG, so this walks IFD0's SubIFDs and looks for LinearRaw (Photometric 34892).
public enum DNGProbe {
    static let photometric: UInt16 = 262, subIFDs: UInt16 = 330, linearRaw = 34892

    /// True if IFD0 or one of its SubIFDs is LinearRaw (demosaiced, as Apple ProRAW is).
    public static func isLinearRaw(_ url: URL) -> Bool {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return false }
        defer { try? handle.close() }
        guard let header = read(handle, 0, 8), header.count == 8 else { return false }
        let little: Bool
        switch (header[0], header[1]) {
        case (0x49, 0x49): little = true
        case (0x4d, 0x4d): little = false
        default: return false
        }
        let tiff = Reader(handle: handle, little: little)
        guard tiff.u16(at: header, 2) == 42, let ifd0 = tiff.u32(at: header, 4) else { return false }
        guard let entries = tiff.entries(at: UInt64(ifd0)) else { return false }
        if entries[photometric]?.first == UInt32(linearRaw) { return true }
        for offset in entries[subIFDs] ?? [] {
            if tiff.entries(at: UInt64(offset))?[photometric]?.first == UInt32(linearRaw) { return true }
        }
        return false
    }

    static func read(_ handle: FileHandle, _ offset: UInt64, _ count: Int) -> [UInt8]? {
        guard (try? handle.seek(toOffset: offset)) != nil, let data = try? handle.read(upToCount: count) else { return nil }
        return [UInt8](data)
    }

    struct Reader {
        let handle: FileHandle
        let little: Bool

        func u16(at b: [UInt8], _ i: Int) -> UInt16? {
            guard i + 2 <= b.count else { return nil }
            return little ? UInt16(b[i]) | UInt16(b[i + 1]) << 8 : UInt16(b[i]) << 8 | UInt16(b[i + 1])
        }

        func u32(at b: [UInt8], _ i: Int) -> UInt32? {
            guard let lo = u16(at: b, little ? i : i + 2), let hi = u16(at: b, little ? i + 2 : i) else { return nil }
            return UInt32(hi) << 16 | UInt32(lo)
        }

        /// Tag -> values, for SHORT / LONG / IFD tags (inline or at an offset), of the IFD at `offset`.
        func entries(at offset: UInt64) -> [UInt16: [UInt32]]? {
            guard let countBytes = DNGProbe.read(handle, offset, 2), let count = u16(at: countBytes, 0),
                  let b = DNGProbe.read(handle, offset + 2, Int(count) * 12) else { return nil }
            var out: [UInt16: [UInt32]] = [:]
            for e in 0..<Int(count) {
                let base = e * 12
                guard let tag = u16(at: b, base), let type = u16(at: b, base + 2), let n = u32(at: b, base + 4),
                      [3, 4, 13].contains(type), n > 0, n < 64, base + 12 <= b.count else { continue }
                let size = type == 3 ? 2 : 4
                var bytes = Array(b[(base + 8)..<(base + 12)])
                if Int(n) * size > 4 {
                    guard let ptr = u32(at: b, base + 8), let far = DNGProbe.read(handle, UInt64(ptr), Int(n) * size) else { continue }
                    bytes = far
                }
                out[tag] = (0..<Int(n)).compactMap { size == 2 ? u16(at: bytes, $0 * 2).map(UInt32.init) : u32(at: bytes, $0 * 4) }
            }
            return out
        }
    }
}
