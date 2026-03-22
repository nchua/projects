import SwiftUI

/// Circular countdown ring with center number and "Leave at" badge.
struct CountdownRingView: View {
    let minutesRemaining: Int
    let totalMinutes: Int
    let leaveByTime: Date?

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var progress: Double {
        guard totalMinutes > 0 else { return 0 }
        let elapsed = Double(totalMinutes - minutesRemaining)
        return min(max(elapsed / Double(totalMinutes), 0), 1)
    }

    private var ringColor: Color {
        if minutesRemaining <= 0 { return .departRed }
        if minutesRemaining < 10 { return .departRed }
        if minutesRemaining < 30 { return .departOrange }
        return .departPrimary
    }

    var body: some View {
        VStack(spacing: 8) {
            ZStack {
                // Background track
                Circle()
                    .stroke(Color.departBorder, lineWidth: 8)

                // Progress arc
                Circle()
                    .trim(from: 0, to: progress)
                    .stroke(
                        AngularGradient(
                            colors: [ringColor.opacity(0.5), ringColor],
                            center: .center,
                            startAngle: .degrees(0),
                            endAngle: .degrees(360 * progress)
                        ),
                        style: StrokeStyle(lineWidth: 8, lineCap: .round)
                    )
                    .rotationEffect(.degrees(-90))
                    .animation(reduceMotion ? nil : .easeInOut(duration: 0.8), value: progress)

                // Center content
                VStack(spacing: 2) {
                    Text("\(max(0, minutesRemaining))")
                        .font(.departCountdown)
                        .foregroundStyle(ringColor)
                        .contentTransition(.numericText())
                        .animation(reduceMotion ? nil : .spring(duration: 0.3), value: minutesRemaining)

                    Text("minutes")
                        .font(.departOverline)
                        .foregroundStyle(Color.departTextSecondary)
                }
            }
            .frame(width: 160, height: 160)

            // Leave at badge
            if let leaveByTime {
                Text("Leave at \(leaveByTime.shortTimeString)")
                    .font(.departCaption)
                    .foregroundStyle(Color.departTextSecondary)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 4)
                    .background(Color.departSurface)
                    .clipShape(Capsule())
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Departure countdown")
        .accessibilityValue("\(max(0, minutesRemaining)) minutes until departure")
    }
}
