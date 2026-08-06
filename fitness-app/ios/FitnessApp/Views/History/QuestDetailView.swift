//
//  QuestDetailView.swift
//  FitnessApp
//
//  Workout detail (quest summary + per-exercise objective cards).
//  Extracted from HistoryView.swift when the History tab was removed
//  (ARISE v2 Phase 0). QuestDetailView itself is presented by StatsView;
//  the summary/objective cards are shared with HuntView.
//

import SwiftUI

// MARK: - Quest Detail

/// Shared surface for a workout-detail loader. HuntViewModel and
/// HistoryViewModel both provide these members, so the Hunt Log and Power
/// tabs share this one detail view instead of drifting near-copies
/// (v2.1 — the old HuntDetailView duplicate lacked the HR section and the
/// cardio-activity objectives suppression).
protocol WorkoutDetailProviding: ObservableObject {
    var isLoadingDetail: Bool { get }
    var selectedWorkout: WorkoutResponse? { get }
    func loadWorkoutDetail(id: String) async
    /// Rename the hunt ("" clears back to the suggested name) and refresh
    /// both the detail and the owning list.
    func renameWorkout(id: String, to name: String) async
}

extension HistoryViewModel: WorkoutDetailProviding {}
extension HuntViewModel: WorkoutDetailProviding {}

struct QuestDetailView<ViewModel: WorkoutDetailProviding>: View {
    let workoutId: String
    @ObservedObject var viewModel: ViewModel
    @State private var showRenameAlert = false
    @State private var renameText = ""

    var body: some View {
        ZStack {
            VoidBackground(glowIntensity: 0.03)

            if viewModel.isLoadingDetail {
                SwiftUI.ProgressView()
                    .tint(.systemPrimary)
            } else if let workout = viewModel.selectedWorkout {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        // Header Card
                        QuestSummaryCard(workout: workout)
                            .padding(.horizontal)
                            .fadeIn(delay: 0)

                        // Session-level heart rate (avg/peak/strain + zone bar) —
                        // only when HR data exists; absent for legacy workouts.
                        if workout.hasHRData {
                            AriseWorkoutHRSection(workout: workout, title: "Heart Rate")
                                .padding(.horizontal)
                                .fadeIn(delay: 0.05)
                        }

                        // Per-mile splits — cardio sessions with granular
                        // distance data (imported or re-synced after mile_splits).
                        if workout.mileSplits?.isEmpty == false {
                            AriseMileSplitsCard(workout: workout)
                                .padding(.horizontal)
                                .fadeIn(delay: 0.08)
                        }

                        // Objectives — a cardio/sport activity has no real sets to
                        // show, so suppress this section for activities (the HR
                        // block above carries the meaningful detail).
                        if !(workout.isActivity ?? false) {
                            AriseSectionHeader(title: "Completed Objectives")
                                .padding(.horizontal)
                                .fadeIn(delay: 0.1)

                            ForEach(Array(workout.exercises.enumerated()), id: \.element.id) { index, exercise in
                                ObjectiveDetailCard(exercise: exercise)
                                    .padding(.horizontal)
                                    .fadeIn(delay: 0.15 + Double(index) * 0.05)
                            }
                        }
                    }
                    .padding(.vertical)
                }
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 32))
                        .foregroundColor(.warningRed)

                    Text("Hunt data not found")
                        .font(.ariseMono(size: 14))
                        .foregroundColor(.textSecondary)
                }
            }
        }
        .navigationTitle("Hunt Details")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(Color.voidDark, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    renameText = viewModel.selectedWorkout?.name
                        ?? viewModel.selectedWorkout?.suggestedName
                        ?? ""
                    showRenameAlert = true
                } label: {
                    Image(systemName: "pencil")
                        .foregroundColor(.systemPrimary)
                }
                .disabled(viewModel.selectedWorkout == nil)
                .accessibilityLabel("Rename hunt")
            }
        }
        .alert("Name This Hunt", isPresented: $showRenameAlert) {
            TextField("Hunt name", text: $renameText)
            Button("Save") {
                Task {
                    await viewModel.renameWorkout(
                        id: workoutId,
                        to: renameText.trimmingCharacters(in: .whitespaces)
                    )
                }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Leave empty to go back to the suggested name.")
        }
        .task {
            await viewModel.loadWorkoutDetail(id: workoutId)
        }
    }
}

