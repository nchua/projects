import Foundation

/// Lightweight goals store for the Power tab (ARISE v2 §8.4).
/// Goals moved here from the old Home mission card; backed by the /goals API.
@MainActor
class GoalsViewModel: ObservableObject {
    @Published var goals: [GoalSummaryResponse] = []
    @Published var canAddMore = true
    @Published var maxGoals = 5
    @Published var error: String?

    func loadGoals() async {
        do {
            let response = try await APIClient.shared.getGoals()
            goals = response.goals
            canAddMore = response.canAddMore
            maxGoals = response.maxGoals
        } catch {
            self.error = error.localizedDescription
        }
    }

    func deleteGoal(id: String) async {
        do {
            try await APIClient.shared.deleteGoal(id: id)
            await loadGoals()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func deleteAllGoals() async {
        for goal in goals {
            do {
                try await APIClient.shared.deleteGoal(id: goal.id)
            } catch {
                self.error = error.localizedDescription
            }
        }
        await loadGoals()
    }

    /// Build an editable GoalResponse from a summary row.
    /// The editor only reads target/deadline fields, so progress details can be zeroed.
    func editableGoal(from summary: GoalSummaryResponse) -> GoalResponse {
        GoalResponse(
            id: summary.id,
            exerciseId: "",
            exerciseName: summary.exerciseName,
            targetWeight: summary.targetWeight,
            targetReps: summary.targetReps,
            targetE1rm: summary.targetE1rm,
            weightUnit: summary.weightUnit,
            deadline: summary.deadline,
            startingE1rm: nil,
            currentE1rm: nil,
            status: summary.status,
            notes: nil,
            createdAt: "",
            progressPercent: summary.progressPercent,
            weightToGo: 0,
            weeksRemaining: 0
        )
    }
}
