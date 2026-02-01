import SwiftUI
import PhotosUI

struct QuestsView: View {
    @StateObject private var viewModel = QuestsViewModel()
    @State private var navigateToLog = false
    @State private var showScreenshotPicker = false
    @State private var selectedPhotos: [PhotosPickerItem] = []
    @State private var screenshotDataForLogView: [Data]? = nil
    @State private var isLoadingPhotos = false

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                // Loading overlay for photo conversion
                if isLoadingPhotos {
                    Color.black.opacity(0.5)
                        .ignoresSafeArea()
                        .overlay(
                            VStack(spacing: 16) {
                                ProgressView()
                                    .tint(.systemPrimary)
                                    .scaleEffect(1.5)
                                Text("Preparing screenshots...")
                                    .font(.system(size: 13))
                                    .foregroundColor(.textMuted)
                            }
                        )
                        .zIndex(100)
                }

                ScrollView {
                    VStack(spacing: 0) {
                        // Header (Edge Flow)
                        QuestCenterHeader()
                            .padding(.horizontal, 20)
                            .padding(.top, 20)

                        // Action Buttons (Edge Flow)
                        QuestActionButtons(
                            onBeginQuest: { navigateToLog = true },
                            onScanLog: { showScreenshotPicker = true }
                        )
                        .padding(.horizontal, 20)
                        .padding(.top, 20)
                        .padding(.bottom, 24)

                        // Archive Header (Edge Flow)
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Quest Archive")
                                    .font(.system(size: 18, weight: .semibold))
                                    .foregroundColor(.textPrimary)

                                if let date = viewModel.selectedDate {
                                    Text(date.formattedMedium)
                                        .font(.system(size: 13))
                                        .foregroundColor(.textMuted)
                                }
                            }

                            Spacer()

                            // Clear selection button
                            if viewModel.selectedDate != nil {
                                Button {
                                    withAnimation(.smoothSpring) {
                                        viewModel.clearSelection()
                                    }
                                } label: {
                                    Text("Clear")
                                        .font(.system(size: 13))
                                        .foregroundColor(.systemPrimary)
                                }
                            }

                            // Calendar toggle
                            Button {
                                withAnimation(.smoothSpring) {
                                    viewModel.showCalendar.toggle()
                                }
                            } label: {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 10)
                                        .fill(viewModel.showCalendar ? Color.systemPrimary.opacity(0.15) : Color.voidMedium)
                                        .frame(width: 36, height: 36)

                                    Image(systemName: viewModel.showCalendar ? "list.bullet" : "calendar")
                                        .font(.system(size: 14, weight: .medium))
                                        .foregroundColor(viewModel.showCalendar ? .systemPrimary : .textSecondary)
                                }
                            }
                        }
                        .padding(.horizontal, 20)
                        .padding(.bottom, 14)

                        // Calendar (Edge Flow style)
                        if viewModel.showCalendar {
                            QuestsCalendarView(
                                selectedDate: Binding(
                                    get: { viewModel.selectedDate ?? Date() },
                                    set: { viewModel.selectDate($0) }
                                ),
                                datesWithWorkouts: viewModel.datesWithWorkouts,
                                hasSelection: viewModel.selectedDate != nil
                            )
                            .padding(16)
                            .edgeFlowCard(accent: .systemPrimary)
                            .padding(.horizontal, 20)
                            .padding(.bottom, 16)
                        }

                        // Workout List (Edge Flow)
                        if viewModel.isLoading && viewModel.workouts.isEmpty {
                            VStack(spacing: 16) {
                                ProgressView()
                                    .tint(.systemPrimary)
                                Text("Loading quests...")
                                    .font(.system(size: 13))
                                    .foregroundColor(.textMuted)
                            }
                            .padding(.vertical, 40)
                        } else if viewModel.displayedWorkouts.isEmpty {
                            EmptyQuestsCard(hasDateFilter: viewModel.selectedDate != nil)
                                .padding(.horizontal, 20)
                        } else {
                            VStack(spacing: 10) {
                                ForEach(Array(viewModel.displayedWorkouts.enumerated()), id: \.element.id) { index, workout in
                                    NavigationLink {
                                        QuestsDetailView(
                                            workoutId: workout.id,
                                            viewModel: viewModel
                                        )
                                    } label: {
                                        EdgeFlowWorkoutRow(workout: workout)
                                    }
                                    .buttonStyle(PlainButtonStyle())
                                    .contextMenu {
                                        Button(role: .destructive) {
                                            Task { await viewModel.deleteWorkout(workout) }
                                        } label: {
                                            Label("Delete", systemImage: "trash")
                                        }
                                    }
                                    .fadeIn(delay: Double(index) * 0.03)
                                }

                                // Load more button (Edge Flow pill style)
                                if viewModel.hasMoreWorkouts && !viewModel.showCalendar {
                                    Button {
                                        Task { await viewModel.loadWorkouts() }
                                    } label: {
                                        HStack {
                                            if viewModel.isLoading {
                                                ProgressView()
                                                    .tint(.systemPrimary)
                                            } else {
                                                HStack(spacing: 8) {
                                                    Text("Load More")
                                                        .font(.system(size: 13, weight: .semibold))
                                                    Image(systemName: "chevron.down")
                                                        .font(.system(size: 10, weight: .semibold))
                                                }
                                                .foregroundColor(.systemPrimary)
                                            }
                                        }
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 14)
                                    }
                                }
                            }
                            .padding(.horizontal, 20)
                        }

                        Spacer().frame(height: 100)
                    }
                }
            }
            .navigationBarHidden(true)
            .navigationDestination(isPresented: $navigateToLog) {
                LogView(initialScreenshots: screenshotDataForLogView)
                    .onDisappear {
                        // Clear the screenshot data when coming back
                        screenshotDataForLogView = nil
                    }
            }
            .refreshable {
                await viewModel.loadWorkouts(refresh: true)
            }
            .photosPicker(
                isPresented: $showScreenshotPicker,
                selection: $selectedPhotos,
                maxSelectionCount: 10,
                matching: .images
            )
            .onChange(of: selectedPhotos) { _, newValue in
                if !newValue.isEmpty {
                    // Convert photos to Data and then navigate
                    isLoadingPhotos = true
                    Task {
                        var imageDataArray: [Data] = []
                        for item in newValue {
                            if let data = try? await item.loadTransferable(type: Data.self) {
                                imageDataArray.append(data)
                            }
                        }

                        await MainActor.run {
                            selectedPhotos = [] // Clear selection
                            isLoadingPhotos = false
                            if !imageDataArray.isEmpty {
                                screenshotDataForLogView = imageDataArray
                                navigateToLog = true
                            }
                        }
                    }
                }
            }
        }
        .task {
            await viewModel.loadWorkouts(refresh: true)
        }
    }
}

