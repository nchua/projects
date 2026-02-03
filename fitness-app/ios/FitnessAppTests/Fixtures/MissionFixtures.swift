import Foundation
@testable import FitnessApp

/// Test fixtures for Mission-related data structures.
/// Provides pre-configured JSON data for testing mission functionality.
struct MissionFixtures {

    // MARK: - Current Mission Response JSON

    /// Response with Big Three goals and PPL mission
    static let multiGoalMissionResponseJSON = """
    {
        "has_active_goal": true,
        "has_active_goals": true,
        "goal": {
            "id": "goal-bench-001",
            "exercise_name": "Barbell Bench Press",
            "target_weight": 225.0,
            "target_reps": 1,
            "target_e1rm": 225.0,
            "weight_unit": "lb",
            "deadline": "\(futureDate(weeks: 12))",
            "progress_percent": 82.0,
            "status": "active"
        },
        "goals": [
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
            },
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
            },
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
        ],
        "mission": {
            "id": "mission-ppl-001",
            "goal_exercise_name": "Barbell Bench Press",
            "goal_target_weight": 225.0,
            "goal_weight_unit": "lb",
            "training_split": "ppl",
            "goals": [],
            "goal_count": 3,
            "status": "offered",
            "week_start": "\(currentWeekStart())",
            "week_end": "\(currentWeekEnd())",
            "xp_reward": 200,
            "workouts_completed": 0,
            "workouts_total": 3,
            "days_remaining": \(daysUntilSunday()),
            "workouts": [
                {
                    "id": "workout-push-001",
                    "day_number": 1,
                    "focus": "Push - Barbell Bench Press",
                    "status": "pending",
                    "exercise_count": 3
                },
                {
                    "id": "workout-pull-001",
                    "day_number": 2,
                    "focus": "Pull - Barbell Deadlift",
                    "status": "pending",
                    "exercise_count": 3
                },
                {
                    "id": "workout-legs-001",
                    "day_number": 3,
                    "focus": "Legs - Barbell Back Squat",
                    "status": "pending",
                    "exercise_count": 3
                }
            ]
        },
        "needs_goal_setup": false,
        "can_add_more_goals": true
    }
    """

    /// Response indicating user needs to set up goals first
    static let needsGoalSetupResponseJSON = """
    {
        "has_active_goal": false,
        "has_active_goals": false,
        "goal": null,
        "goals": [],
        "mission": null,
        "needs_goal_setup": true,
        "can_add_more_goals": true
    }
    """

    /// Response with goals but no mission yet (mid-week)
    static let goalsWithoutMissionResponseJSON = """
    {
        "has_active_goal": true,
        "has_active_goals": true,
        "goal": {
            "id": "goal-bench-001",
            "exercise_name": "Barbell Bench Press",
            "target_weight": 225.0,
            "target_reps": 1,
            "target_e1rm": 225.0,
            "weight_unit": "lb",
            "deadline": "\(futureDate(weeks: 12))",
            "progress_percent": 82.0,
            "status": "active"
        },
        "goals": [
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
        ],
        "mission": null,
        "needs_goal_setup": false,
        "can_add_more_goals": true
    }
    """

    /// Response with max goals (5) - cannot add more
    static let maxGoalsMissionResponseJSON = """
    {
        "has_active_goal": true,
        "has_active_goals": true,
        "goal": {
            "id": "goal-bench-001",
            "exercise_name": "Barbell Bench Press",
            "target_weight": 225.0,
            "target_reps": 1,
            "target_e1rm": 225.0,
            "weight_unit": "lb",
            "deadline": "\(futureDate(weeks: 12))",
            "progress_percent": 82.0,
            "status": "active"
        },
        "goals": [
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
            },
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
            },
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
            },
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
        "mission": null,
        "needs_goal_setup": false,
        "can_add_more_goals": false
    }
    """

    // MARK: - Mission Accept Response JSON

    static let missionAcceptSuccessResponseJSON = """
    {
        "success": true,
        "mission": {
            "id": "mission-ppl-001",
            "goal_id": "goal-bench-001",
            "goal_exercise_name": "Barbell Bench Press",
            "goal_target_weight": 225.0,
            "goal_weight_unit": "lb",
            "training_split": "ppl",
            "goals": [],
            "goal_count": 3,
            "week_start": "\(currentWeekStart())",
            "week_end": "\(currentWeekEnd())",
            "status": "accepted",
            "xp_reward": 200,
            "weekly_target": "Build strength in Bench, Squat, Deadlift",
            "coaching_message": "This week's Push/Pull/Legs split targets all 3 of your goals.",
            "workouts": [],
            "workouts_completed": 0,
            "workouts_total": 3,
            "days_remaining": \(daysUntilSunday())
        },
        "message": "Mission accepted! Complete your workouts this week."
    }
    """

    // MARK: - Decoding Helpers

    /// Decode multi-goal mission response
    static func decodeMultiGoalMissionResponse() throws -> CurrentMissionResponse {
        let data = multiGoalMissionResponseJSON.data(using: .utf8)!
        return try JSONDecoder().decode(CurrentMissionResponse.self, from: data)
    }

    /// Decode needs goal setup response
    static func decodeNeedsGoalSetupResponse() throws -> CurrentMissionResponse {
        let data = needsGoalSetupResponseJSON.data(using: .utf8)!
        return try JSONDecoder().decode(CurrentMissionResponse.self, from: data)
    }

    /// Decode goals without mission response
    static func decodeGoalsWithoutMissionResponse() throws -> CurrentMissionResponse {
        let data = goalsWithoutMissionResponseJSON.data(using: .utf8)!
        return try JSONDecoder().decode(CurrentMissionResponse.self, from: data)
    }

    /// Decode max goals mission response
    static func decodeMaxGoalsMissionResponse() throws -> CurrentMissionResponse {
        let data = maxGoalsMissionResponseJSON.data(using: .utf8)!
        return try JSONDecoder().decode(CurrentMissionResponse.self, from: data)
    }

    /// Decode mission accept response
    static func decodeMissionAcceptResponse() throws -> MissionAcceptResponse {
        let data = missionAcceptSuccessResponseJSON.data(using: .utf8)!
        return try JSONDecoder().decode(MissionAcceptResponse.self, from: data)
    }

    // MARK: - Date Helpers

    private static func currentWeekStart() -> String {
        let calendar = Calendar.current
        let today = Date()
        let weekday = calendar.component(.weekday, from: today)
        let daysToMonday = (weekday == 1) ? -6 : (2 - weekday)
        let monday = calendar.date(byAdding: .day, value: daysToMonday, to: today)!
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: monday)
    }

    private static func currentWeekEnd() -> String {
        let calendar = Calendar.current
        let today = Date()
        let weekday = calendar.component(.weekday, from: today)
        let daysToSunday = (weekday == 1) ? 0 : (8 - weekday)
        let sunday = calendar.date(byAdding: .day, value: daysToSunday, to: today)!
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: sunday)
    }

    private static func daysUntilSunday() -> Int {
        let calendar = Calendar.current
        let today = Date()
        let weekday = calendar.component(.weekday, from: today)
        return (weekday == 1) ? 0 : (8 - weekday)
    }

    private static func futureDate(weeks: Int) -> String {
        let date = Calendar.current.date(byAdding: .weekOfYear, value: weeks, to: Date())!
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }
}