struct QuestSummaryCard: View {
    let workout: WorkoutResponse

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header with date and status
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(headerLabel)
                        .font(.ariseMono(size: 10, weight: .semibold))
                        .foregroundColor(accentColor)
                        .tracking(1)

                    // Hunt name (custom → suggestion), falling back to the date
                    Text(workout.displayName ?? formatDate(workout.date))
                        .font(.ariseHeader(size: 20, weight: .bold))
                        .foregroundColor(.textPrimary)

                    if workout.displayName != nil {
                        Text(formatDate(workout.date))
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.textMuted)
                    }
                }

                Spacer()

                // Completion / activity marker
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(accentColor)
                        .frame(width: 40, height: 40)

                    Image(systemName: isActivity ? "flame.fill" : "checkmark")
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(.voidBlack)
                }
            }

            AriseDivider()

            // Stats — distance-first for cardio with mileage (wrapping to a
            // second row), otherwise objectives/sets/RPE for a strength quest.
            if isActivity {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(Array(activityStats.chunked(into: 3).enumerated()), id: \.offset) { _, row in
                        HStack(spacing: 24) {
                            ForEach(row, id: \.label) { stat in
                                statCell(value: stat.value, label: stat.label, color: stat.color)
                            }
                            Spacer()
                        }
                    }
                }
            } else {
                HStack(spacing: 24) {
                    statCell(value: "\(workout.exercises.count)", label: "OBJECTIVES", color: .systemPrimary)
                    statCell(value: "\(totalSets)", label: "SETS", color: .textPrimary)
                    if let rpe = workout.sessionRpe {
                        statCell(value: "\(rpe)", label: "RPE", color: .gold)
                    }
                    Spacer()
                }
            }

            // Notes
            if let notes = workout.notes, !notes.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("HUNTER NOTES")
                        .font(.ariseMono(size: 10, weight: .semibold))
                        .foregroundColor(.textMuted)
                        .tracking(1)

                    Text(notes)
                        .font(.ariseMono(size: 13))
                        .foregroundColor(.textSecondary)
                        .italic()
                }
            }
        }
        .padding(20)
        .background(Color.voidMedium)
        .overlay(
            Rectangle()
                .fill(accentColor.opacity(0.3))
                .frame(height: 1),
            alignment: .top
        )
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }

    private var isActivity: Bool { workout.isActivity ?? false }

    /// Orange for cardio/sport activities, green for completed strength quests.
    private var accentColor: Color { isActivity ? .orange : .successGreen }

    private var headerLabel: String {
        guard isActivity else { return "HUNT COMPLETE" }
        // Skip the type eyebrow when it's already the headline (suggested name)
        if let type = workout.activityType,
           type.lowercased() != (workout.displayName ?? "").lowercased() {
            return type.uppercased()
        }
        return "ACTIVITY LOGGED"
    }

    @ViewBuilder
    private func statCell(value: String, label: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value)
                .font(.ariseDisplay(size: 20, weight: .bold))
                .foregroundColor(color)
            Text(label)
                .font(.ariseMono(size: 9, weight: .medium))
                .foregroundColor(.textMuted)
                .tracking(0.5)
        }
    }

    private var totalSets: Int {
        workout.exercises.reduce(0) { $0 + $1.sets.count }
    }

    /// Activity stat cells in display order: distance + pace lead when the
    /// session carries mileage; the classic trio follows.
    private var activityStats: [(value: String, label: String, color: Color)] {
        var stats: [(value: String, label: String, color: Color)] = []
        if let miles = workout.distanceMiles {
            stats.append((String(format: "%.2f", miles), "MILES", .systemPrimary))
            if let pace = workout.paceSecondsPerMile {
                stats.append((pace.asMinSecString, "PACE /MI", .textPrimary))
            }
        }
        if let duration = workout.durationMinutes {
            stats.append(("\(duration)", "MINUTES", stats.isEmpty ? .systemPrimary : .textPrimary))
        }
        if let calories = workout.calories {
            stats.append(("\(calories)", "CALORIES", .textPrimary))
        }
        // Unified Strain (ARISE v2 §7.1) — one metric everywhere.
        if let strain = workout.ariseStrain {
            stats.append((String(format: "%.1f", strain.value), "STRAIN", .gold))
        }
        return stats
    }

    private func formatDate(_ dateString: String) -> String {
        dateString.parseISO8601Date()?.formattedMedium ?? dateString
    }
}

