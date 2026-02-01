import Foundation
import SwiftUI

@MainActor
class HistoryViewModel: ObservableObject {
    @Published var workouts: [WorkoutSummaryResponse] = []
    @Published var selectedWorkout: WorkoutResponse?
    @Published var selectedDate = Date()
    @Published var displayedMonth = Date()  // Persists across view recreations
    @Published var isLoading = false
    @Published var isLoadingDetail = false
    @Published var error: String?
    @Published var hasMoreWorkouts = true

    private var offset = 0
    private let limit = 20

    var workoutsByDate: [String: [WorkoutSummaryResponse]] {
        Dictionary(grouping: workouts) { workout in
            String(workout.date.prefix(10))
        }
    }

    var datesWithWorkouts: Set<String> {
        Set(workouts.map { String($0.date.prefix(10)) })
    }

    func loadWorkouts(refresh: Bool = false) async {
        if refresh {
            offset = 0
            hasMoreWorkouts = true
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
            // Don't set error for unauthorized - user will be redirected to login
            if case .unauthorized = apiError {
                return
            }
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

    func workoutsForDate(_ date: Date) -> [WorkoutSummaryResponse] {
        // Use local timezone DateFormatter to match how workout dates are stored
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone.current
        let dateString = formatter.string(from: date)
        return workouts.filter { String($0.date.prefix(10)) == dateString }
    }
}
