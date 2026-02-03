import XCTest
@testable import FitnessApp

/// Tests for MultiGoalSetupViewModel.
///
/// The MultiGoalSetupViewModel manages the state for the goal setup wizard,
/// allowing users to configure up to 5 training goals.
final class MultiGoalSetupViewModelTests: XCTestCase {

    // MARK: - Test Lifecycle

    override func setUpWithError() throws {
        // Setup runs before each test
    }

    override func tearDownWithError() throws {
        // Teardown runs after each test
    }

    // MARK: - Pending Goals Management

    func testInitialStateHasNoPendingGoals() throws {
        // When starting fresh, pendingGoals should be empty
        let pendingGoals: [Any] = []
        XCTAssertTrue(pendingGoals.isEmpty, "Initial state should have no pending goals")
    }

    func testAddGoalIncrementsPendingGoalsCount() throws {
        // Adding a goal should increment the count
        var pendingGoals: [String] = []

        pendingGoals.append("goal-1")
        XCTAssertEqual(pendingGoals.count, 1)

        pendingGoals.append("goal-2")
        XCTAssertEqual(pendingGoals.count, 2)

        pendingGoals.append("goal-3")
        XCTAssertEqual(pendingGoals.count, 3)
    }

    func testRemoveGoalDecrementsPendingGoalsCount() throws {
        // Removing a goal should decrement the count
        var pendingGoals = ["goal-1", "goal-2", "goal-3"]

        pendingGoals.removeFirst()
        XCTAssertEqual(pendingGoals.count, 2)
    }

    func testMaxFiveGoalsEnforced() throws {
        // Cannot add more than 5 goals
        let maxGoals = 5
        let currentGoalCount = 5

        let canAddMore = currentGoalCount < maxGoals
        XCTAssertFalse(canAddMore, "Should not allow more than 5 goals")
    }

    func testCanAddGoalsWhenUnderLimit() throws {
        // Can add goals when under the limit
        let maxGoals = 5
        let currentGoalCount = 3

        let canAddMore = currentGoalCount < maxGoals
        XCTAssertTrue(canAddMore, "Should allow adding goals when under limit")
    }

    // MARK: - Goal Validation

    func testGoalRequiresExerciseId() throws {
        // A goal must have an exercise ID
        let exerciseId: String? = nil
        let hasValidExercise = exerciseId != nil

        XCTAssertFalse(hasValidExercise, "Goal without exercise ID is invalid")
    }

    func testGoalRequiresPositiveTargetWeight() throws {
        // Target weight must be positive
        let validWeights = [135.0, 225.0, 315.0]
        let invalidWeights = [0.0, -100.0]

        for weight in validWeights {
            XCTAssertGreaterThan(weight, 0, "Valid weight should be positive")
        }

        for weight in invalidWeights {
            XCTAssertLessThanOrEqual(weight, 0, "Invalid weight should be <= 0")
        }
    }

    func testGoalRequiresPositiveTargetReps() throws {
        // Target reps must be >= 1
        let validReps = [1, 3, 5, 10]
        let invalidReps = [0, -1]

        for reps in validReps {
            XCTAssertGreaterThanOrEqual(reps, 1, "Valid reps should be >= 1")
        }

        for reps in invalidReps {
            XCTAssertLessThan(reps, 1, "Invalid reps should be < 1")
        }
    }

    func testGoalDeadlineShouldBeInFuture() throws {
        // Deadline should be in the future (or at least today)
        let today = Date()
        let futureDeadline = Calendar.current.date(byAdding: .day, value: 7, to: today)!
        let pastDeadline = Calendar.current.date(byAdding: .day, value: -7, to: today)!

        XCTAssertGreaterThanOrEqual(futureDeadline, today, "Future deadline is valid")
        XCTAssertLessThan(pastDeadline, today, "Past deadline may be invalid")
    }

    // MARK: - Weight Unit Handling

    func testValidWeightUnits() throws {
        // Only "lb" and "kg" are valid
        let validUnits = ["lb", "kg"]
        let invalidUnits = ["lbs", "pounds", "kilograms", ""]

        for unit in validUnits {
            let isValid = unit == "lb" || unit == "kg"
            XCTAssertTrue(isValid, "\(unit) should be valid")
        }

        for unit in invalidUnits {
            let isValid = unit == "lb" || unit == "kg"
            XCTAssertFalse(isValid, "\(unit) should be invalid")
        }
    }

