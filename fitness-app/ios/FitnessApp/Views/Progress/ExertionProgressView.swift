import SwiftUI
import Charts

/// Power › EXERTION segment (ARISE v2 §7.2): strain + volume weekly trends
/// as two ALIGNED small multiples (never a dual-axis chart), the per-exercise
/// cardiac-cost card, and per-week zone-distribution bars using the locked
/// `AriseHRZoneBar` palette (order + labels carry identity, never color alone).
struct ExertionProgressView: View {
    let exercises: [ExerciseResponse]

    @State private var weekly: [ExertionWeekPoint] = []
    @State private var cardiacCost: CardiacCostResponse?
    @State private var selectedExerciseId: String?
    @State private var isLoading = true

    /// Exercises worth offering in the cardiac-cost picker: prefer big three,
    /// then everything else the user trains.
    private var pickerExercises: [ExerciseResponse] {
        let bigThreeNames = ["squat", "bench press", "deadlift"]
        let big = exercises.filter { ex in bigThreeNames.contains { ex.name.lowercased().contains($0) } }
        let rest = exercises.filter { ex in !bigThreeNames.contains { ex.name.lowercased().contains($0) } }
        return big + rest
    }

    var body: some View {
        VStack(spacing: 20) {
            if isLoading {
                SwiftUI.ProgressView()
                    .tint(.systemPrimary)
                    .padding(.vertical, 60)
            } else {
                strainTrendCard
                volumeTrendCard
                cardiacCostCard
                zoneDistributionCard
            }
        }
        .padding(.horizontal)
        .task {
            await load()
        }
    }

    // MARK: - Loading

    private func load() async {
        isLoading = true
        weekly = (try? await APIClient.shared.getExertionWeekly(weeks: 8)) ?? []
        if selectedExerciseId == nil {
            selectedExerciseId = pickerExercises.first?.id
        }
        await loadCardiacCost()
        isLoading = false
    }

    private func loadCardiacCost() async {
        guard let id = selectedExerciseId else { return }
        cardiacCost = try? await APIClient.shared.getCardiacCost(exerciseId: id)
    }

    // MARK: - Small multiple 1: strain

    private var strainTrendCard: some View {
        chartCard(title: "Weekly Strain") {
            if weekly.allSatisfy({ $0.strainTotal == nil }) {
                noSignalRow("No strain data yet — log wearable or WHOOP hunts.")
            } else {
                Chart(weekly) { point in
                    BarMark(
                        x: .value("Week", shortWeekLabel(point.weekStart)),
                        y: .value("Strain", point.strainTotal ?? 0)
                    )
                    .foregroundStyle(
                        LinearGradient(
                            colors: [Color.orange.opacity(0.5), Color.orange],
                            startPoint: .bottom, endPoint: .top
                        )
                    )
                    .cornerRadius(3)
                }
                .frame(height: 120)
                .chartXAxis { AxisMarks { _ in AxisValueLabel().font(.system(size: 9)) } }
                .chartYAxis { AxisMarks { _ in
                    AxisGridLine().foregroundStyle(Color.white.opacity(0.06))
                    AxisValueLabel().font(.system(size: 9))
                } }
            }
        }
    }

    // MARK: - Small multiple 2: volume (aligned x-axis, separate chart)

    private var volumeTrendCard: some View {
        chartCard(title: "Weekly Volume") {
            Chart(weekly) { point in
                BarMark(
                    x: .value("Week", shortWeekLabel(point.weekStart)),
                    y: .value("Volume", point.volumeLb)
                )
                .foregroundStyle(
                    LinearGradient(
                        colors: [Color.systemPrimary.opacity(0.5), Color.systemPrimary],
                        startPoint: .bottom, endPoint: .top
                    )
                )
                .cornerRadius(3)
            }
            .frame(height: 120)
            .chartXAxis { AxisMarks { _ in AxisValueLabel().font(.system(size: 9)) } }
            .chartYAxis { AxisMarks { _ in
                AxisGridLine().foregroundStyle(Color.white.opacity(0.06))
                AxisValueLabel().font(.system(size: 9))
            } }
        }
    }

    // MARK: - Cardiac cost