/// Per-mile split list for a cardio activity. Bars scale to the slowest mile
/// (longer bar = slower mile); the fastest full mile reads green. A trailing
/// partial mile (total time minus full-mile time) shows muted.
struct AriseMileSplitsCard: View {
    let workout: WorkoutResponse

    private struct SplitRow {
        let label: String        // "1", "2", … or "0.24" for the partial tail
        let seconds: Int
        let paceSecPerMile: Int  // == seconds for full miles; scaled for the tail
        let isPartial: Bool
    }

    var body: some View {
        let rows = splitRows
        let maxPace = rows.map(\.paceSecPerMile).max() ?? 1
        // "Fastest" needs a comparison — require at least two FULL miles.
        let fullMilePaces = rows.filter { !$0.isPartial }.map(\.paceSecPerMile)
        let fastestPace = fullMilePaces.count > 1 ? fullMilePaces.min() : nil

        return VStack(alignment: .leading, spacing: 8) {
            AriseSectionHeader(title: "Mile Splits")

            VStack(spacing: 10) {
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    splitRowView(row, maxPace: maxPace, fastestPace: fastestPace)
                }
            }
            .padding(16)
            .background(Color.voidMedium)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
        }
    }

    private var splitRows: [SplitRow] {
        guard let splits = workout.mileSplits, !splits.isEmpty else { return [] }
        var rows = splits.enumerated().map { index, seconds in
            SplitRow(label: "\(index + 1)", seconds: seconds,
                     paceSecPerMile: seconds, isPartial: false)
        }
        // Trailing partial mile: whatever time the full-mile splits don't cover.
        if let miles = workout.distanceMiles, let total = workout.durationSeconds {
            let remainderMiles = miles - Double(splits.count)
            let remainderSeconds = total - splits.reduce(0, +)
            if remainderMiles >= 0.05, remainderSeconds > 0 {
                rows.append(SplitRow(
                    label: String(format: "%.2f", remainderMiles),
                    seconds: remainderSeconds,
                    paceSecPerMile: Int((Double(remainderSeconds) / remainderMiles).rounded()),
                    isPartial: true
                ))
            }
        }
        return rows
    }

    private func splitRowView(_ row: SplitRow, maxPace: Int, fastestPace: Int?) -> some View {
        let isFastest = !row.isPartial && row.paceSecPerMile == fastestPace
        return HStack(spacing: 12) {
            Text("MI \(row.label)")
                .font(.ariseMono(size: 11, weight: .medium))
                .foregroundColor(row.isPartial ? .textMuted : .textSecondary)
                .frame(width: 56, alignment: .leading)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Rectangle().fill(Color.voidLight)
                    Rectangle()
                        .fill(isFastest
                              ? Color.successGreen
                              : Color.systemPrimary.opacity(row.isPartial ? 0.35 : 0.75))
                        .frame(width: geo.size.width * CGFloat(row.paceSecPerMile) / CGFloat(max(maxPace, 1)))
                }
            }
            .frame(height: 6)
            .cornerRadius(3)

            Text(row.seconds.asMinSecString)
                .font(.ariseMono(size: 13, weight: .semibold))
                .foregroundColor(isFastest ? .successGreen : .textPrimary)
                .frame(width: 52, alignment: .trailing)
        }
    }
}

struct ObjectiveDetailCard: View {
    let exercise: WorkoutExerciseResponse

    var exerciseColor: Color {
        Color.exerciseColor(for: exercise.exerciseName)
    }

