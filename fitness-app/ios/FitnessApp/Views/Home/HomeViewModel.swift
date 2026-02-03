import Foundation
import SwiftUI

struct WeeklyStats {
    var calories: Int = 0
    var caloriesGoal: Int = 650
    var activeMinutes: Int = 0
    var activeGoal: Int = 60
    var workoutsGoal: Int = 4
    var totalVolume: Double = 0
}

// Big Three exercise name variations (same as ProgressViewModel)
private let homeBigThreeVariations: [[String]] = [
    ["Back Squat", "Barbell Back Squat", "Squat", "BB Squat", "Barbell Squat", "Low Bar Squat", "High Bar Squat"],
    ["Bench Press", "Barbell Bench Press", "BB Bench", "Flat Bench Press", "Flat Barbell Bench Press"],
    ["Deadlift", "Barbell Deadlift", "Conventional Deadlift", "BB Deadlift"]
]

@MainActor
class HomeViewModel: ObservableObject {
    @Published var recentWorkout: WorkoutSummaryResponse?
    @Published var weeklyReview: WeeklyReviewResponse?
    @Published var recentPRs: [PRResponse] = []
    @Published var insights: [InsightResponse] = []
    @Published var primaryLiftTrend: LiftTrendResponse?
    @Published var weeklyStats = WeeklyStats()
    @Published var userProgress: UserProgressResponse?
    @Published var recentAchievements: [AchievementResponse] = []
    @Published var dailyQuests: DailyQuestsResponse?
    @Published var profile: ProfileResponse?
    @Published var cooldownStatus: [MuscleCooldownStatus] = []
    @Published var cooldownAgeModifier: Double = 1.0
    @Published var currentMission: CurrentMissionResponse?
    @Published var missionLoadError: String?
    @Published var goalForEdit: GoalResponse?
    @Published var isLoading = false
    @Published var error: String?

    // Big Three data (loaded from trends like Stats page)
    @Published var exercises: [ExerciseResponse] = []
    @Published var bigThreeTrends: [String: TrendResponse] = [:] // exerciseId -> trend

    // HealthKit integration
    @Published var healthKitAuthorized = false
    @Published var todaySteps: Int = 0
    @Published var todayCalories: Int = 0
    @Published var todayExerciseMinutes: Int = 0
    @Published var todayStandHours: Int = 0
    @Published var isHealthKitSyncing = false

    // Weekly HealthKit stats
    @Published var weeklySteps: Int = 0
    @Published var weeklyCalories: Int = 0
    @Published var weeklyExerciseMinutes: Int = 0
    @Published var weeklyAvgSteps: Int = 0

    // Computed properties for easier access
    var hunterLevel: Int { userProgress?.level ?? 1 }
    var hunterRank: HunterRank { HunterRank(rawValue: userProgress?.rank ?? "E") ?? .e }
    var currentXP: Int { userProgress?.totalXp ?? 0 }
    var xpToNextLevel: Int {
        guard let progress = userProgress else { return 100 }
        return XPCalculator.xpToNextLevel(currentLevel: progress.level, totalXp: progress.totalXp)
    }

    var levelProgress: Double {
        guard let progress = userProgress else { return 0.0 }
        return XPCalculator.levelProgress(currentLevel: progress.level, totalXp: progress.totalXp)
    }
    var streakDays: Int { userProgress?.currentStreak ?? 0 }

    // Profile-based properties for avatar sync
    var hunterName: String {
        guard let email = profile?.email else { return "Hunter" }
        return email.components(separatedBy: "@").first?.capitalized ?? "Hunter"
    }

    var hunterInitials: String {
        guard let email = profile?.email else { return "H" }
        let components = email.components(separatedBy: "@").first?.components(separatedBy: ".") ?? []
        if components.count >= 2 {
            return String(components[0].prefix(1) + components[1].prefix(1)).uppercased()
        } else if let first = components.first, first.count >= 2 {
            return String(first.prefix(2)).uppercased()
        }
        return "NC"
    }