// MARK: - Quest Center Header (Edge Flow)

struct QuestCenterHeader: View {
    @State private var showContent = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Quest Center")
                .font(.system(size: 28, weight: .bold))
                .foregroundColor(.textPrimary)

            Text("Log workouts and track your progress")
                .font(.system(size: 13))
                .foregroundColor(.textMuted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opacity(showContent ? 1 : 0)
        .offset(y: showContent ? 0 : 10)
        .onAppear {
            withAnimation(.easeOut(duration: 0.5)) {
                showContent = true
            }
        }
    }
}

// MARK: - Quest Action Buttons (Edge Flow)

struct QuestActionButtons: View {
    let onBeginQuest: () -> Void
    let onScanLog: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            // Begin Quest Button - Primary Pill
            Button(action: onBeginQuest) {
                HStack(spacing: 8) {
                    Text("\u{26A1}")  // Lightning bolt
                        .font(.system(size: 14))
                    Text("Begin Quest")
                        .font(.system(size: 14, weight: .semibold))
                }
                .edgeFlowPillButton(isPrimary: true)
            }

            // Scan Log Button - Secondary Pill
            Button(action: onScanLog) {
                HStack(spacing: 8) {
                    Image(systemName: "camera.viewfinder")
                        .font(.system(size: 14, weight: .medium))
                    Text("Scan")
                        .font(.system(size: 14, weight: .semibold))
                }
                .edgeFlowPillButton(isPrimary: false)
            }
        }
    }
}