    var fantasyName: String {
        ExerciseFantasyNames.fantasyName(for: exercise.exerciseName)
    }

    // Calculate best set (highest e1RM)
    var bestSet: SetResponse? {
        exercise.sets.max(by: { ($0.e1rm ?? 0) < ($1.e1rm ?? 0) })
    }

    /// Show the per-set HR column only when at least one set carries HR.
    var showHRCol: Bool {
        exercise.sets.contains { $0.avgHeartRate != nil || $0.peakHeartRate != nil }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header with left color border
            HStack(spacing: 0) {
                Rectangle()
                    .fill(exerciseColor)
                    .frame(width: 4)

                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(exercise.exerciseName)
                            .font(.ariseHeader(size: 16, weight: .semibold))
                            .foregroundColor(.textPrimary)

                        Text("\"\(fantasyName)\"")
                            .font(.ariseMono(size: 11))
                            .foregroundColor(.textMuted)
                            .italic()
                    }

                    Spacer()

                    // Best e1RM badge
                    if let best = bestSet, let e1rm = best.e1rm {
                        VStack(alignment: .trailing, spacing: 2) {
                            Text("\(e1rm.formattedWeight)")
                                .font(.ariseDisplay(size: 18, weight: .bold))
                                .foregroundColor(.gold)
                            Text("BEST e1RM")
                                .font(.ariseMono(size: 8, weight: .semibold))
                                .foregroundColor(.textMuted)
                                .tracking(0.5)
                        }
                    }
                }
                .padding(16)
            }
            .background(Color.voidMedium)

            Rectangle()
                .fill(Color.ariseBorder)
                .frame(height: 1)

            // Set Headers
            HStack {
                Text("SET")
                    .frame(width: 36, alignment: .leading)
                Text("WEIGHT")
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text("REPS")
                    .frame(width: 44, alignment: .center)
                Text("RPE")
                    .frame(width: 36, alignment: .center)
                if showHRCol {
                    Text("HR")
                        .frame(width: 40, alignment: .center)
                }
                Text("e1RM")
                    .frame(width: 56, alignment: .trailing)
            }
            .font(.ariseMono(size: 10, weight: .semibold))
            .foregroundColor(.textMuted)
            .tracking(1)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(Color.voidDark)

            // Sets
            ForEach(Array(exercise.sets.enumerated()), id: \.element.id) { index, set in
                let isBest = bestSet?.id == set.id && set.e1rm != nil

                HStack {
                    // Set number with checkmark
                    ZStack {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(Color.successGreen)
                            .frame(width: 20, height: 20)

                        Image(systemName: "checkmark")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(.voidBlack)
                    }
                    .frame(width: 36, alignment: .leading)

                    Text("\(set.weight.formattedWeight) \(set.weightUnit)")
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .foregroundColor(.textPrimary)

                    Text("\(set.reps)")
                        .frame(width: 44, alignment: .center)
                        .foregroundColor(.textPrimary)

                    Text(set.rpe.map { "\($0)" } ?? "-")
                        .frame(width: 36, alignment: .center)
                        .foregroundColor(.systemPrimary)

                    if showHRCol {
                        let setHR = set.avgHeartRate ?? set.peakHeartRate
                        Text(setHR.map { "\($0)" } ?? "-")
                            .frame(width: 40, alignment: .center)
                            .foregroundColor(setHR.map { AriseHRZoneBar.hrZoneColor(forHR: $0, maxHR: nil) } ?? .textMuted)
                    }

                    Text(set.e1rm.map { "\($0.formattedWeight)" } ?? "-")
                        .frame(width: 56, alignment: .trailing)
                        .foregroundColor(isBest ? .gold : .textSecondary)
                }
                .font(.ariseMono(size: 14))
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(isBest ? Color.gold.opacity(0.05) : Color.clear)

                if index < exercise.sets.count - 1 {
                    Rectangle()
                        .fill(Color.ariseBorder)
                        .frame(height: 1)
                        .padding(.horizontal, 16)
                }
            }
        }
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }
}
