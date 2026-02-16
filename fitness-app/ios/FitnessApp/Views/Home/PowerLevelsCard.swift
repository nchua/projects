import SwiftUI

// MARK: - Big Three Lift Model

struct BigThreeLift: Identifiable {
    let id = UUID()
    let name: String
    let e1rm: Double
    let trendPercent: Double?

    var shortName: String {
        switch name.lowercased() {
        case "barbell back squat", "squat": return "Squat"
        case "barbell bench press", "bench press", "bench": return "Bench"
        case "conventional deadlift", "deadlift": return "Deadlift"
        default: return name
        }
    }

    var liftColor: Color {
        switch shortName.lowercased() {
        case "squat": return Color(hex: "FF6B6B")
        case "bench": return Color.systemPrimary
        case "deadlift": return Color(hex: "7B61FF")
        default: return .systemPrimary
        }
    }
}

// MARK: - Power Levels Card (Consolidated)

struct PowerLevelsCard: View {
    let lifts: [BigThreeLift]
    @Binding var selectedTab: Int

    private var hasData: Bool {
        lifts.contains { $0.e1rm > 0 }
    }

    /// Highest e1RM across all lifts (used as progress bar ceiling)
    private var maxE1rm: Double {
        lifts.map(\.e1rm).max() ?? 1
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Section Header
            HStack {
                Text("Power Levels")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(.textPrimary)

                Spacer()

                Button {
                    selectedTab = 4
                } label: {
                    Text("Details")
                        .font(.system(size: 13))
                        .foregroundColor(.systemPrimary)
                }
            }
            .padding(.horizontal, 20)

            if hasData {
                // Consolidated 3-column card
                HStack(spacing: 0) {
                    ForEach(Array(lifts.enumerated()), id: \.element.id) { index, lift in
                        if lift.e1rm > 0 {
                            PowerLevelColumn(
                                lift: lift,
                                progressFraction: lift.e1rm / maxE1rm
                            )

                            if index < lifts.count - 1 {
                                // Vertical divider
                                Rectangle()
                                    .fill(Color.white.opacity(0.06))
                                    .frame(width: 1)
                                    .padding(.vertical, 8)
                            }
                        }
                    }
                }
                .padding(20)
                .edgeFlowCard()
                .padding(.horizontal, 20)
            } else {
                // Empty state
                VStack(spacing: 14) {
                    Image(systemName: "chart.bar.fill")
                        .font(.system(size: 24))
                        .foregroundColor(.textMuted)

                    Text("Log workouts with Squat, Bench, or Deadlift to see your power levels")
                        .font(.system(size: 13))
                        .foregroundColor(.textMuted)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(28)
                .background(Color.voidMedium)
                .clipShape(RoundedRectangle(cornerRadius: 20))
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
                        .strokeBorder(
                            Color.white.opacity(0.08),
                            style: StrokeStyle(lineWidth: 1.5, dash: [8, 6])
                        )
                )
                .padding(.horizontal, 20)
            }
        }
    }
}

// MARK: - Single Lift Column

private struct PowerLevelColumn: View {
    let lift: BigThreeLift
    let progressFraction: Double

    var body: some View {
        VStack(spacing: 10) {
            // Label
            HStack(spacing: 5) {
                Circle()
                    .fill(lift.liftColor)
                    .frame(width: 6, height: 6)
                Text(lift.shortName.uppercased())
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(.textSecondary)
                    .tracking(0.5)
            }

            // e1RM value
            HStack(alignment: .lastTextBaseline, spacing: 3) {
                Text(lift.e1rm.formattedWeight)
                    .font(.system(size: 24, weight: .bold))
                    .foregroundColor(lift.liftColor)

                Text("lbs")
                    .font(.system(size: 11))
                    .foregroundColor(.textMuted)
            }

            // Mini progress bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.white.opacity(0.06))
                        .frame(height: 4)

                    RoundedRectangle(cornerRadius: 2)
                        .fill(lift.liftColor)
                        .frame(width: max(geo.size.width * 0.1, geo.size.width * progressFraction), height: 4)
                }
            }
            .frame(width: 56, height: 4)

            // Trend arrow
            TrendBadge(percent: lift.trendPercent)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 4)
    }
}

// MARK: - Trend Badge

private struct TrendBadge: View {
    let percent: Double?

    var body: some View {
        if let pct = percent {
            HStack(spacing: 2) {
                Image(systemName: trendIcon(pct))
                    .font(.system(size: 8, weight: .bold))

                Text(trendText(pct))
                    .font(.system(size: 11, weight: .semibold))
            }
            .foregroundColor(trendColor(pct))
        } else {
            Text("—")
                .font(.system(size: 11))
                .foregroundColor(.textMuted)
        }
    }

    private func trendIcon(_ pct: Double) -> String {
        if pct > 1 { return "arrow.up" }
        if pct < -1 { return "arrow.down" }
        return "minus"
    }

    private func trendText(_ pct: Double) -> String {
        if abs(pct) < 0.1 { return "0.0%" }
        return String(format: "%+.1f%%", pct)
    }

    private func trendColor(_ pct: Double) -> Color {
        if pct > 1 { return Color(hex: "00FF88") }
        if pct < -1 { return Color(hex: "FF6B6B") }
        return .textMuted
    }
}
