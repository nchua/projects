import SwiftUI

struct HistoryView: View {
    @StateObject private var viewModel = HistoryViewModel()
    @State private var showCalendar = true

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                VStack(spacing: 0) {
                    // Header
                    QuestArchiveHeader(showCalendar: $showCalendar)

                    // Calendar Toggle
                    if showCalendar {
                        AriseCalendarView(
                            selectedDate: $viewModel.selectedDate,
                            displayedMonth: $viewModel.displayedMonth,
                            datesWithWorkouts: viewModel.datesWithWorkouts
                        )
                        // Force calendar to re-render when workout dates change
                        .id(viewModel.datesWithWorkouts.hashValue)
                        .padding()
                        .background(Color.voidMedium)
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.ariseBorder, lineWidth: 1)
                        )
                        .overlay(
                            // Top glow line
                            Rectangle()
                                .fill(Color.systemPrimary.opacity(0.2))
                                .frame(height: 1),
                            alignment: .top
                        )
                        .padding(.horizontal)
                        .padding(.bottom, 16)
                    }

                    // Quest List
                    if viewModel.isLoading && viewModel.workouts.isEmpty {
                        Spacer()
                        SwiftUI.ProgressView()
                            .tint(.systemPrimary)
                        Spacer()
                    } else if viewModel.workouts.isEmpty {
                        Spacer()
                        EmptyQuestArchiveView()
                        Spacer()
                    } else {
                        List {
                            ForEach(Array(workoutsToShow.enumerated()), id: \.element.id) { index, workout in
                                NavigationLink {
                                    QuestDetailView(
                                        workoutId: workout.id,
                                        viewModel: viewModel
                                    )
                                } label: {
                                    CompletedQuestRow(workout: workout)
                                        .fadeIn(delay: Double(index) * 0.05)
                                }
                                .listRowBackground(Color.voidMedium)
                                .listRowSeparatorTint(Color.ariseBorder)
                                .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                    Button(role: .destructive) {
                                        Task {
                                            await viewModel.deleteWorkout(workout)
                                        }
                                    } label: {
                                        Label("Delete", systemImage: "trash")
                                    }
                                }
                            }

                            if viewModel.hasMoreWorkouts && !showCalendar {
                                Button {
                                    Task {
                                        await viewModel.loadWorkouts()
                                    }
                                } label: {
                                    HStack {
                                        Spacer()
                                        if viewModel.isLoading {
                                            SwiftUI.ProgressView()
                                                .tint(.systemPrimary)
                                        } else {
                                            HStack(spacing: 8) {
                                                Text("LOAD MORE")
                                                    .font(.ariseMono(size: 12, weight: .semibold))
                                                    .tracking(1)
                                                Image(systemName: "chevron.down")
                                                    .font(.system(size: 10, weight: .bold))
                                            }
                                            .foregroundColor(.systemPrimary)
                                        }
                                        Spacer()
                                    }
                                    .padding(.vertical, 16)
                                }
                                .listRowBackground(Color.voidDark)
                            }
                        }
                        .listStyle(.plain)
                        .scrollContentBackground(.hidden)
                    }
                }
            }
            .navigationBarHidden(true)
            .refreshable {
                await viewModel.loadWorkouts(refresh: true)
            }
        }
        .task {
            await viewModel.loadWorkouts(refresh: true)
        }
    }

    private var workoutsToShow: [WorkoutSummaryResponse] {
        if showCalendar {
            return viewModel.workoutsForDate(viewModel.selectedDate)
        } else {
            return viewModel.workouts
        }
    }
}

// MARK: - Header

struct QuestArchiveHeader: View {
    @Binding var showCalendar: Bool

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("[ ARCHIVE ]")
                    .font(.ariseMono(size: 11, weight: .medium))
                    .foregroundColor(.systemPrimary)
                    .tracking(2)