    /// Find Big Three exercises from loaded exercises list
    var bigThreeExercises: [ExerciseResponse] {
        homeBigThreeVariations.compactMap { variations in
            for variation in variations {
                if let exercise = exercises.first(where: { $0.name.caseInsensitiveCompare(variation) == .orderedSame }) {
                    return exercise
                }
            }
            return nil
        }
    }

    /// Big Three lifts with current e1RM from trend data
    var bigThreeLifts: [BigThreeLift] {
        let displayNames = ["Squat", "Bench Press", "Deadlift"]

        return displayNames.enumerated().map { index, displayName in
            // Check if we have the exercise and trend data
            if index < bigThreeExercises.count {
                let exercise = bigThreeExercises[index]
                let trend = bigThreeTrends[exercise.id]
                let e1rm = trend?.currentE1rm ?? 0
                let trendPercent = trend?.percentChange

                return BigThreeLift(
                    name: displayName,
                    e1rm: e1rm,
                    trendPercent: trendPercent
                )
            } else {
                // No exercise found - show placeholder
                return BigThreeLift(
                    name: displayName,
                    e1rm: 0,
                    trendPercent: nil
                )
            }
        }
    }

    /// Load trend data for Big Three exercises
    func loadBigThreeTrends() async {
        for exercise in bigThreeExercises {
            do {
                let trend = try await APIClient.shared.getExerciseTrend(
                    exerciseId: exercise.id,
                    timeRange: "12w"
                )
                bigThreeTrends[exercise.id] = trend
            } catch {
                // Silently fail - not critical
                print("DEBUG: Failed to load trend for \(exercise.name): \(error)")
            }
        }
    }

    func loadData() async {
        isLoading = true
        error = nil

        // Load each data source independently so one failure doesn't break everything
        await withTaskGroup(of: Void.self) { group in
            group.addTask { @MainActor in
                do {
                    let workouts = try await APIClient.shared.getWorkouts(limit: 1, offset: 0)
                    self.recentWorkout = workouts.first
                } catch {
                    print("DEBUG: Failed to load workouts: \(error)")
                }
            }

            group.addTask { @MainActor in
                do {
                    let weekly = try await APIClient.shared.getWeeklyReview()
                    self.weeklyReview = weekly
                    self.weeklyStats.totalVolume = weekly.totalVolume
                    self.weeklyStats.calories = weekly.totalWorkouts * 120
                    self.weeklyStats.activeMinutes = weekly.totalWorkouts * 45
                } catch {
                    print("DEBUG: Failed to load weekly review: \(error)")
                }
            }

            group.addTask { @MainActor in
                do {
                    let prs = try await APIClient.shared.getPRs()
                    self.recentPRs = prs.prs
                } catch {
                    print("DEBUG: Failed to load PRs: \(error)")
                }
            }

            group.addTask { @MainActor in
                do {
                    let insightsResponse = try await APIClient.shared.getInsights()
                    self.insights = insightsResponse.insights
                } catch {
                    print("DEBUG: Failed to load insights: \(error)")
                }
            }

            group.addTask { @MainActor in
                do {
                    let progress = try await APIClient.shared.getUserProgress()
                    self.userProgress = progress
                } catch let apiError as APIError {
                    if case .unauthorized = apiError {
                        // Will be handled by auth manager
                    }
                    print("DEBUG: Failed to load user progress: \(apiError)")
                } catch {
                    print("DEBUG: Failed to load user progress: \(error)")
                }
            }

            group.addTask { @MainActor in
                do {
                    let achievements = try await APIClient.shared.getRecentAchievements(limit: 3)
                    self.recentAchievements = achievements.achievements
                } catch {
                    print("DEBUG: Failed to load achievements: \(error)")
                }
            }

            group.addTask { @MainActor in
                do {
                    let quests = try await APIClient.shared.getDailyQuests()
                    self.dailyQuests = quests
                } catch {
                    print("DEBUG: Failed to load quests: \(error)")
                }
            }

            group.addTask { @MainActor in
                do {
                    let profileResult = try await APIClient.shared.getProfile()
                    self.profile = profileResult
                } catch {
                    print("DEBUG: Failed to load profile: \(error)")
                }
            }

            group.addTask { @MainActor in
                do {
                    let cooldowns = try await APIClient.shared.getCooldownStatus()
                    self.cooldownStatus = cooldowns.musclesCooling
                    self.cooldownAgeModifier = cooldowns.ageModifier
                } catch {
                    print("DEBUG: Failed to load cooldown status: \(error)")
                }
            }

            group.addTask { @MainActor in
                do {
                    let exercisesResult = try await APIClient.shared.getExercises()
                    self.exercises = exercisesResult
                } catch {
                    print("DEBUG: Failed to load exercises: \(error)")
                }
            }

            group.addTask { @MainActor in
                do {
                    self.currentMission = try await APIClient.shared.getCurrentMission()
                    self.missionLoadError = nil
                } catch {
                    print("DEBUG: Failed to load current mission: \(error)")
                    self.missionLoadError = error.localizedDescription
                }
            }
        }

        // Load Big Three trends after exercises are loaded
        await loadBigThreeTrends()

        // Try to load trend for primary lift
        if let firstPR = recentPRs.first {
            do {
                let trendResponse = try await APIClient.shared.getExerciseTrend(
                    exerciseId: firstPR.exerciseId,
                    timeRange: "12w"
                )
                primaryLiftTrend = LiftTrendResponse(
                    exerciseId: firstPR.exerciseId,
                    exerciseName: firstPR.exerciseName,
                    trendDirection: trendResponse.trendDirection,
                    percentChange: trendResponse.percentChange,
                    dataPoints: trendResponse.dataPoints
                )
            } catch {
                // Silently fail for trend - not critical
            }
        }

        isLoading = false

        // Load HealthKit data after main data
        await loadHealthKitData()
    }

