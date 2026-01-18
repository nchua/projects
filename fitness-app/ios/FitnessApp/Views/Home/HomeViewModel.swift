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

        do {
            async let workoutsTask = APIClient.shared.getWorkouts(limit: 1, offset: 0)
            async let weeklyTask = APIClient.shared.getWeeklyReview()
            async let prsTask = APIClient.shared.getPRs()
            async let insightsTask = APIClient.shared.getInsights()
            async let progressTask = APIClient.shared.getUserProgress()
            async let achievementsTask = APIClient.shared.getRecentAchievements(limit: 3)
            async let questsTask = APIClient.shared.getDailyQuests()
            async let profileTask = APIClient.shared.getProfile()
            async let cooldownTask = APIClient.shared.getCooldownStatus()
            async let exercisesTask = APIClient.shared.getExercises()

            let (workouts, weekly, prs, insightsResponse, progress, achievements, quests, profileResult, cooldowns, exercisesResult) = try await (
                workoutsTask,
                weeklyTask,
                prsTask,
                insightsTask,
                progressTask,
                achievementsTask,
                questsTask,
                profileTask,
                cooldownTask,
                exercisesTask
            )

            userProgress = progress
            recentAchievements = achievements.achievements
            dailyQuests = quests
            profile = profileResult
            cooldownStatus = cooldowns.musclesCooling
            cooldownAgeModifier = cooldowns.ageModifier
            exercises = exercisesResult

            recentWorkout = workouts.first
            weeklyReview = weekly
            recentPRs = prs.prs
            insights = insightsResponse.insights

            // Calculate weekly stats from available data
            weeklyStats.totalVolume = weekly.totalVolume
            // Estimate calories and active time based on workouts
            weeklyStats.calories = weekly.totalWorkouts * 120 // ~120 cal per workout
            weeklyStats.activeMinutes = weekly.totalWorkouts * 45 // ~45 min per workout

            // Load Big Three trends (for Power Levels card)
            await loadBigThreeTrends()

            // Try to load trend for primary lift
            if let firstPR = prs.prs.first {
                do {
                    let trendResponse = try await APIClient.shared.getExerciseTrend(
                        exerciseId: firstPR.exerciseId,
                        timeRange: "12w"
                    )
                    // Convert TrendResponse to LiftTrendResponse
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
                        difficulty: oldQuest.difficulty
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
