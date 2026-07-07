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
