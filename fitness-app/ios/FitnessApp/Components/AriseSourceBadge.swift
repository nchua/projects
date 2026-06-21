import SwiftUI

/// Provenance badge showing where a workout's HR data came from. Replaces the
/// old inline orange "WHOOP" badge in History. Keyed on the canonical
/// `hr_source` strings stamped server-side: `"whoop"`, `"apple_watch"` (underscore),
/// `"screenshot"`. Renders `EmptyView` for `nil` / unknown sources.
///
/// Chrome is pixel-identical to the previous inline badge: a small symbol + mono
/// label tinted by the source color over a 10%-opacity background pill.
struct AriseSourceBadge: View {
    let source: String?
    var compact: Bool = false

    private var meta: (symbol: String, color: Color, label: String)? {
        switch source {
        case "whoop":       return ("circle.circle", .orange, "WHOOP")
        case "apple_watch": return ("applewatch", .systemPrimary, "APPLE WATCH")
        case "screenshot":  return ("camera.fill", .textMuted, "SCREENSHOT")
        default:            return nil   // nil / unknown -> no badge
        }
    }

    var body: some View {
        if let meta {
            HStack(spacing: 2) {
                Image(systemName: meta.symbol)
                    .font(.system(size: compact ? 7 : 9, weight: .semibold))
                Text(meta.label)
                    .font(.ariseMono(size: compact ? 8 : 9, weight: .semibold))
                    .tracking(0.5)
            }
            .foregroundColor(meta.color)
            .padding(.horizontal, compact ? 4 : 6)
            .padding(.vertical, 2)
            .background(meta.color.opacity(0.1))
            .cornerRadius(2)
        }
    }
}

#Preview {
    ZStack {
        VoidBackground()
        VStack(alignment: .leading, spacing: 16) {
            AriseSourceBadge(source: "whoop")
            AriseSourceBadge(source: "apple_watch")
            AriseSourceBadge(source: "screenshot")
            AriseSourceBadge(source: "apple_watch", compact: true)
            AriseSourceBadge(source: nil)    // nothing
        }
        .padding()
    }
}
