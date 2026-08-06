import SwiftUI

/// Segmented heart-rate zone bar (ARISE language). A horizontal stack of
/// fixed cold→hot colored segments whose widths are proportional to the seconds
/// spent in each zone, over a `voidLight` track, with an optional wrapping legend.
///
/// Data is the backend `hr_zone_seconds` map (e.g. `{"z1":120,...,"z5":30}`).
/// The palette endpoints are LOCKED (never data-driven): z1 cyan … z5 red+glow.
/// Supports the 5-zone scheme (`z1..z5`, which also covers a `z1/z3/z5` collapse
/// to cyan/gold/red) and a 3-zone `low/mid/high` scheme. Unknown keys are dropped
/// (never a gray mystery segment). Renders `EmptyView` when there is no data.
struct AriseHRZoneBar: View {
    let zoneSeconds: [String: Int]   // {"z1":120,...,"z5":30}
    var height: CGFloat = 12
    var showLegend: Bool = true
    var maxHR: Int? = nil

    // Local-only token for the THRESHOLD zone (z4) — between gold and red.
    private static let hrZ4Orange = Color(hex: "FF8C42")

    private static let zoneOrder5 = ["z1", "z2", "z3", "z4", "z5"]
    private static let zoneOrder3 = ["low", "mid", "high"]

    /// Fixed metadata for a known zone key. Returns `nil` for unknown keys so
    /// they are dropped from both the bar and the legend.
    static func zoneMeta(for key: String) -> (label: String, pct: String, color: Color, glow: Bool)? {
        switch key {
        case "z1":   return ("RECOVERY", "50–60%", .systemPrimary, false)
        case "z2":   return ("AEROBIC", "60–70%", .successGreen, false)
        case "z3":   return ("TEMPO", "70–80%", .gold, false)
        case "z4":   return ("THRESHOLD", "80–90%", hrZ4Orange, false)
        case "z5":   return ("MAX", "90–100%", .warningRed, true)
        case "low":  return ("LOW", "", .systemPrimary, false)
        case "mid":  return ("MID", "", .gold, false)
        case "high": return ("HIGH", "", .warningRed, true)
        default:     return nil
        }
    }

    /// Zone color for a single bpm reading — used to tint per-set HR values.
    /// With `maxHR`, buckets by %max (`<60 z1 … <90 z4, else z5`); without it,
    /// uses absolute bpm thresholds (calibrated to ~190 maxHR).
    static func hrZoneColor(forHR bpm: Int, maxHR: Int?) -> Color {
        let zone: String
        if let maxHR, maxHR > 0 {
            switch Double(bpm) / Double(maxHR) {
            case ..<0.60: zone = "z1"
            case ..<0.70: zone = "z2"
            case ..<0.80: zone = "z3"
            case ..<0.90: zone = "z4"
            default:      zone = "z5"
            }
        } else {
            switch bpm {
            case ..<114: zone = "z1"
            case ..<133: zone = "z2"
            case ..<152: zone = "z3"
            case ..<171: zone = "z4"
            default:     zone = "z5"
            }
        }
        return zoneMeta(for: zone)?.color ?? .textSecondary
    }

    /// Present zone keys (value > 0), in fixed cold→hot order. Unknown keys dropped.
    private var orderedKeys: [String] {
        let present = Set(zoneSeconds.filter { $0.value > 0 }.keys)
        let use3 = !present.isEmpty && present.isSubset(of: Set(Self.zoneOrder3))
        let order = use3 ? Self.zoneOrder3 : Self.zoneOrder5
        return order.filter { present.contains($0) }
    }

    /// True when a map would render at least one segment — i.e. it has ≥1 *known*
    /// zone key with seconds > 0. Callers use this to gate the surrounding section
    /// so an all-zero / unknown-only map doesn't leave a header with nothing under it.
    static func hasRenderableZones(_ zones: [String: Int]?) -> Bool {
        guard let zones else { return false }
        let known = Set(zoneOrder5).union(zoneOrder3)
        return zones.contains { known.contains($0.key) && $0.value > 0 }
    }

    var body: some View {
        let keys = orderedKeys
        let total = keys.reduce(0) { $0 + (zoneSeconds[$1] ?? 0) }

        if keys.isEmpty || total <= 0 {
            EmptyView()   // belt-and-suspenders; callers also guard
        } else {
            VStack(alignment: .leading, spacing: 8) {
                // Segmented bar over a voidLight track
                GeometryReader { geo in
                    HStack(spacing: 0) {
                        ForEach(keys, id: \.self) { key in
                            let secs = zoneSeconds[key] ?? 0
                            let meta = Self.zoneMeta(for: key)
                            Rectangle()
                                .fill(meta?.color ?? .voidLight)
                                .frame(width: geo.size.width * CGFloat(secs) / CGFloat(total))
                                .if(meta?.glow == true) { view in
                                    view.shadow(color: (meta?.color ?? .clear).opacity(0.7), radius: 6, x: 0, y: 0)
                                }
                        }
                    }
                }
                .frame(height: height)
                .background(Color.voidLight)
                .clipShape(RoundedRectangle(cornerRadius: 2))

                if showLegend {
                    legend(keys)
                }
            }
        }
    }

    @ViewBuilder
    private func legend(_ keys: [String]) -> some View {
        FlowLayout(spacing: 12) {
            ForEach(keys, id: \.self) { key in
                if let meta = Self.zoneMeta(for: key) {
                    HStack(spacing: 4) {
                        Circle()
                            .fill(meta.color)
                            .frame(width: 8, height: 8)
                        Text(meta.label)
                            .foregroundColor(.textSecondary)
                        Text(timeLabel(zoneSeconds[key] ?? 0))
                            .foregroundColor(.textMuted)
                        if maxHR != nil, !meta.pct.isEmpty {
                            Text(meta.pct)
                                .foregroundColor(.textMuted)
                        }
                    }
                    .font(.ariseMono(size: 9, weight: .medium))
                    .tracking(0.5)
                }
            }
        }
    }

    private func timeLabel(_ seconds: Int) -> String {
        seconds.asMinSecString
    }
}

#Preview {
    ZStack {
        VoidBackground()
        VStack(spacing: 28) {
            AriseHRZoneBar(zoneSeconds: ["z1": 300, "z2": 600, "z3": 420, "z4": 180, "z5": 60], maxHR: 190)
            AriseHRZoneBar(zoneSeconds: ["z1": 200, "z3": 300, "z5": 120])   // collapsed 3
            AriseHRZoneBar(zoneSeconds: ["low": 200, "mid": 300, "high": 100]) // low/mid/high
            AriseHRZoneBar(zoneSeconds: [:])                                  // empty -> nothing
        }
        .padding()
    }
}
