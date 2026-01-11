import SwiftUI
import PhotosUI

struct QuestsView: View {
    @StateObject private var viewModel = QuestsViewModel()
    @State private var navigateToLog = false
    @State private var showScreenshotPicker = false
    @State private var selectedPhotos: [PhotosPickerItem] = []

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                ScrollView {
                    VStack(spacing: 0) {
                        // Header
                        QuestCenterHeader()
                            .padding(.horizontal)
                            .padding(.top)

                        // Action Buttons
                        QuestActionButtons(
                            onBeginQuest: { navigateToLog = true },
                            onScanLog: { showScreenshotPicker = true }
                        )
                        .padding()

                        // Archive Header
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("[ QUEST ARCHIVE ]")
                                    .font(.ariseMono(size: 10, weight: .medium))
                                    .foregroundColor(.textMuted)
                                    .tracking(1)

                                if let date = viewModel.selectedDate {
                                    Text(date.formattedMedium)
                                        .font(.ariseHeader(size: 14, weight: .semibold))
                                        .foregroundColor(.textPrimary)
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
                                    Text("CLEAR")
                                        .font(.ariseMono(size: 10, weight: .semibold))
                                        .foregroundColor(.systemPrimary)
                                        .tracking(1)
                                }
                            }

                            // Calendar toggle
                            Button {
                                withAnimation(.smoothSpring) {
                                    viewModel.showCalendar.toggle()
                                }
                            } label: {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 4)
                                        .fill(viewModel.showCalendar ? Color.systemPrimary.opacity(0.1) : Color.voidLight)
                                        .frame(width: 40, height: 40)
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 4)
                                                .stroke(viewModel.showCalendar ? Color.systemPrimary.opacity(0.3) : Color.ariseBorder, lineWidth: 1)
                                        )

                                    Image(systemName: viewModel.showCalendar ? "list.bullet" : "calendar")
                                        .font(.system(size: 14, weight: .semibold))
                                        .foregroundColor(viewModel.showCalendar ? .systemPrimary : .textSecondary)
                                }
                            }
                        }
                        .padding(.horizontal)
                        .padding(.bottom, 12)

                        // Calendar (full month)
                        if viewModel.showCalendar {
                            QuestsCalendarView(
                                selectedDate: Binding(
                                    get: { viewModel.selectedDate ?? Date() },
                                    set: { viewModel.selectDate($0) }
                                ),
                                datesWithWorkouts: viewModel.datesWithWorkouts,
                                hasSelection: viewModel.selectedDate != nil
                            )
                            .padding()
                            .background(Color.voidMedium)
                            .cornerRadius(4)
                            .overlay(
                                RoundedRectangle(cornerRadius: 4)
                                    .stroke(Color.ariseBorder, lineWidth: 1)
                            )
                            .overlay(
                                Rectangle()
                                    .fill(Color.systemPrimary.opacity(0.2))
                                    .frame(height: 1),
                                alignment: .top
                            )
                            .padding(.horizontal)
                            .padding(.bottom, 16)
                        }

                        // Workout List
                        if viewModel.isLoading && viewModel.workouts.isEmpty {
                            VStack(spacing: 16) {
                                ProgressView()
                                    .tint(.systemPrimary)
                                Text("LOADING QUESTS...")
                                    .font(.ariseMono(size: 11, weight: .medium))
                                    .foregroundColor(.textMuted)
                                    .tracking(1)
                            }
                            .padding(.vertical, 40)
                        } else if viewModel.displayedWorkouts.isEmpty {
                            EmptyQuestsCard(hasDateFilter: viewModel.selectedDate != nil)
                                .padding(.horizontal)
                        } else {
                            VStack(spacing: 8) {
                                ForEach(Array(viewModel.displayedWorkouts.enumerated()), id: \.element.id) { index, workout in
                                    NavigationLink {
                                        QuestsDetailView(
                                            workoutId: workout.id,
                                            viewModel: viewModel
                                        )
                                    } label: {
                                        CompletedQuestRow(workout: workout)
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

                                // Load more button
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
                                                    Text("LOAD MORE")
                                                        .font(.ariseMono(size: 12, weight: .semibold))
                                                        .tracking(1)
                                                    Image(systemName: "chevron.down")
                                                        .font(.system(size: 10, weight: .bold))
                                                }
                                                .foregroundColor(.systemPrimary)
                                            }
                                        }
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 16)
                                    }
                                }
                            }
                            .padding(.horizontal)
                        }

                        Spacer().frame(height: 100)
                    }
                }
            }
            .navigationBarHidden(true)
            .navigationDestination(isPresented: $navigateToLog) {
                LogView()
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
                    // Navigate to screenshot processing
                    // This will be handled by LogView's screenshot flow
                    navigateToLog = true
                }
            }
        }
        .task {
            await viewModel.loadWorkouts(refresh: true)
        }
    }
}

