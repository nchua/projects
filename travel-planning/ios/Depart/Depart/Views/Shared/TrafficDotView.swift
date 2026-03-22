import SwiftUI

/// Color-coded dot indicating traffic/congestion level.
/// Always paired with text label for color-blind accessibility.
struct TrafficDotView: View {
    let congestion: CongestionLevel
    let showLabel: Bool

    init(_ congestion: CongestionLevel, showLabel: Bool = false) {
        self.congestion = congestion
        self.showLabel = showLabel
    }

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(congestion.color)
                .frame(width: 8, height: 8)

            if showLabel {
                Text(congestion.displayName)
                    .font(.departCaption)
                    .foregroundStyle(Color.departTextSecondary)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Traffic conditions")
        .accessibilityValue(congestion.displayName)
    }
}
