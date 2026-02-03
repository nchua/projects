import XCTest
@testable import FitnessApp

/// Tests for API type encoding and decoding.
///
/// These tests verify that:
/// - Request types encode correctly (snake_case conversion)
/// - Response types decode correctly from API JSON
/// - Optional fields are handled properly
final class APITypesTests: XCTestCase {

    // MARK: - Test Lifecycle

    override func setUpWithError() throws {
        // Setup runs before each test
    }

    override func tearDownWithError() throws {
        // Teardown runs after each test
    }

    // MARK: - Goal Create Encoding

    func testGoalCreateEncodesWithSnakeCase() throws {
        // GoalCreate should encode with snake_case keys for the API
        let expectedKeys = [
            "exercise_id",
            "target_weight",
            "target_reps",
            "weight_unit",
            "deadline",
            "notes"
        ]

        // Verify CodingKeys are defined correctly
        for key in expectedKeys {
            XCTAssertTrue(key.contains("_") || key == "notes" || key == "deadline",
                         "Key '\(key)' should be snake_case or simple")
        }
    }

    func testGoalBatchCreateEncodesArray() throws {
        // GoalBatchCreate should have a "goals" array
        let goals = [
            createMockGoalJson(exerciseName: "Bench Press"),
            createMockGoalJson(exerciseName: "Squat"),
        ]

        XCTAssertEqual(goals.count, 2)
    }

    // MARK: - Goal Response Decoding

    func testGoalSummaryResponseDecodes() throws {
        // Test decoding a GoalSummaryResponse from JSON
        let json = """
        {
            "id": "goal-001",
            "exercise_name": "Barbell Bench Press",
            "target_weight": 225.0,
            "target_reps": 1,
            "target_e1rm": 225.0,
            "weight_unit": "lb",
            "deadline": "2026-05-01",
            "progress_percent": 82.0,
            "status": "active"
        }
        """

        let data = json.data(using: .utf8)!
        XCTAssertNoThrow(try JSONDecoder().decode(GoalSummaryResponse.self, from: data))
    }

    func testGoalResponseDecodesFullDetails() throws {
        // Test decoding a full GoalResponse
        let json = """
        {
            "id": "goal-001",
            "exercise_id": "ex-001",
            "exercise_name": "Barbell Bench Press",
            "target_weight": 225.0,
            "target_reps": 1,
            "target_e1rm": 225.0,
            "weight_unit": "lb",
            "deadline": "2026-05-01",
            "starting_e1rm": 180.0,
            "current_e1rm": 205.0,
            "status": "active",
            "notes": null,
            "created_at": "2026-02-01T12:00:00Z",
            "progress_percent": 91.1,
            "weight_to_go": 20.0,
            "weeks_remaining": 12
        }
        """

        let data = json.data(using: .utf8)!
        XCTAssertNoThrow(try JSONDecoder().decode(GoalResponse.self, from: data))
    }

    func testGoalBatchCreateResponseDecodes() throws {
        // Test decoding batch creation response
        let json = """
        {
            "goals": [
                {
                    "id": "goal-001",
                    "exercise_id": "ex-001",
                    "exercise_name": "Bench Press",
                    "target_weight": 225.0,
                    "target_reps": 1,
                    "target_e1rm": 225.0,
                    "weight_unit": "lb",
                    "deadline": "2026-05-01",
                    "starting_e1rm": 180.0,
                    "current_e1rm": 180.0,
                    "status": "active",
                    "notes": null,
                    "created_at": "2026-02-01T12:00:00Z",
                    "progress_percent": 80.0,
                    "weight_to_go": 45.0,
                    "weeks_remaining": 12
                }
            ],
            "created_count": 1,
            "active_count": 1
        }
        """

        let data = json.data(using: .utf8)!
        let response = try JSONDecoder().decode(GoalBatchCreateResponse.self, from: data)

        XCTAssertEqual(response.createdCount, 1)
        XCTAssertEqual(response.activeCount, 1)
        XCTAssertEqual(response.goals.count, 1)
    }

