//
//  QuestDetailView.swift
//  FitnessApp
//
//  Workout detail (quest summary + per-exercise objective cards).
//  Extracted from HistoryView.swift when the History tab was removed
//  (ARISE v2 Phase 0) — still used by HuntView and StatsView.
//

import SwiftUI

// MARK: - Quest Detail

struct QuestDetailView: View {
    let workoutId: String
    @ObservedObject var viewModel: HistoryViewModel

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

                    Text(formatDate(workout.date))
                        .font(.ariseHeader(size: 20, weight: .bold))
                        .foregroundColor(.textPrimary)
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

            // Stats row — duration/calories/exertion for activities, otherwise
            // objectives/sets/RPE for a logged strength quest.
            HStack(spacing: 24) {
                if isActivity {
                    if let duration = workout.durationMinutes {
                        statCell(value: "\(duration)", label: "MINUTES", color: .systemPrimary)
                    }
                    if let calories = workout.calories {
                        statCell(value: "\(calories)", label: "CALORIES", color: .textPrimary)
                    }
                    if let strain = workout.strain {
                        statCell(value: String(format: "%.1f", strain), label: "STRAIN", color: .gold)
                    } else if let exertion = workout.exertionScore {
                        statCell(value: String(format: "%.1f", exertion), label: "EXERTION", color: .gold)
                    }
                } else {
                    statCell(value: "\(workout.exercises.count)", label: "OBJECTIVES", color: .systemPrimary)
                    statCell(value: "\(totalSets)", label: "SETS", color: .textPrimary)
                    if let rpe = workout.sessionRpe {
                        statCell(value: "\(rpe)", label: "RPE", color: .gold)
                    }
                }

                Spacer()
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
        isActivity ? (workout.activityType?.uppercased() ?? "ACTIVITY LOGGED") : "HUNT COMPLETE"
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

    private func formatDate(_ dateString: String) -> String {
        dateString.parseISO8601Date()?.formattedMedium ?? dateString
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