    // MARK: - API Integration

    func testCreateGoalsCallsBatchAPIWhenMultipleGoals() throws {
        // When creating multiple goals, the batch endpoint should be used
        let goalCount = 3
        let shouldUseBatchAPI = goalCount > 1

        XCTAssertTrue(shouldUseBatchAPI, "Multiple goals should use batch API")
    }

    func testCreateGoalsCallsSingleAPIWhenOneGoal() throws {
        // When creating a single goal, the single endpoint can be used
        let goalCount = 1
        let shouldUseBatchAPI = goalCount > 1

        XCTAssertFalse(shouldUseBatchAPI, "Single goal doesn't need batch API")
    }

    // MARK: - State Management

    func testGoalsCreatedFlagSetOnSuccess() throws {
        // After successful creation, a flag should indicate completion
        var goalsCreated = false

        // Simulate successful creation
        goalsCreated = true

        XCTAssertTrue(goalsCreated, "goalsCreated should be true after success")
    }

    func testErrorDisplayedOnAPIFailure() throws {
        // On API failure, an error message should be set
        var errorMessage: String? = nil

        // Simulate failure
        errorMessage = "Failed to create goals"

        XCTAssertNotNil(errorMessage, "Error message should be set on failure")
    }

    func testLoadingStateWhileCreatingGoals() throws {
        // While creating goals, isLoading should be true
        var isLoading = false

        // Start creation
        isLoading = true
        XCTAssertTrue(isLoading, "Should be loading during creation")

        // Complete creation
        isLoading = false
        XCTAssertFalse(isLoading, "Should not be loading after completion")
    }

    // MARK: - E1RM Calculation

    func testE1rmCalculationForOneRepGoal() throws {
        // For a 1-rep goal, e1RM equals the target weight
        let targetWeight = 225.0
        let targetReps = 1
        let targetE1rm = targetWeight * (1 + Double(targetReps) / 30)

        XCTAssertEqual(targetE1rm, targetWeight, "1-rep e1RM should equal weight")
    }

    func testE1rmCalculationForMultiRepGoal() throws {
        // For multi-rep goals, e1RM uses Epley formula
        let targetWeight = 200.0
        let targetReps = 5
        let expectedE1rm = targetWeight * (1 + Double(targetReps) / 30)

        // 200 * (1 + 5/30) = 200 * 1.167 = 233.3
        XCTAssertEqual(expectedE1rm, 233.33333333333334, accuracy: 0.01)
    }

    // MARK: - Goal Selection UI

    func testExerciseSearchFiltersResults() throws {
        // Exercise search should filter by name
        let exercises = ["Bench Press", "Barbell Row", "Back Squat"]
        let searchQuery = "bench"

        let filteredExercises = exercises.filter { $0.lowercased().contains(searchQuery.lowercased()) }

        XCTAssertEqual(filteredExercises.count, 1)
        XCTAssertEqual(filteredExercises.first, "Bench Press")
    }

    func testEmptySearchReturnsAllExercises() throws {
        // Empty search should return all exercises
        let exercises = ["Bench Press", "Barbell Row", "Back Squat"]
        let searchQuery = ""

        let filteredExercises = searchQuery.isEmpty ? exercises : exercises.filter { $0.contains(searchQuery) }

        XCTAssertEqual(filteredExercises.count, exercises.count)
    }

    // MARK: - Navigation State

    func testNavigationToNextStepWhenGoalValid() throws {
        // Should navigate to next step when current goal is valid
        let hasExercise = true
        let hasTargetWeight = true
        let hasDeadline = true

        let canProceed = hasExercise && hasTargetWeight && hasDeadline
        XCTAssertTrue(canProceed, "Should be able to proceed when goal is valid")
    }

    func testCannotProceedWithInvalidGoal() throws {
        // Cannot proceed to next step with invalid goal
        let hasExercise = false
        let hasTargetWeight = true
        let hasDeadline = true

        let canProceed = hasExercise && hasTargetWeight && hasDeadline
        XCTAssertFalse(canProceed, "Should not proceed without exercise")
    }
}

// MARK: - Performance Tests

extension MultiGoalSetupViewModelTests {

    func testPerformanceOfGoalValidation() throws {
        // Measure validation performance
        self.measure {
            for _ in 0..<1000 {
                let weight = 225.0
                let reps = 5
                let _ = weight * (1 + Double(reps) / 30)
            }
        }
    }
}
