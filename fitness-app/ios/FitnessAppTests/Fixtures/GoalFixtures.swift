import Foundation
@testable import FitnessApp

/// Test fixtures for Goal-related data structures.
/// Provides pre-configured JSON data for testing goal functionality.
struct GoalFixtures {

    // MARK: - JSON Data for Decoding

    /// Bench press goal JSON (225 lb, 82% progress)
    static let benchGoalJSON = """
    {
        "id": "goal-bench-001",
        "exercise_name": "Barbell Bench Press",
        "target_weight": 225.0,
        "target_reps": 1,
        "target_e1rm": 225.0,
        "weight_unit": "lb",
        "deadline": "\(futureDate(weeks: 12))",
        "progress_percent": 82.0,
        "status": "active"
    }
    """

    /// Squat goal JSON (315 lb, 88% progress)
    static let squatGoalJSON = """
    {
        "id": "goal-squat-001",
        "exercise_name": "Barbell Back Squat",
        "target_weight": 315.0,
        "target_reps": 1,
        "target_e1rm": 315.0,
        "weight_unit": "lb",
        "deadline": "\(futureDate(weeks: 12))",
        "progress_percent": 88.0,
        "status": "active"
    }
    """

    /// Deadlift goal JSON (405 lb, 93% progress)
    static let deadliftGoalJSON = """
    {
        "id": "goal-dead-001",
        "exercise_name": "Barbell Deadlift",
        "target_weight": 405.0,
        "target_reps": 1,
        "target_e1rm": 405.0,
        "weight_unit": "lb",
        "deadline": "\(futureDate(weeks: 12))",
        "progress_percent": 93.0,
        "status": "active"
    }
    """

    // MARK: - Goal Collections JSON

    /// Big Three goals (bench, squat, deadlift)
    static let bigThreeGoalsJSON = """
    [
        \(benchGoalJSON),
        \(squatGoalJSON),
        \(deadliftGoalJSON)
    ]
    """

    // MARK: - API Response JSON

    /// Goals list response with Big Three goals
    static let bigThreeListResponseJSON = """
    {
        "goals": \(bigThreeGoalsJSON),
        "active_count": 3,
        "completed_count": 0,
        "can_add_more": true,
        "max_goals": 5
    }
    """

    /// Goals list with max (5) active goals
    static let maxGoalsListResponseJSON = """
    {
        "goals": [
            \(benchGoalJSON),
            \(squatGoalJSON),
            \(deadliftGoalJSON),
            {
                "id": "goal-ohp-001",
                "exercise_name": "Overhead Press",
                "target_weight": 155.0,
                "target_reps": 1,
                "target_e1rm": 155.0,
                "weight_unit": "lb",
                "deadline": "\(futureDate(weeks: 12))",
                "progress_percent": 75.0,
                "status": "active"
            },
            {
                "id": "goal-row-001",
                "exercise_name": "Barbell Row",
                "target_weight": 185.0,
                "target_reps": 1,
                "target_e1rm": 185.0,
                "weight_unit": "lb",
                "deadline": "\(futureDate(weeks: 12))",
                "progress_percent": 80.0,
                "status": "active"
            }
        ],
        "active_count": 5,
        "completed_count": 0,
        "can_add_more": false,
        "max_goals": 5
    }
    """

    /// Empty goals list (no goals set up yet)
    static let emptyGoalsListResponseJSON = """
    {
        "goals": [],
        "active_count": 0,
        "completed_count": 0,
        "can_add_more": true,
        "max_goals": 5
    }
    """

    /// Batch creation response (3 goals)
    static let batchCreateResponseJSON = """
    {
        "goals": [
            {
                "id": "goal-bench-001",
                "exercise_id": "ex-bench-001",
                "exercise_name": "Barbell Bench Press",
                "target_weight": 225.0,
                "target_reps": 1,
                "target_e1rm": 225.0,
                "weight_unit": "lb",
                "deadline": "\(futureDate(weeks: 12))",
                "starting_e1rm": 180.0,
                "current_e1rm": 184.5,
                "status": "active",
                "notes": null,
                "created_at": "\(ISO8601DateFormatter().string(from: Date()))",
                "progress_percent": 82.0,
                "weight_to_go": 40.5,
                "weeks_remaining": 12
            },
            {
                "id": "goal-squat-001",
                "exercise_id": "ex-squat-001",
                "exercise_name": "Barbell Back Squat",
                "target_weight": 315.0,
                "target_reps": 1,
                "target_e1rm": 315.0,
                "weight_unit": "lb",
                "deadline": "\(futureDate(weeks: 12))",
                "starting_e1rm": 252.0,
                "current_e1rm": 277.2,
                "status": "active",
                "notes": null,
                "created_at": "\(ISO8601DateFormatter().string(from: Date()))",
                "progress_percent": 88.0,
                "weight_to_go": 37.8,
                "weeks_remaining": 12
            },
            {
                "id": "goal-dead-001",
                "exercise_id": "ex-dead-001",
                "exercise_name": "Barbell Deadlift",
                "target_weight": 405.0,
                "target_reps": 1,
                "target_e1rm": 405.0,
                "weight_unit": "lb",
                "deadline": "\(futureDate(weeks: 12))",
                "starting_e1rm": 324.0,
                "current_e1rm": 376.65,
                "status": "active",
                "notes": null,
                "created_at": "\(ISO8601DateFormatter().string(from: Date()))",
                "progress_percent": 93.0,
                "weight_to_go": 28.35,
                "weeks_remaining": 12
            }
        ],
        "created_count": 3,
        "active_count": 3
    }
    """

    // MARK: - Decoding Helpers

    /// Decode BigThree goals list response
    static func decodeBigThreeListResponse() throws -> GoalsListResponse {
        let data = bigThreeListResponseJSON.data(using: .utf8)!
        return try JSONDecoder().decode(GoalsListResponse.self, from: data)
    }

    /// Decode max goals list response
    static func decodeMaxGoalsListResponse() throws -> GoalsListResponse {
        let data = maxGoalsListResponseJSON.data(using: .utf8)!
        return try JSONDecoder().decode(GoalsListResponse.self, from: data)
    }

    /// Decode empty goals list response
    static func decodeEmptyGoalsListResponse() throws -> GoalsListResponse {
        let data = emptyGoalsListResponseJSON.data(using: .utf8)!
        return try JSONDecoder().decode(GoalsListResponse.self, from: data)
    }

    /// Decode batch create response
    static func decodeBatchCreateResponse() throws -> GoalBatchCreateResponse {
        let data = batchCreateResponseJSON.data(using: .utf8)!
        return try JSONDecoder().decode(GoalBatchCreateResponse.self, from: data)
    }

    // MARK: - Date Helpers

    private static func futureDate(weeks: Int) -> String {
        let date = Calendar.current.date(byAdding: .weekOfYear, value: weeks, to: Date())!
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    private static func pastDate(weeks: Int) -> String {
        let date = Calendar.current.date(byAdding: .weekOfYear, value: -weeks, to: Date())!
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }
}