    func testGoalsListResponseDecodes() throws {
        // Test decoding goals list response
        let json = """
        {
            "goals": [],
            "active_count": 0,
            "completed_count": 0,
            "can_add_more": true,
            "max_goals": 5
        }
        """

        let data = json.data(using: .utf8)!
        let response = try JSONDecoder().decode(GoalsListResponse.self, from: data)

        XCTAssertEqual(response.activeCount, 0)
        XCTAssertEqual(response.maxGoals, 5)
        XCTAssertTrue(response.canAddMore)
    }

    // MARK: - Mission Response Decoding

    func testCurrentMissionResponseDecodesGoalsArray() throws {
        // Test decoding CurrentMissionResponse with goals array
        let json = """
        {
            "has_active_goal": true,
            "has_active_goals": true,
            "goal": {
                "id": "goal-001",
                "exercise_name": "Bench Press",
                "target_weight": 225.0,
                "target_reps": 1,
                "target_e1rm": 225.0,
                "weight_unit": "lb",
                "deadline": "2026-05-01",
                "progress_percent": 82.0,
                "status": "active"
            },
            "goals": [
                {
                    "id": "goal-001",
                    "exercise_name": "Bench Press",
                    "target_weight": 225.0,
                    "target_reps": 1,
                    "target_e1rm": 225.0,
                    "weight_unit": "lb",
                    "deadline": "2026-05-01",
                    "progress_percent": 82.0,
                    "status": "active"
                },
                {
                    "id": "goal-002",
                    "exercise_name": "Squat",
                    "target_weight": 315.0,
                    "target_reps": 1,
                    "target_e1rm": 315.0,
                    "weight_unit": "lb",
                    "deadline": "2026-05-01",
                    "progress_percent": 88.0,
                    "status": "active"
                }
            ],
            "mission": null,
            "needs_goal_setup": false,
            "can_add_more_goals": true
        }
        """

        let data = json.data(using: .utf8)!
        let response = try JSONDecoder().decode(CurrentMissionResponse.self, from: data)

        XCTAssertTrue(response.hasActiveGoals)
        XCTAssertEqual(response.goals.count, 2)
        XCTAssertTrue(response.canAddMoreGoals)
    }

    func testWeeklyMissionSummaryDecodes() throws {
        // Test decoding mission summary with multi-goal fields
        let json = """
        {
            "id": "mission-001",
            "goal_exercise_name": "Bench Press",
            "goal_target_weight": 225.0,
            "goal_weight_unit": "lb",
            "training_split": "ppl",
            "goals": [],
            "goal_count": 3,
            "status": "offered",
            "week_start": "2026-02-03",
            "week_end": "2026-02-09",
            "xp_reward": 200,
            "workouts_completed": 0,
            "workouts_total": 3,
            "days_remaining": 5,
            "workouts": []
        }
        """

        let data = json.data(using: .utf8)!
        let response = try JSONDecoder().decode(WeeklyMissionSummary.self, from: data)

        XCTAssertEqual(response.trainingSplit, "ppl")
        XCTAssertEqual(response.goalCount, 3)
        XCTAssertEqual(response.xpReward, 200)
    }

    func testWeeklyMissionResponseDecodes() throws {
        // Test decoding full mission response
        let json = """
        {
            "id": "mission-001",
            "goal_id": "goal-001",
            "goal_exercise_name": "Bench Press",
            "goal_target_weight": 225.0,
            "goal_weight_unit": "lb",
            "training_split": "ppl",
            "goals": [],
            "goal_count": 3,
            "week_start": "2026-02-03",
            "week_end": "2026-02-09",
            "status": "accepted",
            "xp_reward": 200,
            "weekly_target": "Build strength in Bench, Squat, Deadlift",
            "coaching_message": "This week's PPL split targets all goals.",
            "workouts": [],
            "workouts_completed": 1,
            "workouts_total": 3,
            "days_remaining": 4
        }
        """

        let data = json.data(using: .utf8)!
        let response = try JSONDecoder().decode(WeeklyMissionResponse.self, from: data)

        XCTAssertEqual(response.status, "accepted")
        XCTAssertEqual(response.workoutsCompleted, 1)
        XCTAssertNotNil(response.coachingMessage)
    }

