import SwiftUI

/// Pill showing traffic dot + "Light traffic * 22 min drive".
struct TrafficPillView: View {
    let congestion: CongestionLevel
    let travelMinutes: Int?

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(congestion.color)
                .frame(width: 8, height: 8)

            Text(congestion.displayName)
                .font(.departCaption)

            if let travelMinutes {
                Text("·")
                    .foregroundStyle(.secondary)
                Text("\(travelMinutes) min drive")
                    .font(.departCaption)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(.ultraThinMaterial)
        .clipShape(Capsule())
    }
}
