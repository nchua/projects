import SwiftUI
import Charts

// MARK: - Goal Progress Graph View

/// Displays a chart showing projected vs actual e1RM progress toward a goal
struct GoalProgressGraphView: View {
    let progress: GoalProgressResponse

    @State private var selectedDate: Date?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header with status badge
            HStack {
                Text(progress.exerciseName.uppercased())
                    .font(.ariseHeader(size: 16, weight: .bold))
                    .foregroundColor(.textPrimary)
                Spacer()
                StatusBadge(status: progress.status, weeksDifference: progress.weeksDifference)
            }

            // Target info
            let targetDisplay = progress.targetReps == 1
                ? "\(Int(progress.targetWeight)) \(progress.weightUnit)"
                : "\(Int(progress.targetWeight)) \(progress.weightUnit) x \(progress.targetReps)"
            Text("Target: \(targetDisplay) by \(formatDeadline(progress.targetDate))")
                .font(.ariseBody(size: 14))
                .foregroundColor(.textSecondary)

            // Chart
            Chart {
                // Projected line (dotted)
                ForEach(progress.projectedPoints, id: \.date) { point in
                    LineMark(
                        x: .value("Date", parseDate(point.date)),
                        y: .value("e1RM", point.e1rm)
                    )
                    .foregroundStyle(Color.textMuted)
                    .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [5, 5]))
                }

                // Actual line (solid)
                ForEach(progress.actualPoints, id: \.date) { point in
                    LineMark(
                        x: .value("Date", parseDate(point.date)),
                        y: .value("e1RM", point.e1rm)
                    )
                    .foregroundStyle(Color.systemPrimary)
                    .lineStyle(StrokeStyle(lineWidth: 2))
                    .interpolationMethod(.catmullRom)

                    PointMark(
                        x: .value("Date", parseDate(point.date)),
                        y: .value("e1RM", point.e1rm)
                    )
                    .foregroundStyle(Color.systemPrimary)
                    .symbolSize(32)
                }

                // Target line (horizontal)
                RuleMark(y: .value("Target", progress.targetE1rm))
                    .foregroundStyle(Color.gold.opacity(0.5))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                    .annotation(position: .trailing, alignment: .leading) {
                        Text("Target")
                            .font(.ariseMono(size: 9))
                            .foregroundColor(.gold)
                            .padding(.leading, 4)
                    }
            }
            .frame(height: 200)
            .chartXAxis {
                AxisMarks(values: .automatic) { value in
                    AxisValueLabel {
                        if let date = value.as(Date.self) {
                            Text(date.formatted(.dateTime.month(.abbreviated).day()))
                                .font(.ariseMono(size: 9))
                                .foregroundColor(.textMuted)
                        }
                    }
                }
            }
            .chartYAxis {
                AxisMarks(position: .leading) { value in
                    AxisValueLabel {
                        if let val = value.as(Double.self) {
                            Text("\(Int(val))")
                                .font(.ariseMono(size: 9))
                                .foregroundColor(.textMuted)
                        }
                    }
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [4]))
                        .foregroundStyle(Color.ariseBorder)
                }
            }
            .chartLegend(position: .bottom, alignment: .leading) {
                HStack(spacing: 16) {
                    LegendItem(color: .systemPrimary, label: "Actual", dashed: false)
                    LegendItem(color: .textMuted, label: "Projected", dashed: true)
                }
            }

            // Stats row
            HStack(spacing: 0) {
                StatItem(
                    title: "Current",
                    value: progress.currentE1rm != nil ? "\(Int(progress.currentE1rm!)) \(progress.weightUnit)" : "—"
                )
                Divider()
                    .frame(height: 32)
                    .background(Color.ariseBorder)
                StatItem(
                    title: "Weekly Gain",
                    value: progress.weeklyGainRate > 0 ? "+\(String(format: "%.1f", progress.weeklyGainRate)) \(progress.weightUnit)/wk" : "—"
                )
                Divider()
                    .frame(height: 32)
                    .background(Color.ariseBorder)
                StatItem(
                    title: "Needed",
                    value: progress.requiredGainRate > 0 ? "+\(String(format: "%.1f", progress.requiredGainRate)) \(progress.weightUnit)/wk" : "—"
                )
            }
            .padding(.horizontal, 8)
        }
        .padding()
        .background(Color.voidMedium)
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }

    private func parseDate(_ dateString: String) -> Date {
        // Try ISO8601 formats
        let formatters = [
            ISO8601DateFormatter(),
            {
                let f = DateFormatter()
                f.dateFormat = "yyyy-MM-dd"
                f.timeZone = TimeZone(identifier: "UTC")
                return f
            }()
        ]

        for formatter in formatters {
            if let iso = formatter as? ISO8601DateFormatter,
               let date = iso.date(from: dateString) {
                return date
            }
            if let df = formatter as? DateFormatter,
               let date = df.date(from: dateString) {
                return date
            }
        }

        return Date()
    }

    private func formatDeadline(_ dateString: String) -> String {
        let date = parseDate(dateString)
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d"
        return formatter.string(from: date)
    }
}