// MARK: - Full Month Calendar (Edge Flow)

struct QuestsCalendarView: View {
    @Binding var selectedDate: Date
    let datesWithWorkouts: Set<String>
    var hasSelection: Bool = false

    @State private var displayedMonth = Date()

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
                        RoundedRectangle(cornerRadius: 8)
                            .fill(Color.voidLight)
                            .frame(width: 28, height: 28)

                        Image(systemName: "chevron.left")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(.textSecondary)
                    }
                }

                Spacer()

                Text(dateFormatter.string(from: displayedMonth).uppercased())
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.textPrimary)
                    .tracking(1)

                Spacer()

                Button {
                    withAnimation(.smoothSpring) {
                        displayedMonth = calendar.date(byAdding: .month, value: 1, to: displayedMonth) ?? displayedMonth
                    }
                } label: {
                    ZStack {
                        RoundedRectangle(cornerRadius: 8)
                            .fill(Color.voidLight)
                            .frame(width: 28, height: 28)

                        Image(systemName: "chevron.right")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(.textSecondary)
                    }
                }
            }

            // Day Headers
            HStack(spacing: 0) {
                ForEach(["S", "M", "T", "W", "T", "F", "S"], id: \.self) { day in
                    Text(day)
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.textMuted)
                        .frame(maxWidth: .infinity)
                }
            }

            // Calendar Grid - Full Month
            let days = daysInMonth()
            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 7), spacing: 6) {
                ForEach(days, id: \.self) { date in
                    if let date = date {
                        let isSelected = hasSelection && calendar.isDate(date, inSameDayAs: selectedDate)
                        EdgeFlowCalendarDayCell(
                            date: date,
                            isSelected: isSelected,
                            hasWorkout: hasWorkout(on: date),
                            isToday: calendar.isDateInToday(date)
                        ) {
                            withAnimation(.quickSpring) {
                                selectedDate = date
                            }
                        }
                    } else {
                        Text("")
                            .frame(height: 44)
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
        // (stored as local date strings like "2024-01-15", not UTC)
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone.current
        let dateString = formatter.string(from: date)
        let hasIt = datesWithWorkouts.contains(dateString)
        // Debug for end of month dates
        let day = Calendar.current.component(.day, from: date)
        if day >= 29 {
            print("DEBUG hasWorkout check: '\(dateString)' in \(datesWithWorkouts) = \(hasIt)")
        }
        return hasIt
    }
}

// MARK: - Edge Flow Calendar Day Cell

struct EdgeFlowCalendarDayCell: View {
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
                    .font(.system(size: 13, weight: isSelected || isToday ? .semibold : .regular))
                    .foregroundColor(textColor)

                // Quest completion indicator
                if hasWorkout {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.successGreen)
                        .frame(width: 10, height: 3)
                } else {
                    Rectangle()
                        .fill(Color.clear)
                        .frame(width: 10, height: 3)
                }
            }
            .frame(height: 44)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isSelected ? Color.systemPrimary.opacity(0.15) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(
                        isToday ? Color.systemPrimary : Color.clear,
                        lineWidth: isToday ? 2 : 0
                    )
            )
            .shadow(color: isSelected ? Color.systemPrimaryGlow.opacity(0.2) : .clear, radius: 4, x: 0, y: 0)
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

// MARK: - Edge Flow Workout Row

struct EdgeFlowWorkoutRow: View {
    let workout: WorkoutSummaryResponse

    private var isWhoopActivity: Bool {
        workout.isWhoopActivity == true
    }

    private var hasExercises: Bool {
        workout.exerciseCount > 0
    }

    private var indicatorColor: Color {
        (isWhoopActivity && !hasExercises) ? .orange : .successGreen
    }

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
        HStack(spacing: 14) {
            // Quest info
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 10) {
                    Text(formatDate(workout.date))
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.textPrimary)