    // MARK: - HealthKit

    func requestHealthKitAccess() async {
        let manager = HealthKitManager.shared
        await manager.requestAuthorization()
        healthKitAuthorized = manager.isAuthorized

        if healthKitAuthorized {
            await loadHealthKitData()
        }
    }

    func loadHealthKitData() async {
        let manager = HealthKitManager.shared

        guard manager.isHealthDataAvailable else { return }

        if !manager.isAuthorized {
            await manager.requestAuthorization()
        }

        healthKitAuthorized = manager.isAuthorized
        guard healthKitAuthorized else { return }

        // Fetch today's stats (also fetches weekly)
        await manager.fetchTodayStats()

        // Update local published properties - today
        todaySteps = manager.todaySteps
        todayCalories = manager.todayActiveCalories
        todayExerciseMinutes = manager.todayExerciseMinutes
        todayStandHours = manager.todayStandHours

        // Update weekly stats
        weeklySteps = manager.weeklySteps
        weeklyCalories = manager.weeklyCalories
        weeklyExerciseMinutes = manager.weeklyExerciseMinutes
        weeklyAvgSteps = manager.weeklyAvgSteps

        // Sync to backend in background
        isHealthKitSyncing = true
        await manager.syncTodayOnly()
        isHealthKitSyncing = false
    }

    func syncHealthKit() async {
        isHealthKitSyncing = true
        await HealthKitManager.shared.syncToBackend()
        await loadHealthKitData()
        isHealthKitSyncing = false
    }

    // MARK: - Mission Actions

    func acceptMission(missionId: String) async {
        do {
            let _ = try await APIClient.shared.acceptMission(id: missionId)
            // Reload mission data
            self.currentMission = try await APIClient.shared.getCurrentMission()
            // Reload quests (they'll now show mission objectives)
            self.dailyQuests = try await APIClient.shared.getDailyQuests()
        } catch {
            print("DEBUG: Failed to accept mission: \(error)")
            self.error = error.localizedDescription
        }
    }

    func declineMission(missionId: String) async {
        do {
            let _ = try await APIClient.shared.declineMission(id: missionId)
            // Reload mission data
            self.currentMission = try await APIClient.shared.getCurrentMission()
        } catch {
            print("DEBUG: Failed to decline mission: \(error)")
            self.error = error.localizedDescription
        }
    }

    // MARK: - Goal Actions