                Text("Quest Log")
                    .font(.ariseHeader(size: 24, weight: .bold))
                    .foregroundColor(.textPrimary)
            }

            Spacer()

            Button {
                withAnimation(.smoothSpring) {
                    showCalendar.toggle()
                }
            } label: {
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(showCalendar ? Color.systemPrimary.opacity(0.1) : Color.voidLight)
                        .frame(width: 40, height: 40)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(showCalendar ? Color.systemPrimary.opacity(0.3) : Color.ariseBorder, lineWidth: 1)
                        )

                    Image(systemName: showCalendar ? "list.bullet" : "calendar")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(showCalendar ? .systemPrimary : .textSecondary)
                }
            }
        }
        .padding()
    }
}

// MARK: - Calendar

struct AriseCalendarView: View {
    @Binding var selectedDate: Date
    @Binding var displayedMonth: Date
    let datesWithWorkouts: Set<String>

    private let calendar = Calendar.current
    private let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMMM yyyy"
        return formatter
    }()

    var body: some View {
        VStack(spacing: 16) {
            // Month Navigation
            HStack {
                Button {
                    withAnimation(.smoothSpring) {
                        displayedMonth = calendar.date(byAdding: .month, value: -1, to: displayedMonth) ?? displayedMonth
                    }
                } label: {
                    ZStack {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Color.voidLight)
                            .frame(width: 32, height: 32)

                        Image(systemName: "chevron.left")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.textSecondary)
                    }
                }

                Spacer()

                Text(dateFormatter.string(from: displayedMonth).uppercased())
                    .font(.ariseHeader(size: 14, weight: .semibold))
                    .foregroundColor(.textPrimary)
                    .tracking(1)

                Spacer()

                Button {
                    withAnimation(.smoothSpring) {
                        displayedMonth = calendar.date(byAdding: .month, value: 1, to: displayedMonth) ?? displayedMonth
                    }
                } label: {
                    ZStack {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Color.voidLight)
                            .frame(width: 32, height: 32)

                        Image(systemName: "chevron.right")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.textSecondary)
                    }
                }
            }

            // Day Headers
            HStack(spacing: 0) {
                ForEach(["S", "M", "T", "W", "T", "F", "S"], id: \.self) { day in
                    Text(day)
                        .font(.ariseMono(size: 10, weight: .semibold))
                        .foregroundColor(.textMuted)
                        .tracking(1)
                        .frame(maxWidth: .infinity)
                }
            }

            // Calendar Grid
            let days = daysInMonth()
            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 7), spacing: 6) {
                ForEach(days, id: \.self) { date in
                    if let date = date {
                        AriseCalendarDayCell(
                            date: date,
                            isSelected: calendar.isDate(date, inSameDayAs: selectedDate),
                            hasWorkout: hasWorkout(on: date),
                            isToday: calendar.isDateInToday(date)
                        ) {
                            withAnimation(.quickSpring) {
                                selectedDate = date
                            }
                        }
                    } else {
                        Text("")
                            .frame(height: 40)
                    }
                }
            }
        }
    }

    private func daysInMonth() -> [Date?] {
        guard let range = calendar.range(of: .day, in: .month, for: displayedMonth),
              let firstDay = calendar.date(from: calendar.dateComponents([.year, .month], from: displayedMonth))
        else { return [] }

        let firstWeekday = calendar.component(.weekday, from: firstDay)
        var days: [Date?] = Array(repeating: nil, count: firstWeekday - 1)

        for day in range {
            if let date = calendar.date(byAdding: .day, value: day - 1, to: firstDay) {
                days.append(date)
            }
        }

        return days
    }

    private func hasWorkout(on date: Date) -> Bool {
        // Use local timezone DateFormatter to match how workout dates are stored
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone.current
        return datesWithWorkouts.contains(formatter.string(from: date))
    }
}

struct AriseCalendarDayCell: View {
    let date: Date
    let isSelected: Bool
    let hasWorkout: Bool
    let isToday: Bool
    let onTap: () -> Void