// MARK: - Status Badge

private struct StatusBadge: View {
    let status: String
    let weeksDifference: Int

    var body: some View {
        Text(statusText)
            .font(.ariseMono(size: 11, weight: .bold))
            .foregroundColor(statusColor)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(statusColor.opacity(0.15))
            .cornerRadius(4)
    }

    private var statusText: String {
        switch status {
        case "ahead":
            return weeksDifference > 0 ? "+\(weeksDifference)w ahead" : "On track"
        case "on_track":
            return "On track"
        case "behind":
            return weeksDifference < 0 ? "\(abs(weeksDifference))w behind" : "Behind"
        default:
            return status.capitalized
        }
    }

    private var statusColor: Color {
        switch status {
        case "ahead":
            return .systemGreen
        case "on_track":
            return .systemPrimary
        case "behind":
            return .systemRed
        default:
            return .textSecondary
        }
    }
}

// MARK: - Legend Item

private struct LegendItem: View {
    let color: Color
    let label: String
    let dashed: Bool

    var body: some View {
        HStack(spacing: 6) {
            Rectangle()
                .fill(color)
                .frame(width: 16, height: 2)
                .overlay(
                    dashed ? Rectangle()
                        .stroke(color, style: StrokeStyle(lineWidth: 2, dash: [3, 3]))
                        .frame(width: 16, height: 2)
                    : nil
                )
            Text(label)
                .font(.ariseMono(size: 10))
                .foregroundColor(.textSecondary)
        }
    }
}

// MARK: - Stat Item

private struct StatItem: View {
    let title: String
    let value: String

    var body: some View {
        VStack(spacing: 2) {
            Text(title.uppercased())
                .font(.ariseMono(size: 9))
                .foregroundColor(.textMuted)
            Text(value)
                .font(.ariseMono(size: 12, weight: .medium))
                .foregroundColor(.textPrimary)
        }
        .frame(maxWidth: .infinity)
    }
}

// MARK: - Preview

#Preview {
    GoalProgressGraphView(
        progress: GoalProgressResponse(
            goalId: "123",
            exerciseName: "Bench Press",
            targetWeight: 225,
            targetReps: 1,
            targetE1rm: 225,
            targetDate: "2026-04-15",
            startingE1rm: 180,
            currentE1rm: 210,
            weightUnit: "lb",
            actualPoints: [
                ProgressPoint(date: "2026-01-01", e1rm: 180),
                ProgressPoint(date: "2026-01-15", e1rm: 190),
                ProgressPoint(date: "2026-02-01", e1rm: 205),
                ProgressPoint(date: "2026-02-04", e1rm: 210)
            ],
            projectedPoints: [
                ProgressPoint(date: "2026-01-01", e1rm: 180),
                ProgressPoint(date: "2026-04-15", e1rm: 225)
            ],
            status: "ahead",
            weeksDifference: 2,
            weeklyGainRate: 4.5,
            requiredGainRate: 3.2
        )
    )
    .padding()
    .background(Color.voidDeep)
}