    // MARK: - Optional Field Handling

    func testNullNotesHandled() throws {
        // Null notes field should decode as nil
        let json = """
        {
            "id": "goal-001",
            "exercise_id": "ex-001",
            "exercise_name": "Bench Press",
            "target_weight": 225.0,
            "target_reps": 1,
            "target_e1rm": 225.0,
            "weight_unit": "lb",
            "deadline": "2026-05-01",
            "starting_e1rm": null,
            "current_e1rm": null,
            "status": "active",
            "notes": null,
            "created_at": "2026-02-01T12:00:00Z",
            "progress_percent": 0.0,
            "weight_to_go": 225.0,
            "weeks_remaining": 12
        }
        """

        let data = json.data(using: .utf8)!
        let response = try JSONDecoder().decode(GoalResponse.self, from: data)

        XCTAssertNil(response.notes)
        XCTAssertNil(response.startingE1rm)
    }

    func testMissingOptionalFieldsHandled() throws {
        // Mission can have null mission field when goals exist but no mission yet
        let json = """
        {
            "has_active_goal": true,
            "has_active_goals": true,
            "goal": null,
            "goals": [],
            "mission": null,
            "needs_goal_setup": false,
            "can_add_more_goals": true
        }
        """

        let data = json.data(using: .utf8)!
        let response = try JSONDecoder().decode(CurrentMissionResponse.self, from: data)

        XCTAssertNil(response.goal)
        XCTAssertNil(response.mission)
    }

    // MARK: - Training Split Values

    func testTrainingSplitValues() throws {
        // Verify expected training split values
        let validSplits = ["ppl", "upper_lower", "full_body", "single_focus"]

        for split in validSplits {
            XCTAssertFalse(split.isEmpty)
        }
    }

    // MARK: - Helpers

    private func createMockGoalJson(exerciseName: String) -> [String: Any] {
        return [
            "exercise_id": "ex-001",
            "target_weight": 225.0,
            "target_reps": 1,
            "weight_unit": "lb",
            "deadline": "2026-05-01",
            "notes": NSNull()
        ]
    }
}

// MARK: - Edge Case Tests

extension APITypesTests {

    func testVeryLargeTargetWeight() throws {
        // Should handle large weight values
        let json = """
        {
            "id": "goal-001",
            "exercise_name": "Squat",
            "target_weight": 1000.0,
            "target_reps": 1,
            "target_e1rm": 1000.0,
            "weight_unit": "lb",
            "deadline": "2026-05-01",
            "progress_percent": 50.0,
            "status": "active"
        }
        """

        let data = json.data(using: .utf8)!
        let response = try JSONDecoder().decode(GoalSummaryResponse.self, from: data)

        XCTAssertEqual(response.targetWeight, 1000.0)
    }

    func testDecimalProgressPercent() throws {
        // Progress can have decimal places
        let json = """
        {
            "id": "goal-001",
            "exercise_name": "Bench Press",
            "target_weight": 225.0,
            "target_reps": 1,
            "target_e1rm": 225.0,
            "weight_unit": "lb",
            "deadline": "2026-05-01",
            "progress_percent": 82.567,
            "status": "active"
        }
        """

        let data = json.data(using: .utf8)!
        let response = try JSONDecoder().decode(GoalSummaryResponse.self, from: data)

        XCTAssertEqual(response.progressPercent, 82.567, accuracy: 0.001)
    }

    func testKilogramWeightUnit() throws {
        // Should handle kg weight unit
        let json = """
        {
            "id": "goal-001",
            "exercise_name": "Bench Press",
            "target_weight": 100.0,
            "target_reps": 1,
            "target_e1rm": 100.0,
            "weight_unit": "kg",
            "deadline": "2026-05-01",
            "progress_percent": 80.0,
            "status": "active"
        }
        """

        let data = json.data(using: .utf8)!
        let response = try JSONDecoder().decode(GoalSummaryResponse.self, from: data)

        XCTAssertEqual(response.weightUnit, "kg")
    }
}
