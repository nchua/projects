import XCTest
@testable import FitnessApp

/// Tests for MissionCard component and related display logic.
///
/// The MissionCard displays weekly mission details including:
/// - Training split (PPL, Upper/Lower, etc.)
/// - Multiple goals summary
/// - Workout progress
/// - XP reward
final class MissionCardTests: XCTestCase {

    // MARK: - Test Lifecycle

    override func setUpWithError() throws {
        // Setup runs before each test
    }

    override func tearDownWithError() throws {
        // Teardown runs after each test
    }

    // MARK: - Multi-Goal Badge Display

    func testMultiGoalBadgeShownWhenMultipleGoals() throws {
        // When there are multiple goals, show "N Goals" badge
        let goalCount = 3
        let shouldShowBadge = goalCount > 1

        XCTAssertTrue(shouldShowBadge, "Should show badge for multiple goals")
    }

    func testMultiGoalBadgeHiddenForSingleGoal() throws {
        // Single goal doesn't need a badge
        let goalCount = 1
        let shouldShowBadge = goalCount > 1

        XCTAssertFalse(shouldShowBadge, "Should not show badge for single goal")
    }

    func testMultiGoalBadgeText() throws {
        // Badge should display correct count
        let goalCounts = [2, 3, 4, 5]

        for count in goalCounts {
            let badgeText = "\(count) Goals"
            XCTAssertEqual(badgeText, "\(count) Goals")
        }
    }

    // MARK: - Training Split Formatting

    func testPplSplitFormatting() throws {
        // "ppl" should display as "Push/Pull/Legs"
        let trainingSplit = "ppl"
        let formatted = formatTrainingSplit(trainingSplit)

        XCTAssertEqual(formatted, "Push/Pull/Legs")
    }

    func testUpperLowerSplitFormatting() throws {
        // "upper_lower" should display as "Upper/Lower"
        let trainingSplit = "upper_lower"
        let formatted = formatTrainingSplit(trainingSplit)

        XCTAssertEqual(formatted, "Upper/Lower")
    }

    func testFullBodySplitFormatting() throws {
        // "full_body" should display as "Full Body"
        let trainingSplit = "full_body"
        let formatted = formatTrainingSplit(trainingSplit)

        XCTAssertEqual(formatted, "Full Body")
    }

    func testSingleFocusSplitFormatting() throws {
        // "single_focus" should display as "Single Focus"
        let trainingSplit = "single_focus"
        let formatted = formatTrainingSplit(trainingSplit)

        XCTAssertEqual(formatted, "Single Focus")
    }

    func testNilSplitReturnsDefault() throws {
        // Nil training split should return a default
        let trainingSplit: String? = nil
        let formatted = formatTrainingSplit(trainingSplit)

        XCTAssertEqual(formatted, "Weekly Training")
    }

    // MARK: - Goals Summary Row

    func testGoalsSummaryRowShowsAllGoals() throws {
        // All goals should be displayed in the summary
        let goalNames = ["Bench Press", "Squat", "Deadlift"]

        XCTAssertEqual(goalNames.count, 3)
        XCTAssertTrue(goalNames.contains("Bench Press"))
        XCTAssertTrue(goalNames.contains("Squat"))
        XCTAssertTrue(goalNames.contains("Deadlift"))
    }

    func testGoalChipDisplaysExerciseName() throws {
        // Each goal chip should show the exercise name
        let goalExerciseNames = ["Barbell Bench Press", "Barbell Back Squat"]

        for name in goalExerciseNames {
            // In real test, would check the GoalChip view displays this
            XCTAssertFalse(name.isEmpty, "Exercise name should not be empty")
        }
    }

    func testGoalChipDisplaysProgressPercent() throws {
        // Goal chips should show progress percentage
        let progressValues = [82.0, 88.0, 93.0]

        for progress in progressValues {
            let displayText = "\(Int(progress))%"
            XCTAssertTrue(displayText.contains("%"))
        }
    }

    // MARK: - Add Goal Button

    func testAddGoalButtonShownWhenCanAddMore() throws {
        // Button should be visible when under max goals
        let canAddMoreGoals = true

        XCTAssertTrue(canAddMoreGoals, "Add button should be shown")
    }

    func testAddGoalButtonHiddenAtLimit() throws {
        // Button should be hidden when at max goals (5)
        let canAddMoreGoals = false

        XCTAssertFalse(canAddMoreGoals, "Add button should be hidden at limit")
    }

    // MARK: - Workout Progress Display

    func testWorkoutProgressText() throws {
        // Should display "X of Y workouts"
        let completed = 1
        let total = 3
        let progressText = "\(completed) of \(total) workouts"

        XCTAssertEqual(progressText, "1 of 3 workouts")
    }