    func loadGoalForEdit(goalId: String) async {
        do {
            // Load the full goal details for editing
            let goals = try await APIClient.shared.getGoals()
            // Find the matching goal from the list
            if let goal = goals.goals.first(where: { $0.id == goalId }) {
                // Convert GoalSummaryResponse to GoalResponse by fetching full details
                // For now, create a GoalResponse from summary data
                self.goalForEdit = GoalResponse(
                    id: goal.id,
                    exerciseId: "",  // Not needed for editing
                    exerciseName: goal.exerciseName,
                    targetWeight: goal.targetWeight,
                    targetReps: goal.targetReps,
                    targetE1rm: goal.targetE1rm,
                    weightUnit: goal.weightUnit,
                    deadline: goal.deadline,
                    startingE1rm: nil,
                    currentE1rm: nil,
                    status: goal.status,
                    notes: nil,
                    createdAt: "",
                    progressPercent: goal.progressPercent,
                    weightToGo: 0,
                    weeksRemaining: 0
                )
            }
        } catch {
            print("DEBUG: Failed to load goal for edit: \(error)")
            self.error = error.localizedDescription
        }
    }

    func abandonGoal() async {
        guard let goalId = currentMission?.goal?.id else {
            print("DEBUG: No goal to abandon")
            return
        }

        do {
            try await APIClient.shared.deleteGoal(id: goalId)
            // Reload mission data (should now show empty state)
            self.currentMission = try await APIClient.shared.getCurrentMission()
            // Also reload quests
            self.dailyQuests = try await APIClient.shared.getDailyQuests()
        } catch {
            print("DEBUG: Failed to abandon goal: \(error)")
            self.error = error.localizedDescription
        }
    }

    // MARK: - Quest Actions

    func claimQuest(_ questId: String) async {
        do {
            let response = try await APIClient.shared.claimQuestReward(questId: questId)

            // Update local quests state
            if var quests = dailyQuests?.quests {
                if let index = quests.firstIndex(where: { $0.id == questId }) {
                    // Create updated quest with isClaimed = true
                    let oldQuest = quests[index]
                    let updatedQuest = QuestResponse(
                        id: oldQuest.id,
                        questId: oldQuest.questId,
                        name: oldQuest.name,
                        description: oldQuest.description,
                        questType: oldQuest.questType,
                        targetValue: oldQuest.targetValue,
                        xpReward: oldQuest.xpReward,
                        progress: oldQuest.progress,
                        isCompleted: oldQuest.isCompleted,
                        isClaimed: true,
                        difficulty: oldQuest.difficulty,
                        completedByWorkoutId: oldQuest.completedByWorkoutId
                    )
                    quests[index] = updatedQuest

                    dailyQuests = DailyQuestsResponse(
                        quests: quests,
                        refreshAt: dailyQuests?.refreshAt ?? "",
                        completedCount: dailyQuests?.completedCount ?? 0,
                        totalCount: dailyQuests?.totalCount ?? 0
                    )
                }
            }

            // Update user progress with new XP
            if response.leveledUp || response.rankChanged {
                // Reload all progress data to get updated values
                if let newProgress = try? await APIClient.shared.getUserProgress() {
                    userProgress = newProgress
                }
            } else {
                // Just update XP locally
                if let progress = userProgress {
                    // Create a new response with updated XP
                    userProgress = UserProgressResponse(
                        totalXp: response.totalXp,
                        level: response.level,
                        rank: response.rank,
                        currentStreak: progress.currentStreak,
                        longestStreak: progress.longestStreak,
                        totalWorkouts: progress.totalWorkouts,
                        totalVolumeLb: progress.totalVolumeLb,
                        totalPrs: progress.totalPrs,
                        xpToNextLevel: progress.xpToNextLevel,
                        levelProgress: progress.levelProgress,
                        lastWorkoutDate: progress.lastWorkoutDate
                    )
                }
            }
        } catch let apiError as APIError {
            if case .unauthorized = apiError { return }
            self.error = apiError.localizedDescription
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// Response type for lift trends (matches what HomeView expects)
struct LiftTrendResponse {
    let exerciseId: String
    let exerciseName: String
    let trendDirection: String
    let percentChange: Double?
    let dataPoints: [DataPoint]
}
