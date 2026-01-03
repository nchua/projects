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
    @Published var isLoading = false
    @Published var error: String?

    // HealthKit integration
    @Published var healthKitAuthorized = false
    @Published var todaySteps: Int = 0
    @Published var todayCalories: Int = 0
    @Published var todayExerciseMinutes: Int = 0
    @Published var todayStandHours: Int = 0
    @Published var isHealthKitSyncing = false

    // Computed properties for easier access
    var hunterLevel: Int { userProgress?.level ?? 1 }
    var hunterRank: HunterRank { HunterRank(rawValue: userProgress?.rank ?? "E") ?? .e }
    var currentXP: Int { userProgress?.totalXp ?? 0 }
    var xpToNextLevel: Int { userProgress?.xpToNextLevel ?? 100 }
    var levelProgress: Double { userProgress?.levelProgress ?? 0.0 }
    var streakDays: Int { userProgress?.currentStreak ?? 0 }

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

            let (workouts, weekly, prs, insightsResponse, progress, achievements, quests) = try await (
                workoutsTask,
                weeklyTask,
                prsTask,
                insightsTask,
                progressTask,
                achievementsTask,
                questsTask
            )

            userProgress = progress
            recentAchievements = achievements.achievements
            dailyQuests = quests

            recentWorkout = workouts.first
            weeklyReview = weekly
            recentPRs = prs.prs
            insights = insightsResponse.insights

            // Calculate weekly stats from available data
            weeklyStats.totalVolume = weekly.totalVolume
            // Estimate calories and active time based on workouts
            weeklyStats.calories = weekly.totalWorkouts * 120 // ~120 cal per workout
            weeklyStats.activeMinutes = weekly.totalWorkouts * 45 // ~45 min per workout

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

        // Skip if HealthKit not available or not authorized
        guard manager.isHealthDataAvailable else { return }

        // Request authorization if not yet authorized
        if !manager.isAuthorized {
            await manager.requestAuthorization()
        }

        healthKitAuthorized = manager.isAuthorized
        guard healthKitAuthorized else { return }

        // Fetch today's stats
        await manager.fetchTodayStats()

        // Update local published properties
        todaySteps = manager.todaySteps
        todayCalories = manager.todayActiveCalories
        todayExerciseMinutes = manager.todayExerciseMinutes
        todayStandHours = manager.todayStandHours

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
