import SwiftUI
import Charts

struct WeeklyReportView: View {
    @StateObject private var viewModel = WeeklyReportViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationView {
            ZStack {
                Color.voidBlack.ignoresSafeArea()

                if viewModel.isLoading && viewModel.report == nil {
                    ProgressView()
                        .tint(.systemPrimary)
                } else if let report = viewModel.report {
                    reportContent(report)
                } else if let error = viewModel.error {
                    errorState(error)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Text("WEEKLY REPORT")
                        .font(.system(size: 13, weight: .bold, design: .monospaced))
                        .foregroundColor(.systemPrimary)
                        .tracking(2)
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button { dismiss() } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.textSecondary)
                    }
                }
            }
        }
        .task {
            await viewModel.loadReport()
        }
    }

    // MARK: - Report Content

    @ViewBuilder
    private func reportContent(_ report: WeeklyProgressReportResponse) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                headerSection(report)

                // Summary stats
                summaryStatsSection(report)

                // Overall pace (only if goals exist)
                if !report.goalReports.isEmpty {
                    paceStatusCard()
                }

                // Goal cards
                if !report.goalReports.isEmpty {
                    goalCardsSection(report.goalReports)
                }

                // Coaching suggestions
                if !report.suggestions.isEmpty {
                    suggestionsSection(report.suggestions)
                }

                // Edge states
                if !report.hasSufficientData {
                    firstWeekBanner()
                }

                Spacer(minLength: 40)
            }
            .padding(.horizontal, 20)
            .padding(.top, 12)
        }
    }

    // MARK: - Header

    private func headerSection(_ report: WeeklyProgressReportResponse) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Week of \(viewModel.weekDateRange)")
                .font(.ariseDisplay(size: 22))
                .foregroundColor(.textPrimary)

            if report.totalWorkouts == 0 {
                Text("No workouts logged yet")
                    .font(.system(size: 14))
                    .foregroundColor(.textMuted)
            }
        }
    }

    // MARK: - Summary Stats

    private func summaryStatsSection(_ report: WeeklyProgressReportResponse) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 12) {
                EdgeFlowStatCard(
                    value: "\(report.totalWorkouts)",
                    label: "Workouts"
                )
                EdgeFlowStatCard(
                    value: viewModel.volumeFormatted,
                    label: "Volume"
                )
                EdgeFlowStatCard(
                    value: "\(report.totalSets)",
                    label: "Sets"
                )
                if let prs = report.prsAchieved.count as Int?, prs > 0 {
                    EdgeFlowStatCard(
                        value: "\(prs)",
                        label: "PRs",
                        accentColor: .gold
                    )
                }
            }
        }
    }

    // MARK: - Pace Status Card

    private func paceStatusCard() -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("Overall Pace")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.textSecondary)

                Text(viewModel.statusLabel)
                    .font(.ariseDisplay(size: 28))
                    .foregroundColor(viewModel.statusColor)
            }

            Spacer()

            // Volume change badge
            if let volChange = viewModel.volumeChangeFormatted {
                VStack(spacing: 2) {
                    Text(volChange)
                        .font(.system(size: 16, weight: .bold, design: .monospaced))
                        .foregroundColor(
                            (viewModel.report?.volumeChangePercent ?? 0) >= 0
                                ? .successGreen
                                : .warningRed
                        )
                    Text("vs last week")
                        .font(.system(size: 10))
                        .foregroundColor(.textMuted)
                }
            }
        }
        .padding(16)
        .edgeFlowCard(accent: viewModel.statusColor, glow: true)
    }

    // MARK: - Goal Cards

    private func goalCardsSection(_ goals: [GoalProgressReportResponse]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Goal Progress")
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(.textPrimary)

            ForEach(goals) { goal in
                goalCard(goal)
            }
        }
    }

    private func goalCard(_ goal: GoalProgressReportResponse) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            // Exercise name + status badge
            HStack {
                Text(goal.exerciseName)
                    .font(.ariseHeader(size: 16))
                    .foregroundColor(.textPrimary)

                Spacer()

                statusBadge(goal.status)
            }

            // e1RM progress
            HStack(spacing: 16) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Current")
                        .font(.system(size: 10))
                        .foregroundColor(.textMuted)
                    Text("\(Int(goal.currentE1rm ?? 0)) \(goal.weightUnit)")
                        .font(.system(size: 18, weight: .bold, design: .monospaced))
                        .foregroundColor(.textPrimary)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text("Target")
                        .font(.system(size: 10))
                        .foregroundColor(.textMuted)
                    Text("\(Int(goal.targetWeight)) \(goal.weightUnit)")
                        .font(.system(size: 18, weight: .bold, design: .monospaced))
                        .foregroundColor(.gold)
                }
                Spacer()
            }

            // Compact progress chart (only if 2+ actual data points)
            if goal.actualPoints.count >= 2 {
                compactProgressChart(goal)
            }

            // Progress bar
            VStack(spacing: 4) {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Color.voidLight)
                            .frame(height: 8)
                        RoundedRectangle(cornerRadius: 4)
                            .fill(statusColor(for: goal.status))
                            .frame(
                                width: max(0, geo.size.width * min(goal.progressPercent / 100, 1.0)),
                                height: 8
                            )
                    }
                }
                .frame(height: 8)

                HStack {
                    Text("\(Int(goal.progressPercent))%")
                        .font(.system(size: 11, weight: .medium, design: .monospaced))
                        .foregroundColor(.textSecondary)
                    Spacer()
                    if goal.weeksRemaining > 0 {
                        Text("\(Int(goal.weeksRemaining))w remaining")
                            .font(.system(size: 11))
                            .foregroundColor(.textMuted)
                    } else {
                        Text("Deadline passed")
                            .font(.system(size: 11))
                            .foregroundColor(.warningRed)
                    }
                }
            }

            // Pace details
            HStack(spacing: 16) {
                if let required = goal.requiredWeeklyGain {
                    paceDetail(label: "Need", value: "+\(String(format: "%.1f", required))/wk")
                }
                if let actual = goal.actualWeeklyGain {
                    paceDetail(label: "Actual", value: "\(actual >= 0 ? "+" : "")\(String(format: "%.1f", actual))/wk")
                }
                if let projected = goal.projectedCompletionDate,
                   let d = projected.parseISO8601Date() {
                    paceDetail(label: "Projected", value: formatShortDate(d))
                }
            }
        }
        .padding(16)
        .edgeFlowCard(accent: statusColor(for: goal.status))
    }

    private func paceDetail(label: String, value: String) -> some View {
        VStack(spacing: 2) {
            Text(label)
                .font(.system(size: 10))
                .foregroundColor(.textMuted)
            Text(value)
                .font(.system(size: 13, weight: .medium, design: .monospaced))
                .foregroundColor(.textSecondary)
        }
    }

    private func statusBadge(_ status: String) -> some View {
        let (label, color) = statusInfo(status)
        return Text(label)
            .font(.system(size: 10, weight: .bold, design: .monospaced))
            .foregroundColor(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(color.opacity(0.15))
            .clipShape(Capsule())
    }

    // MARK: - Suggestions

    private func suggestionsSection(_ suggestions: [CoachingSuggestionResponse]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Coaching")
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(.textPrimary)

            ForEach(suggestions) { suggestion in
                suggestionCard(suggestion)
            }
        }
    }

    private func suggestionCard(_ suggestion: CoachingSuggestionResponse) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: suggestionIcon(suggestion.type))
                .font(.system(size: 16))
                .foregroundColor(suggestionColor(suggestion.priority))
                .frame(width: 24)
                .padding(.top, 2)

            VStack(alignment: .leading, spacing: 4) {
                Text(suggestion.title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.textPrimary)
                Text(suggestion.description)
                    .font(.system(size: 13))
                    .foregroundColor(.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .edgeFlowCard(accent: suggestionColor(suggestion.priority))
    }

    // MARK: - Edge States

    private func firstWeekBanner() -> some View {
        HStack(spacing: 12) {
            Image(systemName: "chart.line.uptrend.xyaxis")
                .font(.system(size: 20))
                .foregroundColor(.systemPrimary)
            VStack(alignment: .leading, spacing: 2) {
                Text("Building your baseline")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.textPrimary)
                Text("Keep logging workouts — predictions unlock after 2 weeks of data.")
                    .font(.system(size: 13))
                    .foregroundColor(.textSecondary)
            }
        }
        .padding(14)
        .edgeFlowCard(accent: .systemPrimary)
    }

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 32))
                .foregroundColor(.warningRed)
            Text("Couldn't load report")
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(.textPrimary)
            Text(message)
                .font(.system(size: 13))
                .foregroundColor(.textSecondary)
                .multilineTextAlignment(.center)
            Button("Try Again") {
                Task { await viewModel.loadReport() }
            }
            .font(.system(size: 14, weight: .semibold))
            .foregroundColor(.systemPrimary)
        }
        .padding(40)
    }

    // MARK: - Compact Progress Chart

    private func compactProgressChart(_ goal: GoalProgressReportResponse) -> some View {
        let lineColor = statusColor(for: goal.status)

        return Chart {
            // Projected line (dashed pace line)
            ForEach(goal.projectedPoints, id: \.date) { point in
                LineMark(
                    x: .value("Date", parseDate(point.date)),
                    y: .value("e1RM", point.e1rm)
                )
                .foregroundStyle(Color.textMuted)
                .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [5, 5]))
            }

            // Actual line (solid, status-colored)
            ForEach(goal.actualPoints, id: \.date) { point in
                LineMark(
                    x: .value("Date", parseDate(point.date)),
                    y: .value("e1RM", point.e1rm)
                )
                .foregroundStyle(lineColor)
                .lineStyle(StrokeStyle(lineWidth: 2))
                .interpolationMethod(.catmullRom)
            }

            // Data points
            ForEach(Array(goal.actualPoints.enumerated()), id: \.element.date) { index, point in
                PointMark(
                    x: .value("Date", parseDate(point.date)),
                    y: .value("e1RM", point.e1rm)
                )
                .foregroundStyle(lineColor)
                .symbolSize(index == goal.actualPoints.count - 1 ? 40 : 24)
            }

            // Target rule mark (horizontal dashed line at target e1RM)
            if let targetE1rm = targetE1rm(for: goal) {
                RuleMark(y: .value("Target", targetE1rm))
                    .foregroundStyle(Color.gold.opacity(0.4))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
            }
        }
        .frame(height: 100)
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 2)) { value in
                AxisValueLabel {
                    if let date = value.as(Date.self) {
                        Text(date.formatted(.dateTime.month(.abbreviated)))
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundColor(.textMuted)
                    }
                }
            }
        }
        .chartYAxis(.hidden)
        .chartLegend(.hidden)
    }

    private func targetE1rm(for goal: GoalProgressReportResponse) -> Double? {
        // Target e1RM is the endpoint of the projected line
        goal.projectedPoints.last?.e1rm
    }

    private func parseDate(_ dateString: String) -> Date {
        let formatters: [Any] = [
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

    // MARK: - Helpers

    private func formatShortDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d"
        return formatter.string(from: date)
    }

    private func statusColor(for status: String) -> Color {
        switch status {
        case "ahead": return .gold
        case "behind": return .warningRed
        default: return .systemPrimary
        }
    }

    private func statusInfo(_ status: String) -> (String, Color) {
        switch status {
        case "ahead": return ("AHEAD", .gold)
        case "behind": return ("BEHIND", .warningRed)
        default: return ("ON TRACK", .systemPrimary)
        }
    }

    private func suggestionIcon(_ type: String) -> String {
        switch type {
        case "volume": return "chart.bar.fill"
        case "plateau": return "arrow.triangle.2.circlepath"
        case "frequency": return "calendar.badge.plus"
        case "slowdown": return "tortoise.fill"
        case "motivation": return "star.fill"
        default: return "lightbulb.fill"
        }
    }

    private func suggestionColor(_ priority: String) -> Color {
        switch priority {
        case "high": return .warningRed
        case "medium": return .gold
        default: return .systemPrimary
        }
    }
}
