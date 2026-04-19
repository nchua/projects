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
    @Published var profile: ProfileResponse?
    @Published var cooldownStatus: [MuscleCooldownStatus] = []
    @Published var cooldownAgeModifier: Double = 1.0
    @Published var currentMission: CurrentMissionResponse?
    @Published var missionLoadError: String?
    @Published var goalForEdit: GoalResponse?
    @Published var weeklyProgressReport: WeeklyProgressReportResponse?
    @Published var isLoading = false
    @Published var error: String?

    /// Errors from individual endpoints in `loadData()`. Keyed by a short endpoint
    /// name (e.g. "workouts", "quests"); value is a user-visible message.
    /// Surfaced in a compact banner on HomeView so users see partial failures
    /// instead of blank dashboards.
    @Published var dataLoadErrors: [String: String] = [:]

    /// True when at least one endpoint failed during the most recent load.
    var hasDataLoadErrors: Bool { !dataLoadErrors.isEmpty }

    /// Human-readable summary for the banner (e.g. "Quests, PRs").
    var dataLoadErrorSummary: String {
        let names = dataLoadErrors.keys.sorted().map { $0.capitalized }
        return names.joined(separator: ", ")
    }

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

    // Weekly Report computed properties for card display
    var weeklyReportDateRange: String {
        guard let report = weeklyProgressReport else { return "" }
        let start = report.weekStart.parseISO8601Date() ?? Date()
        let end = report.weekEnd.parseISO8601Date() ?? Date()
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d"
        return "\(formatter.string(from: start)) – \(formatter.string(from: end))"
    }

    var weeklyReportStatus: String {
        guard let report = weeklyProgressReport, !report.goalReports.isEmpty else { return "on_track" }
        if report.goalReports.contains(where: { $0.status == "behind" }) { return "behind" }
        if report.goalReports.contains(where: { $0.status == "ahead" }) { return "ahead" }
        return "on_track"
    }

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
        BigThree.orderedVariations.compactMap { variations in
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
                #if DEBUG
                print("DEBUG: Failed to load trend for \(exercise.name): \(error)")
                #endif
            }
        }
    }

    func loadData() async {
        isLoading = true
        error = nil
        // Clear prior endpoint errors at the start of every load so the banner
        // reflects only the most recent attempt.
        dataLoadErrors = [:]

        // Load each data source independently so one failure doesn't break everything
        await withTaskGroup(of: Void.self) { group in
            group.addTask { @MainActor in
                do {
                    let workouts = try await APIClient.shared.getWorkouts(limit: 1, offset: 0)
                    self.recentWorkout = workouts.first
                } catch {
                    self.recordLoadError("workouts", error)
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
                    self.recordLoadError("weekly review", error)
                }
            }

            group.addTask { @MainActor in
                do {
                    let prs = try await APIClient.shared.getPRs()
                    self.recentPRs = prs.prs
                } catch {
                    self.recordLoadError("PRs", error)
                }
            }

            group.addTask { @MainActor in
                do {
                    let insightsResponse = try await APIClient.shared.getInsights()
                    self.insights = insightsResponse.insights
                } catch {
                    self.recordLoadError("insights", error)
                }
            }

            group.addTask { @MainActor in
                do {
                    let progress = try await APIClient.shared.getUserProgress()
                    self.userProgress = progress
                } catch let apiError as APIError {
                    if case .unauthorized = apiError {
                        // Will be handled by auth manager; don't surface in banner.
                    } else {
                        self.recordLoadError("progress", apiError)
                    }
                } catch {
                    self.recordLoadError("progress", error)
                }
            }

            group.addTask { @MainActor in
                do {
                    let achievements = try await APIClient.shared.getRecentAchievements(limit: 3)
                    self.recentAchievements = achievements.achievements
                } catch {
                    self.recordLoadError("achievements", error)
                }
            }

            group.addTask { @MainActor in
                do {
                    let quests = try await APIClient.shared.getDailyQuests()
                    self.dailyQuests = quests
                } catch {
                    self.recordLoadError("quests", error)
                }
            }

            group.addTask { @MainActor in
                do {
                    let profileResult = try await APIClient.shared.getProfile()
                    self.profile = profileResult
                } catch {
                    self.recordLoadError("profile", error)
                }
            }

            group.addTask { @MainActor in
                do {
                    let cooldowns = try await APIClient.shared.getCooldownStatus()
                    self.cooldownStatus = cooldowns.musclesCooling
                    self.cooldownAgeModifier = cooldowns.ageModifier
                } catch {
                    self.recordLoadError("recovery", error)
                }
            }

            group.addTask { @MainActor in
                do {
                    let exercisesResult = try await APIClient.shared.getExercises()
                    self.exercises = exercisesResult
                } catch {
                    self.recordLoadError("exercises", error)
                }
            }

            group.addTask { @MainActor in
                do {
                    self.currentMission = try await APIClient.shared.getCurrentMission()
                    self.missionLoadError = nil
                } catch {
                    self.missionLoadError = error.localizedDescription
                    self.recordLoadError("mission", error)
                }
            }

            group.addTask { @MainActor in
                do {
                    self.weeklyProgressReport = try await APIClient.shared.getWeeklyProgressReport()
                } catch {
                    self.recordLoadError("weekly report", error)
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

        // Schedule local notifications based on loaded data
        scheduleLocalNotifications()

        // Load HealthKit data after main data
        await loadHealthKitData()
    }

    /// Record a per-endpoint load error so `HomeView` can show a banner.
    /// Keeps the existing DEBUG log for parity with prior behavior.
    private func recordLoadError(_ endpointName: String, _ error: Error) {
        #if DEBUG
        print("DEBUG: Failed to load \(endpointName): \(error)")
        #endif
        dataLoadErrors[endpointName] = error.localizedDescription
    }

    private func scheduleLocalNotifications() {
        let nm = NotificationManager.shared

        // Schedule streak-at-risk if user has an active streak
        if let streak = userProgress?.currentStreak, streak > 0 {
            // Only schedule if no workout logged today
            let hasWorkoutToday: Bool
            if let recent = recentWorkout?.date {
                let recentDate = recent.parseISO8601Date() ?? Date.distantPast
                hasWorkoutToday = Calendar.current.isDateInToday(recentDate)
            } else {
                hasWorkoutToday = false
            }

            if !hasWorkoutToday {
                nm.scheduleStreakAtRiskNotification(currentStreak: streak)
            } else {
                nm.cancelStreakReminder()
            }
        }

        // Schedule daily quest reset notification
        nm.scheduleQuestResetNotification()

        // Schedule mission expiring if mission is active
        if let mission = currentMission?.mission {
            if let weekEnd = mission.weekEnd.parseISO8601Date() {
                nm.scheduleMissionExpiringNotification(weekEnd: weekEnd)
            }
        }
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
            #if DEBUG
            print("DEBUG: Failed to accept mission: \(error)")
            #endif
            self.error = error.localizedDescription
        }
    }

    func declineMission(missionId: String) async {
        do {
            let _ = try await APIClient.shared.declineMission(id: missionId)
            // Reload mission data
            self.currentMission = try await APIClient.shared.getCurrentMission()
        } catch {
            #if DEBUG
            print("DEBUG: Failed to decline mission: \(error)")
            #endif
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
            #if DEBUG
            print("DEBUG: Failed to load goal for edit: \(error)")
            #endif
            self.error = error.localizedDescription
        }
    }

    func abandonGoal() async {
        guard let goalId = currentMission?.goal?.id else {
            #if DEBUG
            print("DEBUG: No goal to abandon")
            #endif
            return
        }

        do {
            try await APIClient.shared.deleteGoal(id: goalId)
            // Reload mission data (should now show empty state)
            self.currentMission = try await APIClient.shared.getCurrentMission()
            // Also reload quests
            self.dailyQuests = try await APIClient.shared.getDailyQuests()
        } catch {
            #if DEBUG
            print("DEBUG: Failed to abandon goal: \(error)")
            #endif
            self.error = error.localizedDescription
        }
    }

    /// Delete a specific goal by ID (used by GoalsListSheet swipe-to-delete)
    func deleteGoal(id: String) async {
        do {
            try await APIClient.shared.deleteGoal(id: id)
            // Reload mission data
            self.currentMission = try await APIClient.shared.getCurrentMission()
            // Also reload quests
            self.dailyQuests = try await APIClient.shared.getDailyQuests()
        } catch {
            #if DEBUG
            print("DEBUG: Failed to delete goal: \(error)")
            #endif
            self.error = error.localizedDescription
        }
    }

    /// Delete all goals (used by GoalsListSheet menu)
    func deleteAllGoals() async {
        guard let goals = currentMission?.goals else { return }

        for goal in goals {
            do {
                try await APIClient.shared.deleteGoal(id: goal.id)
            } catch {
                #if DEBUG
                print("DEBUG: Failed to delete goal \(goal.id): \(error)")
                #endif
            }
        }

        // Reload mission data after all deletions
        do {
            self.currentMission = try await APIClient.shared.getCurrentMission()
            self.dailyQuests = try await APIClient.shared.getDailyQuests()
        } catch {
            #if DEBUG
            print("DEBUG: Failed to reload data after deleting all goals: \(error)")
            #endif
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