    private let calendar = Calendar.current

    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 4) {
                Text("\(calendar.component(.day, from: date))")
                    .font(.ariseMono(size: 14, weight: isSelected || isToday ? .semibold : .regular))
                    .foregroundColor(textColor)

                // Quest completion indicator
                if hasWorkout {
                    RoundedRectangle(cornerRadius: 1)
                        .fill(Color.successGreen)
                        .frame(width: 12, height: 3)
                } else {
                    Rectangle()
                        .fill(Color.clear)
                        .frame(width: 12, height: 3)
                }
            }
            .frame(height: 44)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 4)
                    .fill(isSelected ? Color.systemPrimary.opacity(0.15) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(
                        isToday ? Color.systemPrimary : (isSelected ? Color.systemPrimary.opacity(0.3) : Color.clear),
                        lineWidth: isToday ? 2 : 1
                    )
            )
            .shadow(color: isSelected ? Color.systemPrimaryGlow.opacity(0.3) : .clear, radius: 4, x: 0, y: 0)
        }
    }

    private var textColor: Color {
        if isSelected {
            return .systemPrimary
        } else if hasWorkout {
            return .textPrimary
        } else {
            return .textMuted
        }
    }
}

// MARK: - Quest List

struct CompletedQuestRow: View {
    let workout: WorkoutSummaryResponse

    /// Whether this is a WHOOP activity (could be cardio or weightlifting)
    private var isWhoopActivity: Bool {
        workout.isWhoopActivity == true
    }

    /// Whether this WHOOP activity has exercises (weightlifting vs pure cardio)
    private var hasExercises: Bool {
        workout.exerciseCount > 0
    }

    /// Color for the left indicator - orange for pure cardio WHOOP, green for workouts with sets
    private var indicatorColor: Color {
        (isWhoopActivity && !hasExercises) ? .orange : .successGreen
    }

    /// Badge text and icon depend on activity type
    private var badgeText: String {
        if isWhoopActivity && !hasExercises {
            return "ACTIVITY"
        }
        return "COMPLETE"
    }

    private var badgeIcon: String {
        if isWhoopActivity && !hasExercises {
            return "flame.fill"
        }
        return "checkmark"
    }