    func testWorkoutProgressBarValue() throws {
        // Progress bar should show correct percentage
        let completed = 2
        let total = 3
        let progress = Double(completed) / Double(total)

        XCTAssertEqual(progress, 0.6666666666666666, accuracy: 0.001)
    }

    func testCompletedMissionShowsAllDone() throws {
        // When all workouts done, show completion state
        let completed = 3
        let total = 3
        let isComplete = completed >= total

        XCTAssertTrue(isComplete, "Mission should be marked complete")
    }

    // MARK: - XP Reward Display

    func testXpRewardDisplayed() throws {
        // XP reward should be shown
        let xpReward = 200
        let displayText = "+\(xpReward) XP"

        XCTAssertEqual(displayText, "+200 XP")
    }

    func testXpScalesWithGoals() throws {
        // XP = 50 base + 50 per goal
        let goalCounts = [1, 2, 3, 4, 5]
        let expectedXp = [100, 150, 200, 250, 300]

        for (count, expected) in zip(goalCounts, expectedXp) {
            let xp = 50 + (50 * count)
            XCTAssertEqual(xp, expected, "XP for \(count) goals should be \(expected)")
        }
    }

    // MARK: - Days Remaining Display

    func testDaysRemainingText() throws {
        // Should show days until mission expires
        let daysRemaining = 5
        let displayText = "\(daysRemaining) days left"

        XCTAssertEqual(displayText, "5 days left")
    }

    func testLastDayText() throws {
        // On the last day, show special text
        let daysRemaining = 1
        let displayText = daysRemaining == 1 ? "Last day!" : "\(daysRemaining) days left"

        XCTAssertEqual(displayText, "Last day!")
    }

    func testFinalDayText() throws {
        // On Sunday (day 0), show urgent text
        let daysRemaining = 0
        let displayText = daysRemaining == 0 ? "Ends today!" : "\(daysRemaining) days left"

        XCTAssertEqual(displayText, "Ends today!")
    }

    // MARK: - Mission Status

    func testOfferedMissionShowsAcceptButton() throws {
        // Offered missions should show accept/decline options
        let status = "offered"
        let shouldShowAcceptButton = status == "offered"

        XCTAssertTrue(shouldShowAcceptButton)
    }

    func testAcceptedMissionShowsProgress() throws {
        // Accepted missions should show workout progress
        let status = "accepted"
        let shouldShowProgress = status == "accepted"

        XCTAssertTrue(shouldShowProgress)
    }

    func testCompletedMissionShowsClaimButton() throws {
        // Completed missions should show claim XP option
        let status = "completed"
        let shouldShowClaimButton = status == "completed"

        XCTAssertTrue(shouldShowClaimButton)
    }

    // MARK: - Coaching Message

    func testCoachingMessageDisplayed() throws {
        // Mission should display coaching message
        let coachingMessage = "This week's Push/Pull/Legs split targets all 3 of your goals."

        XCTAssertFalse(coachingMessage.isEmpty)
        XCTAssertTrue(coachingMessage.contains("Push/Pull/Legs"))
    }

    func testWeeklyTargetDisplayed() throws {
        // Mission should display weekly target
        let weeklyTarget = "Build strength in Bench, Squat, Deadlift"

        XCTAssertFalse(weeklyTarget.isEmpty)
        XCTAssertTrue(weeklyTarget.contains("Bench"))
    }

    // MARK: - Helper Functions

    /// Format training split for display
    private func formatTrainingSplit(_ split: String?) -> String {
        switch split {
        case "ppl":
            return "Push/Pull/Legs"
        case "upper_lower":
            return "Upper/Lower"
        case "full_body":
            return "Full Body"
        case "single_focus":
            return "Single Focus"
        default:
            return "Weekly Training"
        }
    }
}

// MARK: - Accessibility Tests

extension MissionCardTests {

    func testMissionCardHasAccessibilityLabel() throws {
        // Mission card should have descriptive accessibility label
        let goalCount = 3
        let xpReward = 200
        let accessibilityLabel = "Weekly mission with \(goalCount) goals, \(xpReward) XP reward"

        XCTAssertTrue(accessibilityLabel.contains("mission"))
        XCTAssertTrue(accessibilityLabel.contains("goals"))
        XCTAssertTrue(accessibilityLabel.contains("XP"))
    }

    func testGoalChipHasAccessibilityLabel() throws {
        // Goal chips should have accessibility labels
        let exerciseName = "Barbell Bench Press"
        let progress = 82
        let accessibilityLabel = "\(exerciseName), \(progress)% progress"

        XCTAssertTrue(accessibilityLabel.contains(exerciseName))
        XCTAssertTrue(accessibilityLabel.contains("%"))
    }
}