    private var cardiacCostCard: some View {
        chartCard(title: "Cardiac Cost") {
            VStack(alignment: .leading, spacing: 12) {
                // Exercise picker
                if !pickerExercises.isEmpty {
                    Menu {
                        ForEach(pickerExercises.prefix(20)) { exercise in
                            Button(exercise.name) {
                                selectedExerciseId = exercise.id
                                Task { await loadCardiacCost() }
                            }
                        }
                    } label: {
                        HStack(spacing: 6) {
                            Text(selectedExerciseName)
                                .font(.ariseMono(size: 12, weight: .semibold))
                                .foregroundColor(.textPrimary)
                            Image(systemName: "chevron.up.chevron.down")
                                .font(.system(size: 9))
                                .foregroundColor(.textMuted)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color.voidLight)
                        .clipShape(Capsule())
                    }
                }

                if let cost = cardiacCost, let matched = cost.matchedSet, !cost.points.isEmpty {
                    // Headline: "−18% cardiac cost vs 8 wks ago"
                    HStack(alignment: .lastTextBaseline, spacing: 8) {
                        if let change = cost.percentChange {
                            Text(String(format: "%+.0f%%", change))
                                .font(.ariseDisplay(size: 28, weight: .bold))
                                .foregroundColor(change <= 0 ? .successGreen : .warningRed)
                        }
                        VStack(alignment: .leading, spacing: 1) {
                            Text("ΔHR at \(Int(matched.weight))×\(matched.reps)")
                                .font(.ariseMono(size: 11))
                                .foregroundColor(.textSecondary)
                            Text(costCopy(cost))
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textMuted)
                        }
                        Spacer()
                    }

                    Chart(cost.points) { point in
                        LineMark(
                            x: .value("Week", shortWeekLabel(point.weekStart)),
                            y: .value("ΔHR", point.deltaHrMedian)
                        )
                        .foregroundStyle(Color.warningRed)
                        .symbol(.circle)
                    }
                    .frame(height: 100)
                    .chartXAxis { AxisMarks { _ in AxisValueLabel().font(.system(size: 9)) } }
                    .chartYAxis { AxisMarks { _ in
                        AxisGridLine().foregroundStyle(Color.white.opacity(0.06))
                        AxisValueLabel().font(.system(size: 9))
                    } }

                    // Confounder footnote (recorded, not modeled — §7.2-2)
                    if let caveat = cost.caveats.first {
                        Text("Not modeled: rest, set position, RPE. \(caveat)")
                            .font(.ariseMono(size: 9))
                            .foregroundColor(.textMuted)
                            .italic()
                            .lineLimit(2)
                    }
                } else {
                    noSignalRow("Needs 2+ weeks of the same set with HR data.")
                }
            }
        }
    }

    // MARK: - Zone distribution

    private var zoneDistributionCard: some View {
        chartCard(title: "Zone Distribution") {
            let weeksWithZones = weekly.filter { !$0.zoneSeconds.isEmpty }
            if weeksWithZones.isEmpty {
                noSignalRow("No HR-zone data yet.")
            } else {
                VStack(spacing: 10) {
                    // Legend renders once, on the last row (labels + fixed
                    // z1→z5 order carry identity — never color alone).
                    ForEach(Array(weeksWithZones.enumerated()), id: \.element.id) { index, point in
                        HStack(alignment: .top, spacing: 10) {
                            Text(shortWeekLabel(point.weekStart))
                                .font(.ariseMono(size: 9, weight: .medium))
                                .foregroundColor(.textMuted)
                                .frame(width: 44, alignment: .leading)
                                .padding(.top, 1)

                            AriseHRZoneBar(
                                zoneSeconds: point.zoneSeconds,
                                height: 10,
                                showLegend: index == weeksWithZones.count - 1
                            )
                        }
                    }
                }
            }
        }
    }

    // MARK: - Shared chrome

    private func chartCard<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            AriseSectionHeader(title: title)
            content()
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.voidMedium)
        .clipShape(RoundedRectangle(cornerRadius: 20))
        .overlay(
            RoundedRectangle(cornerRadius: 20)
                .stroke(Color.glassBorder, lineWidth: 1)
        )
    }

    private func noSignalRow(_ message: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "waveform.slash")
                .font(.system(size: 12))
                .foregroundColor(.textMuted)
            Text(message)
                .font(.ariseMono(size: 11))
                .foregroundColor(.textMuted)
        }
        .padding(.vertical, 12)
    }

    private var selectedExerciseName: String {
        pickerExercises.first(where: { $0.id == selectedExerciseId })?.name ?? "Select exercise"
    }

    private func costCopy(_ cost: CardiacCostResponse) -> String {
        switch cost.trendDirection {
        case "improving": return "Falling ΔHR at the same load — engine building."
        case "regressing": return "ΔHR rising — recovery or conditioning slipping."
        case "stable": return "ΔHR holding steady."
        default: return "Building baseline..."
        }
    }

    private func shortWeekLabel(_ weekStart: String) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        guard let date = formatter.date(from: weekStart) else { return weekStart }
        formatter.dateFormat = "M/d"
        return formatter.string(from: date)
    }
}
