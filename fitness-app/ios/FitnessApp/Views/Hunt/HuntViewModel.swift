import Foundation
import SwiftUI

@MainActor
class HuntViewModel: ObservableObject {
    // MARK: - History State
    @Published var workouts: [WorkoutSummaryResponse] = []
    @Published var selectedWorkout: WorkoutResponse?
    @Published var selectedDate: Date?
    @Published var isLoading = false
    @Published var isLoadingDetail = false
    @Published var error: String?
    @Published var hasMoreWorkouts = true
    @Published var showCalendar = true

    // MARK: - Navigation State
    @Published var isLoggingWorkout = false
    @Published var showScreenshotPicker = false

    private var offset = 0
    private let limit = 50 // Load more for calendar view

    // MARK: - Computed Properties

    var workoutsByDate: [String: [WorkoutSummaryResponse]] {
        Dictionary(grouping: workouts) { workout in
            workout.date.localDayKey
        }
    }

    var datesWithWorkouts: Set<String> {
        let dates = Set(workouts.map { $0.date.localDayKey })
        #if DEBUG
        // Debug: print what dates we're extracting
        print("DEBUG datesWithWorkouts: \(dates.sorted())")
        if let firstWorkout = workouts.first {
            print("DEBUG first workout raw date: '\(firstWorkout.date)'")
            print("DEBUG first workout localDayKey: '\(firstWorkout.date.localDayKey)'")
        }
        #endif
        return dates
    }

    var displayedWorkouts: [WorkoutSummaryResponse] {
        if let date = selectedDate {
            return workoutsForDate(date)
        }
        return workouts
    }

    // MARK: - Cleared-gate sigils (ARISE v2 §6.6)

    /// Cleared gates keyed by local clear day (yyyy-MM-dd) → rank.
    /// GateResponse only carries cleared_by_set_id (not a workout id), so the
    /// Hunt Log matches by day: the workout row on the day a gate cleared
    /// gets the rank sigil.
    @Published var clearedGateRanksByDay: [String: String] = [:]

    /// Rank sigil for a workout row, or nil.
    func gateRank(for workout: WorkoutSummaryResponse) -> String? {
        clearedGateRanksByDay[workout.date.localDayKey]
    }

    private func loadClearedGates() async {
        guard let history = try? await APIClient.shared.getGateHistory(limit: 50) else { return }
        var byDay: [String: String] = [:]
        for gate in history where gate.status == "cleared" {
            if let clearedAt = gate.clearedAt?.parseISO8601Date() {
                byDay[DateFormatter.localDate.string(from: clearedAt)] = gate.rank
            }
        }
        clearedGateRanksByDay = byDay
    }

    // MARK: - Actions

    func loadWorkouts(refresh: Bool = false) async {
        if refresh {
            offset = 0
            hasMoreWorkouts = true
            await loadClearedGates()
        }

        guard hasMoreWorkouts else { return }

        isLoading = true
        error = nil

        do {
            let newWorkouts = try await APIClient.shared.getWorkouts(limit: limit, offset: offset)

            if refresh {
                workouts = newWorkouts
            } else {
                workouts.append(contentsOf: newWorkouts)
            }

            hasMoreWorkouts = newWorkouts.count == limit
            offset += newWorkouts.count
        } catch let apiError as APIError {
            if case .unauthorized = apiError { return }
            self.error = apiError.localizedDescription
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func loadWorkoutDetail(id: String) async {
        isLoadingDetail = true

        do {
            selectedWorkout = try await APIClient.shared.getWorkout(id: id)
        } catch let apiError as APIError {
            if case .unauthorized = apiError { return }
            self.error = apiError.localizedDescription
        } catch {
            self.error = error.localizedDescription
        }

        isLoadingDetail = false
    }

    func deleteWorkout(_ workout: WorkoutSummaryResponse) async {
        do {
            try await APIClient.shared.deleteWorkout(id: workout.id)
            workouts.removeAll { $0.id == workout.id }
        } catch let apiError as APIError {
            if case .unauthorized = apiError { return }
            self.error = apiError.localizedDescription
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Rename a hunt ("" clears back to the suggested name), then refresh the
    /// detail and the Hunt Log list so the row title updates immediately.
    func renameWorkout(id: String, to name: String) async {
        do {
            selectedWorkout = try await APIClient.shared.renameWorkout(id: id, name: name)
            await loadWorkouts(refresh: true)
        } catch let apiError as APIError {
            if case .unauthorized = apiError { return }
            self.error = apiError.localizedDescription
        } catch {
            self.error = error.localizedDescription
        }
    }

    func workoutsForDate(_ date: Date) -> [WorkoutSummaryResponse] {
        let dateString = DateFormatter.localDate.string(from: date)
        return workouts.filter { $0.date.localDayKey == dateString }
    }

    func selectDate(_ date: Date) {
        if selectedDate == date {
            selectedDate = nil // Deselect if tapping same date
        } else {
            selectedDate = date
        }
    }

    func clearSelection() {
        selectedDate = nil
    }
}