// MARK: - Quest Center Header

struct QuestCenterHeader: View {
    @State private var showContent = false

    var body: some View {
        VStack(spacing: 12) {
            Text("[ QUEST CENTER ]")
                .font(.ariseMono(size: 11, weight: .medium))
                .foregroundColor(.systemPrimary)
                .tracking(2)

            HStack(spacing: 12) {
                Image(systemName: "scroll.fill")
                    .font(.system(size: 24))
                    .foregroundColor(.systemPrimary)
                    .shadow(color: .systemPrimaryGlow, radius: 10, x: 0, y: 0)

                VStack(alignment: .leading, spacing: 2) {
                    Text("Training Quests")
                        .font(.ariseHeader(size: 22, weight: .bold))
                        .foregroundColor(.textPrimary)

                    Text("Log workouts and track your progress")
                        .font(.ariseMono(size: 11))
                        .foregroundColor(.textMuted)
                }

                Spacer()
            }
        }
        .padding(16)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .overlay(
            Rectangle()
                .fill(Color.systemPrimary.opacity(0.2))
                .frame(height: 1),
            alignment: .top
        )
        .opacity(showContent ? 1 : 0)
        .offset(y: showContent ? 0 : 10)
        .onAppear {
            withAnimation(.easeOut(duration: 0.5)) {
                showContent = true
            }
        }
    }
}

// MARK: - Quest Action Buttons

struct QuestActionButtons: View {
    let onBeginQuest: () -> Void
    let onScanLog: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            // Begin Quest Button
            Button(action: onBeginQuest) {
                VStack(spacing: 10) {
                    Image(systemName: "plus.circle.fill")
                        .font(.system(size: 28))

                    Text("BEGIN QUEST")
                        .font(.ariseMono(size: 11, weight: .semibold))
                        .tracking(1)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 90)
                .background(Color.systemPrimary)
                .foregroundColor(.voidBlack)
                .cornerRadius(4)
            }

            // Scan Log Button
            Button(action: onScanLog) {
                VStack(spacing: 10) {
                    Image(systemName: "camera.fill")
                        .font(.system(size: 28))

                    Text("SCAN LOG")
                        .font(.ariseMono(size: 11, weight: .semibold))
                        .tracking(1)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 90)
                .background(Color.voidMedium)
                .foregroundColor(.systemPrimary)
                .cornerRadius(4)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.systemPrimary.opacity(0.3), lineWidth: 1)
                )
            }
        }
    }
}

// MARK: - Full Month Calendar

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

            // Calendar Grid - Full Month
            let days = daysInMonth()
            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 7), spacing: 6) {
                ForEach(days, id: \.self) { date in
                    if let date = date {
                        let isSelected = hasSelection && calendar.isDate(date, inSameDayAs: selectedDate)
                        AriseCalendarDayCell(
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
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withFullDate]
        return datesWithWorkouts.contains(formatter.string(from: date))
    }
}

// MARK: - Empty State

struct EmptyQuestsCard: View {
    var hasDateFilter: Bool = false

    var body: some View {
        VStack(spacing: 20) {
            ZStack {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.voidLight)
                    .frame(width: 64, height: 64)

                Image(systemName: hasDateFilter ? "calendar.badge.exclamationmark" : "scroll")
                    .font(.system(size: 28))
                    .foregroundColor(.textMuted)
            }

            VStack(spacing: 8) {
                Text(hasDateFilter ? "No Quests on This Day" : "No Quests Yet")
                    .font(.ariseHeader(size: 16, weight: .semibold))
                    .foregroundColor(.textPrimary)

                Text(hasDateFilter ? "Select another date or clear the filter" : "Begin a quest to start tracking\nyour training progress")
                    .font(.ariseMono(size: 12))
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 32)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
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