    var body: some View {
        HStack(spacing: 0) {
            // Left completion indicator
            Rectangle()
                .fill(indicatorColor)
                .frame(width: 4)

            HStack(spacing: 12) {
                // Quest info
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 8) {
                        Text(formatDate(workout.date))
                            .font(.ariseHeader(size: 15, weight: .semibold))
                            .foregroundColor(.textPrimary)

                        // Completed/Activity badge
                        HStack(spacing: 4) {
                            Image(systemName: badgeIcon)
                                .font(.system(size: 8, weight: .bold))
                            Text(badgeText)
                                .font(.ariseMono(size: 9, weight: .semibold))
                                .tracking(0.5)
                        }
                        .foregroundColor(indicatorColor)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(indicatorColor.opacity(0.1))
                        .cornerRadius(2)

                        // WHOOP indicator for activities with exercises
                        if isWhoopActivity && hasExercises {
                            HStack(spacing: 2) {
                                Image(systemName: "applewatch")
                                    .font(.system(size: 7, weight: .semibold))
                                Text("WHOOP")
                                    .font(.ariseMono(size: 8, weight: .semibold))
                                    .tracking(0.5)
                            }
                            .foregroundColor(.orange)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 2)
                            .background(Color.orange.opacity(0.1))
                            .cornerRadius(2)
                        }
                    }

                    if isWhoopActivity && !hasExercises {
                        // Pure cardio WHOOP activity: show activity type, strain, calories
                        HStack(spacing: 16) {
                            if let activityType = workout.activityType {
                                HStack(spacing: 4) {
                                    Image(systemName: activityIconName(for: activityType))
                                        .font(.system(size: 10))
                                        .foregroundColor(.orange)
                                    Text(activityType)
                                        .font(.ariseMono(size: 11, weight: .semibold))
                                        .foregroundColor(.textPrimary)
                                }
                            }

                            if let strain = workout.strain {
                                HStack(spacing: 4) {
                                    Image(systemName: "bolt.fill")
                                        .font(.system(size: 10))
                                        .foregroundColor(.textMuted)
                                    Text(String(format: "%.1f strain", strain))
                                        .font(.ariseMono(size: 11))
                                        .foregroundColor(.textSecondary)
                                }
                            }

                            if let calories = workout.calories {
                                HStack(spacing: 4) {
                                    Image(systemName: "flame")
                                        .font(.system(size: 10))
                                        .foregroundColor(.textMuted)
                                    Text("\(calories) cal")
                                        .font(.ariseMono(size: 11))
                                        .foregroundColor(.textSecondary)
                                }
                            }
                        }
                    } else {
                        // Gym workout or WHOOP weightlifting: show objectives and sets
                        HStack(spacing: 16) {
                            HStack(spacing: 4) {
                                Image(systemName: "scroll.fill")
                                    .font(.system(size: 10))
                                    .foregroundColor(.textMuted)
                                Text("\(workout.exerciseCount) objectives")
                                    .font(.ariseMono(size: 11))
                                    .foregroundColor(.textSecondary)
                            }

                            HStack(spacing: 4) {
                                Image(systemName: "square.stack.fill")
                                    .font(.system(size: 10))
                                    .foregroundColor(.textMuted)
                                Text("\(workout.totalSets) sets")
                                    .font(.ariseMono(size: 11))
                                    .foregroundColor(.textSecondary)
                            }

                            // Show strain for WHOOP weightlifting activities
                            if isWhoopActivity, let strain = workout.strain {
                                HStack(spacing: 4) {
                                    Image(systemName: "bolt.fill")
                                        .font(.system(size: 10))
                                        .foregroundColor(.orange)
                                    Text(String(format: "%.1f", strain))
                                        .font(.ariseMono(size: 11))
                                        .foregroundColor(.orange)
                                }
                            }
                        }

                        // Only show notes for non-WHOOP workouts (WHOOP notes contain metadata)
                        if !isWhoopActivity, let notes = workout.notes, !notes.isEmpty {
                            Text(notes)
                                .font(.ariseMono(size: 11))
                                .foregroundColor(.textMuted)
                                .lineLimit(1)
                                .italic()
                        }
                    }
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.textMuted)
            }
            .padding(16)
        }
    }

    private func formatDate(_ dateString: String) -> String {
        dateString.parseISO8601Date()?.formattedMedium ?? dateString
    }

    /// Return an appropriate SF Symbol icon for the activity type
    private func activityIconName(for activityType: String) -> String {
        let type = activityType.lowercased()
        if type.contains("tennis") { return "figure.tennis" }
        if type.contains("run") { return "figure.run" }
        if type.contains("walk") { return "figure.walk" }
        if type.contains("cycle") || type.contains("bike") { return "figure.outdoor.cycle" }
        if type.contains("swim") { return "figure.pool.swim" }
        if type.contains("yoga") { return "figure.yoga" }
        if type.contains("hik") { return "figure.hiking" }
        if type.contains("basketball") { return "figure.basketball" }
        if type.contains("soccer") || type.contains("football") { return "figure.soccer" }
        if type.contains("golf") { return "figure.golf" }
        if type.contains("functional") || type.contains("weight") || type.contains("strength") { return "figure.strengthtraining.functional" }
        return "figure.mixed.cardio"
    }
}

struct EmptyQuestArchiveView: View {
    @State private var showContent = false