                    // Badge
                    HStack(spacing: 4) {
                        Image(systemName: badgeIcon)
                            .font(.system(size: 8, weight: .bold))
                        Text(badgeText)
                            .font(.system(size: 9, weight: .semibold))
                            .tracking(0.5)
                    }
                    .foregroundColor(indicatorColor)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(indicatorColor.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: 6))

                    // WHOOP indicator for activities with exercises
                    if isWhoopActivity && hasExercises {
                        HStack(spacing: 2) {
                            Image(systemName: "applewatch")
                                .font(.system(size: 7, weight: .semibold))
                            Text("WHOOP")
                                .font(.system(size: 8, weight: .semibold))
                                .tracking(0.5)
                        }
                        .foregroundColor(.orange)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 4)
                        .background(Color.orange.opacity(0.1))
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                }

                // Stats row
                if isWhoopActivity && !hasExercises {
                    HStack(spacing: 16) {
                        if let activityType = workout.activityType {
                            HStack(spacing: 4) {
                                Text(activityType)
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.orange)
                            }
                        }

                        if let strain = workout.strain {
                            Text(String(format: "%.1f strain", strain))
                                .font(.system(size: 12))
                                .foregroundColor(.textSecondary)
                        }

                        if let calories = workout.calories {
                            Text("\(calories) cal")
                                .font(.system(size: 12))
                                .foregroundColor(.textSecondary)
                        }
                    }
                } else {
                    HStack(spacing: 16) {
                        HStack(spacing: 4) {
                            Image(systemName: "scroll.fill")
                                .font(.system(size: 10))
                                .foregroundColor(.textMuted)
                            Text("\(workout.exerciseCount) objectives")
                                .font(.system(size: 12))
                                .foregroundColor(.textSecondary)
                        }

                        HStack(spacing: 4) {
                            Image(systemName: "square.stack.fill")
                                .font(.system(size: 10))
                                .foregroundColor(.textMuted)
                            Text("\(workout.totalSets) sets")
                                .font(.system(size: 12))
                                .foregroundColor(.textSecondary)
                        }

                        if isWhoopActivity, let strain = workout.strain {
                            HStack(spacing: 4) {
                                Image(systemName: "bolt.fill")
                                    .font(.system(size: 10))
                                    .foregroundColor(.orange)
                                Text(String(format: "%.1f", strain))
                                    .font(.system(size: 12))
                                    .foregroundColor(.orange)
                            }
                        }
                    }
                }
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.textMuted)
        }
        .padding(16)
        .edgeFlowCard(accent: indicatorColor)
    }

    private func formatDate(_ dateString: String) -> String {
        dateString.parseISO8601Date()?.formattedMedium ?? dateString
    }
}

// MARK: - Empty State (Edge Flow)

struct EmptyQuestsCard: View {
    var hasDateFilter: Bool = false

    var body: some View {
        VStack(spacing: 20) {
            ZStack {
                RoundedRectangle(cornerRadius: 14)
                    .fill(Color.voidLight)
                    .frame(width: 64, height: 64)

                Image(systemName: hasDateFilter ? "calendar.badge.exclamationmark" : "scroll")
                    .font(.system(size: 28))
                    .foregroundColor(.textMuted)
            }

            VStack(spacing: 8) {
                Text(hasDateFilter ? "No Quests on This Day" : "No Quests Yet")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.textPrimary)

                Text(hasDateFilter ? "Select another date or clear the filter" : "Begin a quest to start tracking\nyour training progress")
                    .font(.system(size: 13))
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 32)
        .edgeFlowCard(accent: .systemPrimary)
    }
}

// MARK: - Quest Detail View (wraps existing)

struct QuestsDetailView: View {
    let workoutId: String
    @ObservedObject var viewModel: QuestsViewModel

    var body: some View {
        ZStack {
            VoidBackground(showGrid: false, glowIntensity: 0.03)

            if viewModel.isLoadingDetail {
                ProgressView()
                    .tint(.systemPrimary)
            } else if let workout = viewModel.selectedWorkout {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        QuestSummaryCard(workout: workout)
                            .padding(.horizontal)
                            .fadeIn(delay: 0)

                        AriseSectionHeader(title: "Completed Objectives")
                            .padding(.horizontal)
                            .fadeIn(delay: 0.1)

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

// MARK: - Preview

#Preview {
    QuestsView()
}