    var body: some View {
        VStack(spacing: 20) {
            ZStack {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.voidLight)
                    .frame(width: 80, height: 80)

                Image(systemName: "scroll")
                    .font(.system(size: 36))
                    .foregroundColor(.textMuted)
            }
            .opacity(showContent ? 1 : 0)
            .scaleEffect(showContent ? 1 : 0.8)

            VStack(spacing: 8) {
                Text("No Quests Recorded")
                    .font(.ariseHeader(size: 18, weight: .semibold))
                    .foregroundColor(.textPrimary)

                Text("Complete training quests to build\nyour archive of achievements")
                    .font(.ariseMono(size: 13))
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
                    .lineSpacing(4)
            }
            .opacity(showContent ? 1 : 0)
        }
        .padding(32)
        .onAppear {
            withAnimation(.easeOut(duration: 0.5).delay(0.2)) {
                showContent = true
            }
        }
    }
}

// MARK: - Quest Detail

struct QuestDetailView: View {
    let workoutId: String
    @ObservedObject var viewModel: HistoryViewModel

    var body: some View {
        ZStack {
            VoidBackground(showGrid: false, glowIntensity: 0.03)

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

                        // Section Header
                        AriseSectionHeader(title: "Completed Objectives")
                            .padding(.horizontal)
                            .fadeIn(delay: 0.1)

                        // Exercises
                        ForEach(Array(workout.exercises.enumerated()), id: \.element.id) { index, exercise in
                            ObjectiveDetailCard(exercise: exercise)
                                .padding(.horizontal)
                                .fadeIn(delay: 0.15 + Double(index) * 0.05)
                        }
                    }
                    .padding(.vertical)
                }
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 32))
                        .foregroundColor(.warningRed)

                    Text("Quest data not found")
                        .font(.ariseMono(size: 14))
                        .foregroundColor(.textSecondary)
                }
            }
        }
        .navigationTitle("Quest Details")
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
                    Text("QUEST COMPLETED")
                        .font(.ariseMono(size: 10, weight: .semibold))
                        .foregroundColor(.successGreen)
                        .tracking(1)

                    Text(formatDate(workout.date))
                        .font(.ariseHeader(size: 20, weight: .bold))
                        .foregroundColor(.textPrimary)
                }

                Spacer()

                // Completion checkmark
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.successGreen)
                        .frame(width: 40, height: 40)

                    Image(systemName: "checkmark")
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(.voidBlack)
                }
            }

            AriseDivider()

            // Stats row
            HStack(spacing: 24) {
                // Objectives
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(workout.exercises.count)")
                        .font(.ariseDisplay(size: 20, weight: .bold))
                        .foregroundColor(.systemPrimary)
                    Text("OBJECTIVES")
                        .font(.ariseMono(size: 9, weight: .medium))
                        .foregroundColor(.textMuted)
                        .tracking(0.5)
                }

                // Total Sets
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(totalSets)")
                        .font(.ariseDisplay(size: 20, weight: .bold))
                        .foregroundColor(.textPrimary)
                    Text("SETS")
                        .font(.ariseMono(size: 9, weight: .medium))
                        .foregroundColor(.textMuted)
                        .tracking(0.5)
                }

                // Session RPE
                if let rpe = workout.sessionRpe {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(rpe)")
                            .font(.ariseDisplay(size: 20, weight: .bold))
                            .foregroundColor(.gold)
                        Text("RPE")
                            .font(.ariseMono(size: 9, weight: .medium))
                            .foregroundColor(.textMuted)
                            .tracking(0.5)
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
                .fill(Color.successGreen.opacity(0.3))
                .frame(height: 1),
            alignment: .top
        )
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
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

// MARK: - Legacy Aliases

typealias HistoryHeader = QuestArchiveHeader
typealias CalendarView = AriseCalendarView
typealias CalendarDayCell = AriseCalendarDayCell
typealias WorkoutHistoryRow = CompletedQuestRow
typealias EmptyHistoryView = EmptyQuestArchiveView
typealias WorkoutDetailView = QuestDetailView
typealias ExerciseDetailCard = ObjectiveDetailCard

#Preview {
    HistoryView()
}
