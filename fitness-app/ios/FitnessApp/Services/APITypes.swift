import Foundation

// MARK: - Auth

struct AuthResponse: Decodable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case tokenType = "token_type"
    }
}

// MARK: - Profile

struct ProfileResponse: Decodable {
    let id: String
    let userId: String?
    let email: String?
    let username: String?
    let age: Int?
    let sex: String?
    let bodyweightLb: Double?
    let heightInches: Double?
    let trainingExperience: String?
    let preferredUnit: String?
    let e1rmFormula: String?
    let createdAt: String?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, age, sex, email, username
        case userId = "user_id"
        case bodyweightLb = "bodyweight_lb"
        case heightInches = "height_inches"
        case trainingExperience = "training_experience"
        case preferredUnit = "preferred_unit"
        case e1rmFormula = "e1rm_formula"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct ProfileUpdate: Encodable {
    var age: Int?
    var sex: String?  // Must be "M" or "F"
    var bodyweightLb: Double?
    var heightInches: Double?
    var trainingExperience: String?
    var preferredUnit: String?
    var e1rmFormula: String?

    enum CodingKeys: String, CodingKey {
        case age, sex
        case bodyweightLb = "bodyweight_lb"
        case heightInches = "height_inches"
        case trainingExperience = "training_experience"
        case preferredUnit = "preferred_unit"
        case e1rmFormula = "e1rm_formula"
    }
}

// MARK: - Username

struct UsernameUpdate: Encodable {
    let username: String
}

struct UsernameCheckResponse: Decodable {
    let username: String
    let available: Bool
}

struct UserPublicResponse: Decodable, Identifiable {
    let id: String
    let username: String
    let rank: String
    let level: Int
}

// MARK: - Exercise

struct ExerciseResponse: Decodable, Identifiable {
    let id: String
    let name: String
    let canonicalId: String?
    let category: String?
    let primaryMuscle: String?
    let secondaryMuscles: [String]?
    let isCustom: Bool?

    enum CodingKeys: String, CodingKey {
        case id, name, category
        case canonicalId = "canonical_id"
        case primaryMuscle = "primary_muscle"
        case secondaryMuscles = "secondary_muscles"
        case isCustom = "is_custom"
    }
}

// MARK: - Workout

struct WorkoutCreate: Encodable {
    let date: String
    let durationMinutes: Int?
    let sessionRpe: Int?
    let notes: String?
    let exercises: [WorkoutExerciseCreate]

    enum CodingKeys: String, CodingKey {
        case date, notes, exercises
        case durationMinutes = "duration_minutes"
        case sessionRpe = "session_rpe"
    }
}

struct WorkoutExerciseCreate: Encodable {
    let exerciseId: String
    let orderIndex: Int
    let sets: [SetCreate]

    enum CodingKeys: String, CodingKey {
        case sets
        case exerciseId = "exercise_id"
        case orderIndex = "order_index"
    }
}

struct SetCreate: Encodable {
    let weight: Double
    let weightUnit: String
    let reps: Int
    let rpe: Int?
    let rir: Int?
    let setNumber: Int

    enum CodingKeys: String, CodingKey {
        case weight, reps, rpe, rir
        case weightUnit = "weight_unit"
        case setNumber = "set_number"
    }
}

struct WorkoutSummaryResponse: Decodable, Identifiable {
    let id: String
    let userId: String
    let date: String
    let durationMinutes: Int?
    let sessionRpe: Int?
    let notes: String?
    let exerciseCount: Int
    let totalSets: Int
    let exerciseNames: [String]?
    let createdAt: String
    let updatedAt: String
    // WHOOP activity fields
    let isWhoopActivity: Bool?
    let activityType: String?
    let strain: Double?
    let calories: Int?

    enum CodingKeys: String, CodingKey {
        case id, date, notes, strain, calories
        case userId = "user_id"
        case durationMinutes = "duration_minutes"
        case sessionRpe = "session_rpe"
        case exerciseCount = "exercise_count"
        case totalSets = "total_sets"
        case exerciseNames = "exercise_names"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case isWhoopActivity = "is_whoop_activity"
        case activityType = "activity_type"
    }
}

struct WorkoutResponse: Decodable, Identifiable {
    let id: String
    let userId: String
    let date: String
    let durationMinutes: Int?
    let sessionRpe: Int?
    let notes: String?
    let exercises: [WorkoutExerciseResponse]
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, date, notes, exercises
        case userId = "user_id"
        case durationMinutes = "duration_minutes"
        case sessionRpe = "session_rpe"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct WorkoutExerciseResponse: Decodable, Identifiable {
    let id: String
    let exerciseId: String
    let exerciseName: String
    let orderIndex: Int
    let sets: [SetResponse]
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, sets
        case exerciseId = "exercise_id"
        case exerciseName = "exercise_name"
        case orderIndex = "order_index"
        case createdAt = "created_at"
    }
}

struct SetResponse: Decodable, Identifiable {
    let id: String
    let weight: Double
    let weightUnit: String
    let reps: Int
    let rpe: Int?
    let rir: Int?
    let setNumber: Int
    let e1rm: Double?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, weight, reps, rpe, rir, e1rm
        case weightUnit = "weight_unit"
        case setNumber = "set_number"
        case createdAt = "created_at"
    }
}

// MARK: - Bodyweight

struct BodyweightCreate: Encodable {
    let date: String
    let weight: Double
    let weightUnit: String
    let source: String?

    enum CodingKeys: String, CodingKey {
        case date, weight, source
        case weightUnit = "weight_unit"
    }
}

struct BodyweightResponse: Decodable, Identifiable {
    let id: String
    let userId: String
    let date: String
    let weightLb: Double
    let weightDisplay: Double
    let weightUnit: String
    let source: String
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, date, source
        case userId = "user_id"
        case weightLb = "weight_lb"
        case weightDisplay = "weight_display"
        case weightUnit = "weight_unit"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct BodyweightHistoryResponse: Decodable {
    let entries: [BodyweightResponse]
    let rollingAverage7day: Double?
    let rollingAverage14day: Double?
    let trend: String
    let trendRatePerWeek: Double?
    let isPlateau: Bool
    let minWeight: Double?
    let maxWeight: Double?
    let totalEntries: Int

    enum CodingKeys: String, CodingKey {
        case entries, trend
        case rollingAverage7day = "rolling_average_7day"
        case rollingAverage14day = "rolling_average_14day"
        case trendRatePerWeek = "trend_rate_per_week"
        case isPlateau = "is_plateau"
        case minWeight = "min_weight"
        case maxWeight = "max_weight"
        case totalEntries = "total_entries"
    }
}

// MARK: - Analytics

struct TrendResponse: Decodable {
    let exerciseId: String
    let exerciseName: String
    let timeRange: String
    let dataPoints: [DataPoint]
    let weeklyBestE1rm: [DataPoint]
    let rollingAverage4w: Double?
    let currentE1rm: Double?
    let trendDirection: String
    let percentChange: Double?
    let totalWorkouts: Int

    enum CodingKeys: String, CodingKey {
        case exerciseId = "exercise_id"
        case exerciseName = "exercise_name"
        case timeRange = "time_range"
        case dataPoints = "data_points"
        case weeklyBestE1rm = "weekly_best_e1rm"
        case rollingAverage4w = "rolling_average_4w"
        case currentE1rm = "current_e1rm"
        case trendDirection = "trend_direction"
        case percentChange = "percent_change"
        case totalWorkouts = "total_workouts"
    }
}

struct SetDetail: Decodable {
    let weight: Double
    let reps: Int
    let e1rm: Double
}

struct DataPoint: Decodable, Identifiable {
    let date: String
    let value: Double
    let workoutId: String?  // ID of the workout with best e1RM on this date
    let sets: [SetDetail]?  // Populated when include_sets=true

    var id: String { date }

    enum CodingKeys: String, CodingKey {
        case date, value, sets
        case workoutId = "workout_id"
    }
}

struct PercentilesResponse: Decodable {
    let userBodyweight: Double?
    let userAge: Int?
    let userSex: String?
    let exercises: [ExercisePercentile]

    enum CodingKeys: String, CodingKey {
        case exercises
        case userBodyweight = "user_bodyweight"
        case userAge = "user_age"
        case userSex = "user_sex"
    }
}

struct ExercisePercentile: Decodable, Identifiable {
    let exerciseId: String
    let exerciseName: String
    let currentE1rm: Double?
    let bodyweightMultiplier: Double?
    let percentile: Int?
    let classification: String

    var id: String { exerciseId }

    enum CodingKeys: String, CodingKey {
        case percentile, classification
        case exerciseId = "exercise_id"
        case exerciseName = "exercise_name"
        case currentE1rm = "current_e1rm"
        case bodyweightMultiplier = "bodyweight_multiplier"
    }
}

struct PRListResponse: Decodable {
    let prs: [PRResponse]
    let totalCount: Int

    enum CodingKeys: String, CodingKey {
        case prs
        case totalCount = "total_count"
    }
}

struct PRResponse: Decodable, Identifiable {
    let id: String
    let exerciseId: String
    let exerciseName: String
    let canonicalId: String?
    let canonicalExerciseName: String?
    let prType: String
    let value: Double?
    let reps: Int?
    let weight: Double?
    let achievedAt: String
    let createdAt: String

    /// Returns the canonical name if available, otherwise the exercise name
    var displayName: String {
        canonicalExerciseName ?? exerciseName
    }

    enum CodingKeys: String, CodingKey {
        case id, value, reps, weight
        case exerciseId = "exercise_id"
        case exerciseName = "exercise_name"
        case canonicalId = "canonical_id"
        case canonicalExerciseName = "canonical_exercise_name"
        case prType = "pr_type"
        case achievedAt = "achieved_at"
        case createdAt = "created_at"
    }
}

struct InsightsResponse: Decodable {
    let insights: [InsightResponse]
    let generatedAt: String

    enum CodingKeys: String, CodingKey {
        case insights
        case generatedAt = "generated_at"
    }
}

struct InsightResponse: Decodable, Identifiable {
    let type: String
    let priority: String
    let title: String
    let description: String
    let exerciseId: String?
    let exerciseName: String?

    var id: String { title + type }

    enum CodingKeys: String, CodingKey {
        case type, priority, title, description
        case exerciseId = "exercise_id"
        case exerciseName = "exercise_name"
    }
}

struct WeeklyReviewResponse: Decodable {
    let weekStart: String
    let weekEnd: String
    let totalWorkouts: Int
    let totalSets: Int
    let totalVolume: Double
    let prsAchieved: [PRResponse]
    let volumeChangePercent: Double?
    let fastestImprovingExercise: String?
    let fastestImprovingPercent: Double?
    let regressingExercises: [String]
    let insights: [InsightResponse]

    enum CodingKeys: String, CodingKey {
        case insights
        case weekStart = "week_start"
        case weekEnd = "week_end"
        case totalWorkouts = "total_workouts"
        case totalSets = "total_sets"
        case totalVolume = "total_volume"
        case prsAchieved = "prs_achieved"
        case volumeChangePercent = "volume_change_percent"
        case fastestImprovingExercise = "fastest_improving_exercise"
        case fastestImprovingPercent = "fastest_improving_percent"
        case regressingExercises = "regressing_exercises"
    }
}

// MARK: - Sync

struct SyncRequest: Encodable {
    let workouts: [WorkoutCreate]
    let bodyweightEntries: [BodyweightCreate]
    let profile: ProfileUpdate?
    let clientTimestamp: String
    let deviceId: String?

    enum CodingKeys: String, CodingKey {
        case workouts, profile
        case bodyweightEntries = "bodyweight_entries"
        case clientTimestamp = "client_timestamp"
        case deviceId = "device_id"
    }
}

struct SyncResponse: Decodable {
    let success: Bool
    let syncedAt: String
    let workoutsSynced: Int
    let bodyweightEntriesSynced: Int
    let profileSynced: Bool

    enum CodingKeys: String, CodingKey {
        case success
        case syncedAt = "synced_at"
        case workoutsSynced = "workouts_synced"
        case bodyweightEntriesSynced = "bodyweight_entries_synced"
        case profileSynced = "profile_synced"
    }
}

struct SyncStatusResponse: Decodable {
    let lastSyncAt: String?
    let pendingWorkouts: Int
    let pendingBodyweightEntries: Int
    let isSynced: Bool

    enum CodingKeys: String, CodingKey {
        case lastSyncAt = "last_sync_at"
        case pendingWorkouts = "pending_workouts"
        case pendingBodyweightEntries = "pending_bodyweight_entries"
        case isSynced = "is_synced"
    }
}

// MARK: - Progress & XP

struct UserProgressResponse: Decodable {
    let totalXp: Int
    let level: Int
    let rank: String
    let currentStreak: Int
    let longestStreak: Int
    let totalWorkouts: Int
    let totalVolumeLb: Int
    let totalPrs: Int
    let xpToNextLevel: Int
    let levelProgress: Double
    let lastWorkoutDate: String?

    enum CodingKeys: String, CodingKey {
        case level, rank
        case totalXp = "total_xp"
        case currentStreak = "current_streak"
        case longestStreak = "longest_streak"
        case totalWorkouts = "total_workouts"
        case totalVolumeLb = "total_volume_lb"
        case totalPrs = "total_prs"
        case xpToNextLevel = "xp_to_next_level"
        case levelProgress = "level_progress"
        case lastWorkoutDate = "last_workout_date"
    }
}

struct AchievementResponse: Decodable, Identifiable {
    let id: String
    let name: String
    let description: String
    let category: String
    let icon: String
    let xpReward: Int
    let rarity: String
    let unlocked: Bool
    let unlockedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, name, description, category, icon, rarity, unlocked
        case xpReward = "xp_reward"
        case unlockedAt = "unlocked_at"
    }
}

struct AchievementsListResponse: Decodable {
    let achievements: [AchievementResponse]
    let totalUnlocked: Int
    let totalAvailable: Int

    enum CodingKeys: String, CodingKey {
        case achievements
        case totalUnlocked = "total_unlocked"
        case totalAvailable = "total_available"
    }
}

// MARK: - Achievement Extensions

extension AchievementResponse {
    /// Human-readable description of unlock requirements based on achievement ID
    var requirementDescription: String {
        // Parse achievement ID to generate requirements
        let id = self.id.lowercased()

        // Workout count achievements
        if id.contains("first_workout") { return "Complete your first workout" }
        if id.contains("workouts_10") { return "Complete 10 workouts" }
        if id.contains("workouts_25") { return "Complete 25 workouts" }
        if id.contains("workouts_50") { return "Complete 50 workouts" }
        if id.contains("workouts_100") { return "Complete 100 workouts" }
        if id.contains("workouts_250") { return "Complete 250 workouts" }
        if id.contains("workouts_500") { return "Complete 500 workouts" }

        // Streak achievements
        if id.contains("streak_3") { return "Maintain a 3-day workout streak" }
        if id.contains("streak_7") { return "Maintain a 7-day workout streak" }
        if id.contains("streak_14") { return "Maintain a 14-day workout streak" }
        if id.contains("streak_30") { return "Maintain a 30-day workout streak" }
        if id.contains("streak_60") { return "Maintain a 60-day workout streak" }
        if id.contains("streak_90") { return "Maintain a 90-day workout streak" }
        if id.contains("streak_180") { return "Maintain a 180-day workout streak" }
        if id.contains("streak_365") { return "Maintain a 365-day workout streak" }

        // PR achievements
        if id.contains("first_pr") { return "Set your first personal record" }
        if id.contains("prs_10") { return "Set 10 personal records" }
        if id.contains("prs_25") { return "Set 25 personal records" }
        if id.contains("prs_50") { return "Set 50 personal records" }
        if id.contains("prs_100") { return "Set 100 personal records" }

        // Volume achievements
        if id.contains("volume_10k") { return "Lift 10,000 total lbs" }
        if id.contains("volume_50k") { return "Lift 50,000 total lbs" }
        if id.contains("volume_100k") { return "Lift 100,000 total lbs" }
        if id.contains("volume_500k") { return "Lift 500,000 total lbs" }
        if id.contains("volume_1m") { return "Lift 1,000,000 total lbs" }

        // Level achievements
        if id.contains("level_5") { return "Reach Level 5" }
        if id.contains("level_10") { return "Reach Level 10" }
        if id.contains("level_25") { return "Reach Level 25" }
        if id.contains("level_50") { return "Reach Level 50" }
        if id.contains("level_100") { return "Reach Level 100" }

        // Rank achievements
        if id.contains("rank_d") { return "Achieve D-Rank Hunter status" }
        if id.contains("rank_c") { return "Achieve C-Rank Hunter status" }
        if id.contains("rank_b") { return "Achieve B-Rank Hunter status" }
        if id.contains("rank_a") { return "Achieve A-Rank Hunter status" }
        if id.contains("rank_s") { return "Achieve S-Rank Hunter status" }

        // Quest achievements
        if id.contains("quests_complete") { return "Complete daily quests" }
        if id.contains("dungeon") { return "Complete dungeon challenges" }

        // Default fallback using the description
        return description
    }
}

struct RecentAchievementsResponse: Decodable {
    let achievements: [AchievementResponse]
}

// MARK: - Workout Create Response (with XP)

struct WorkoutCreateResponse: Decodable, Identifiable {
    let workout: WorkoutResponse
    let xpEarned: Int
    let xpBreakdown: [String: Int]
    let totalXp: Int
    let level: Int
    let leveledUp: Bool
    let newLevel: Int?
    let rank: String
    let rankChanged: Bool
    let newRank: String?
    let currentStreak: Int
    let achievementsUnlocked: [AchievementUnlockedResponse]
    let prsAchieved: [PRAchievedResponse]
    // Dungeon system
    let dungeonSpawned: DungeonSpawnedResponse?
    let dungeonProgress: DungeonProgressResponse?

    var id: String { workout.id }

    enum CodingKeys: String, CodingKey {
        case workout, level, rank
        case xpEarned = "xp_earned"
        case xpBreakdown = "xp_breakdown"
        case totalXp = "total_xp"
        case leveledUp = "leveled_up"
        case newLevel = "new_level"
        case rankChanged = "rank_changed"
        case newRank = "new_rank"
        case currentStreak = "current_streak"
        case achievementsUnlocked = "achievements_unlocked"
        case prsAchieved = "prs_achieved"
        case dungeonSpawned = "dungeon_spawned"
        case dungeonProgress = "dungeon_progress"
    }
}

struct AchievementUnlockedResponse: Decodable, Identifiable {
    let id: String
    let name: String
    let description: String
    let icon: String
    let xpReward: Int
    let rarity: String

    enum CodingKeys: String, CodingKey {
        case id, name, description, icon, rarity
        case xpReward = "xp_reward"
    }
}

struct PRAchievedResponse: Decodable, Identifiable {
    let exerciseName: String
    let prType: String  // "e1rm" or "rep_pr"
    let value: String   // "225 lb" or "315 lb x 5"
    let xpEarned: Int

    var id: String { "\(exerciseName)-\(prType)-\(value)" }

    enum CodingKeys: String, CodingKey {
        case prType = "pr_type"
        case value
        case exerciseName = "exercise_name"
        case xpEarned = "xp_earned"
    }
}

// MARK: - Quests

struct QuestResponse: Decodable, Identifiable {
    let id: String
    let questId: String
    let name: String
    let description: String
    let questType: String
    let targetValue: Int
    let xpReward: Int
    let progress: Int
    let isCompleted: Bool
    let isClaimed: Bool
    let difficulty: String

    enum CodingKeys: String, CodingKey {
        case id, name, description, progress, difficulty
        case questId = "quest_id"
        case questType = "quest_type"
        case targetValue = "target_value"
        case xpReward = "xp_reward"
        case isCompleted = "is_completed"
        case isClaimed = "is_claimed"
    }
}

struct DailyQuestsResponse: Decodable {
    let quests: [QuestResponse]
    let refreshAt: String
    let completedCount: Int
    let totalCount: Int

    enum CodingKeys: String, CodingKey {
        case quests
        case refreshAt = "refresh_at"
        case completedCount = "completed_count"
        case totalCount = "total_count"
    }
}

struct QuestClaimResponse: Decodable {
    let success: Bool
    let xpEarned: Int
    let totalXp: Int
    let level: Int
    let leveledUp: Bool
    let newLevel: Int?
    let rank: String
    let rankChanged: Bool
    let newRank: String?

    enum CodingKeys: String, CodingKey {
        case success, level, rank
        case xpEarned = "xp_earned"
        case totalXp = "total_xp"
        case leveledUp = "leveled_up"
        case newLevel = "new_level"
        case rankChanged = "rank_changed"
        case newRank = "new_rank"
    }
}

// MARK: - Activity (HealthKit Sync)

enum ActivitySource: String, Codable {
    case appleFitness = "apple_fitness"
    case whoop = "whoop"
    case garmin = "garmin"
    case fitbit = "fitbit"
    case manual = "manual"
}

struct ActivityCreate: Encodable {
    let date: String
    let source: String
    let steps: Int?
    let activeCalories: Int?
    let totalCalories: Int?
    let activeMinutes: Int?
    let exerciseMinutes: Int?
    let standHours: Int?
    let moveCalories: Int?
    let strain: Double?
    let recoveryScore: Int?
    let hrv: Int?
    let restingHeartRate: Int?
    let sleepHours: Double?

    enum CodingKeys: String, CodingKey {
        case date, source, steps, strain, hrv
        case activeCalories = "active_calories"
        case totalCalories = "total_calories"
        case activeMinutes = "active_minutes"
        case exerciseMinutes = "exercise_minutes"
        case standHours = "stand_hours"
        case moveCalories = "move_calories"
        case recoveryScore = "recovery_score"
        case restingHeartRate = "resting_heart_rate"
        case sleepHours = "sleep_hours"
    }
}

struct ActivityResponse: Decodable, Identifiable {
    let id: String
    let userId: String
    let date: String
    let source: String
    let steps: Int?
    let activeCalories: Int?
    let totalCalories: Int?
    let activeMinutes: Int?
    let exerciseMinutes: Int?
    let standHours: Int?
    let moveCalories: Int?
    let strain: Double?
    let recoveryScore: Int?
    let hrv: Int?
    let restingHeartRate: Int?
    let sleepHours: Double?
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, date, source, steps, strain, hrv
        case userId = "user_id"
        case activeCalories = "active_calories"
        case totalCalories = "total_calories"
        case activeMinutes = "active_minutes"
        case exerciseMinutes = "exercise_minutes"
        case standHours = "stand_hours"
        case moveCalories = "move_calories"
        case recoveryScore = "recovery_score"
        case restingHeartRate = "resting_heart_rate"
        case sleepHours = "sleep_hours"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct ActivityHistoryResponse: Decodable {
    let entries: [ActivityResponse]
    let total: Int
    let hasMore: Bool

    enum CodingKeys: String, CodingKey {
        case entries, total
        case hasMore = "has_more"
    }
}

struct LastSyncResponse: Decodable {
    let lastSyncedDate: String?
    let source: String

    enum CodingKeys: String, CodingKey {
        case source
        case lastSyncedDate = "last_synced_date"
    }
}

// MARK: - Screenshot Processing

struct ExtractedSet: Decodable {
    let weightLb: Double
    let reps: Int
    let sets: Int
    let isWarmup: Bool

    enum CodingKeys: String, CodingKey {
        case reps, sets
        case weightLb = "weight_lb"
        case isWarmup = "is_warmup"
    }
}

struct ExtractedExercise: Decodable, Identifiable {
    let name: String
    let equipment: String?
    let variation: String?
    let sets: [ExtractedSet]
    let totalReps: Int?
    let totalVolumeLb: Double?
    let matchedExerciseId: String?
    let matchedExerciseName: String?
    let matchConfidence: Int?

    var id: String { name + (matchedExerciseId ?? UUID().uuidString) }

    enum CodingKeys: String, CodingKey {
        case name, equipment, variation, sets
        case totalReps = "total_reps"
        case totalVolumeLb = "total_volume_lb"
        case matchedExerciseId = "matched_exercise_id"
        case matchedExerciseName = "matched_exercise_name"
        case matchConfidence = "match_confidence"
    }
}

struct ExtractedSummary: Decodable {
    let tonnageLb: Double?
    let totalReps: Int?

    enum CodingKeys: String, CodingKey {
        case tonnageLb = "tonnage_lb"
        case totalReps = "total_reps"
    }
}

struct HeartRateZone: Decodable {
    let zone: Int?
    let bpmRange: String?
    let percentage: Double?
    let duration: String?

    enum CodingKeys: String, CodingKey {
        case zone, percentage, duration
        case bpmRange = "bpm_range"
    }
}

struct ScreenshotProcessResponse: Decodable {
    // Common fields
    let screenshotType: String?
    let sessionDate: String?
    let sessionName: String?
    let durationMinutes: Int?
    let summary: ExtractedSummary?
    let exercises: [ExtractedExercise]
    let processingConfidence: String
    let workoutId: String?
    let workoutSaved: Bool
    let activityId: String?
    let activitySaved: Bool

    // WHOOP/Activity-specific fields
    let activityType: String?
    let timeRange: String?
    let strain: Double?
    let steps: Int?
    let calories: Int?
    let avgHr: Int?
    let maxHr: Int?
    let source: String?
    let heartRateZones: [HeartRateZone]?

    // Helper computed property
    var isWhoopActivity: Bool {
        screenshotType == "whoop_activity"
    }

    enum CodingKeys: String, CodingKey {
        case exercises, summary, strain, steps, calories, source
        case screenshotType = "screenshot_type"
        case sessionDate = "session_date"
        case sessionName = "session_name"
        case durationMinutes = "duration_minutes"
        case processingConfidence = "processing_confidence"
        case workoutId = "workout_id"
        case workoutSaved = "workout_saved"
        case activityId = "activity_id"
        case activitySaved = "activity_saved"
        case activityType = "activity_type"
        case timeRange = "time_range"
        case avgHr = "avg_hr"
        case maxHr = "max_hr"
        case heartRateZones = "heart_rate_zones"
    }
}

struct ScreenshotBatchResponse: Decodable {
    let screenshotsProcessed: Int
    let screenshotType: String?
    let sessionDate: String?
    let sessionName: String?
    let durationMinutes: Int?
    let summary: ExtractedSummary?
    let exercises: [ExtractedExercise]
    let processingConfidence: String
    let workoutId: String?
    let workoutSaved: Bool
    let activityId: String?
    let activitySaved: Bool

    // WHOOP/Activity-specific fields
    let activityType: String?
    let timeRange: String?
    let strain: Double?
    let steps: Int?
    let calories: Int?
    let avgHr: Int?
    let maxHr: Int?
    let source: String?
    let heartRateZones: [HeartRateZone]?

    // Helper computed property
    var isWhoopActivity: Bool {
        screenshotType == "whoop_activity"
    }

    enum CodingKeys: String, CodingKey {
        case exercises, summary, strain, steps, calories, source
        case screenshotsProcessed = "screenshots_processed"
        case screenshotType = "screenshot_type"
        case sessionDate = "session_date"
        case sessionName = "session_name"
        case durationMinutes = "duration_minutes"
        case processingConfidence = "processing_confidence"
        case workoutId = "workout_id"
        case workoutSaved = "workout_saved"
        case activityId = "activity_id"
        case activitySaved = "activity_saved"
        case activityType = "activity_type"
        case timeRange = "time_range"
        case avgHr = "avg_hr"
        case maxHr = "max_hr"
        case heartRateZones = "heart_rate_zones"
    }
}

// MARK: - Cooldowns

struct AffectedExercise: Decodable, Identifiable {
    let exerciseId: String
    let exerciseName: String
    let workoutDate: String
    let fatigueType: String  // "primary" or "secondary"

    var id: String { exerciseId + workoutDate }

    enum CodingKeys: String, CodingKey {
        case exerciseId = "exercise_id"
        case exerciseName = "exercise_name"
        case workoutDate = "workout_date"
        case fatigueType = "fatigue_type"
    }
}

/// Detailed breakdown of how cooldown time was calculated
struct FatigueBreakdown: Decodable {
    let baseCooldownHours: Int        // Base time for muscle group (36-72h)
    let totalSets: Int                // Raw set count (includes secondary hits)
    let effectiveSets: Double         // Weighted sets (primary=1.0, secondary=0.5)
    let avgIntensityFactor: Double    // Average intensity factor across sets
    let volumeMultiplier: Double      // Volume-based multiplier (1.0-2.0)
    let ageModifier: Double           // Age-based multiplier (1.0-1.5)
    let finalCooldownHours: Int       // Calculated cooldown after all factors

    enum CodingKeys: String, CodingKey {
        case baseCooldownHours = "base_cooldown_hours"
        case totalSets = "total_sets"
        case effectiveSets = "effective_sets"
        case avgIntensityFactor = "avg_intensity_factor"
        case volumeMultiplier = "volume_multiplier"
        case ageModifier = "age_modifier"
        case finalCooldownHours = "final_cooldown_hours"
    }
}

struct MuscleCooldownStatus: Decodable, Identifiable {
    let muscleGroup: String
    let status: String
    let cooldownPercent: Double
    let hoursRemaining: Int
    let lastTrained: String
    let affectedExercises: [AffectedExercise]
    let fatigueBreakdown: FatigueBreakdown?  // Detailed calculation breakdown

    var id: String { muscleGroup }

    /// Display name for the muscle group
    var displayName: String {
        switch muscleGroup {
        case "chest": return "Chest"
        case "quads": return "Quads"
        case "hamstrings": return "Hamstrings"
        case "biceps": return "Biceps"
        case "triceps": return "Triceps"
        case "shoulders": return "Shoulders"
        default: return muscleGroup.capitalized
        }
    }

    /// Fantasy name for the muscle group (Solo Leveling theme)
    var fantasyName: String {
        switch muscleGroup {
        case "chest": return "Titan's Core"
        case "quads": return "Earth Pillars"
        case "hamstrings": return "Shadow Tendons"
        case "biceps": return "Iron Coils"
        case "triceps": return "Storm Arms"
        case "shoulders": return "Atlas Frame"
        default: return muscleGroup.capitalized
        }
    }

    /// Formatted time remaining
    var timeRemainingFormatted: String {
        if hoursRemaining >= 24 {
            let days = hoursRemaining / 24
            let hours = hoursRemaining % 24
            if hours > 0 {
                return "\(days)d \(hours)h"
            }
            return "\(days)d"
        }
        return "\(hoursRemaining)h"
    }

    enum CodingKeys: String, CodingKey {
        case status
        case muscleGroup = "muscle_group"
        case cooldownPercent = "cooldown_percent"
        case hoursRemaining = "hours_remaining"
        case lastTrained = "last_trained"
        case affectedExercises = "affected_exercises"
        case fatigueBreakdown = "fatigue_breakdown"
    }
}

struct CooldownResponse: Decodable {
    let musclesCooling: [MuscleCooldownStatus]
    let generatedAt: String
    let ageModifier: Double

    enum CodingKeys: String, CodingKey {
        case musclesCooling = "muscles_cooling"
        case generatedAt = "generated_at"
        case ageModifier = "age_modifier"
    }
}

// MARK: - Dungeons

struct DungeonSpawnedResponse: Decodable {
    let id: String
    let dungeonId: String
    let name: String
    let rank: String
    let baseXpReward: Int
    let isStretchDungeon: Bool
    let stretchBonusPercent: Int?
    let timeRemainingSeconds: Int
    let message: String

    enum CodingKeys: String, CodingKey {
        case id, name, rank, message
        case dungeonId = "dungeon_id"
        case baseXpReward = "base_xp_reward"
        case isStretchDungeon = "is_stretch_dungeon"
        case stretchBonusPercent = "stretch_bonus_percent"
        case timeRemainingSeconds = "time_remaining_seconds"
    }
}

struct DungeonProgressResponse: Decodable {
    let dungeonsProgressed: [String]
    let dungeonsCompleted: [String]
    let objectivesCompleted: [String]

    enum CodingKeys: String, CodingKey {
        case dungeonsProgressed = "dungeons_progressed"
        case dungeonsCompleted = "dungeons_completed"
        case objectivesCompleted = "objectives_completed"
    }
}

struct DungeonObjectiveResponse: Decodable, Identifiable {
    let id: String
    let objectiveId: String
    let name: String
    let description: String
    let objectiveType: String
    let targetValue: Int
    let progress: Int
    let isCompleted: Bool
    let isRequired: Bool
    let xpBonus: Int
    let orderIndex: Int

    enum CodingKeys: String, CodingKey {
        case id, name, description, progress
        case objectiveId = "objective_id"
        case objectiveType = "objective_type"
        case targetValue = "target_value"
        case isCompleted = "is_completed"
        case isRequired = "is_required"
        case xpBonus = "xp_bonus"
        case orderIndex = "order_index"
    }
}

struct DungeonResponse: Decodable, Identifiable {
    let id: String
    let dungeonId: String
    let name: String
    let description: String
    let rank: String
    let status: String
    let baseXpReward: Int
    let totalXpReward: Int
    let isStretchDungeon: Bool
    let stretchType: String?
    let stretchBonusPercent: Int?
    let spawnedAt: String
    let expiresAt: String
    let acceptedAt: String?
    let completedAt: String?
    let timeRemainingSeconds: Int
    let durationHours: Int
    let objectives: [DungeonObjectiveResponse]
    let requiredObjectivesComplete: Int
    let totalRequiredObjectives: Int
    let bonusObjectivesComplete: Int
    let totalBonusObjectives: Int
    let isBossDungeon: Bool
    let isEventDungeon: Bool

    /// Check if dungeon is urgent (less than 24 hours remaining)
    var isUrgent: Bool {
        timeRemainingSeconds < 86400
    }

    /// Formatted time remaining
    var timeRemainingFormatted: String {
        let hours = timeRemainingSeconds / 3600
        if hours >= 24 {
            let days = hours / 24
            return "\(days)d \(hours % 24)h"
        }
        return "\(hours)h"
    }

    enum CodingKeys: String, CodingKey {
        case id, name, description, rank, status, objectives
        case dungeonId = "dungeon_id"
        case baseXpReward = "base_xp_reward"
        case totalXpReward = "total_xp_reward"
        case isStretchDungeon = "is_stretch_dungeon"
        case stretchType = "stretch_type"
        case stretchBonusPercent = "stretch_bonus_percent"
        case spawnedAt = "spawned_at"
        case expiresAt = "expires_at"
        case acceptedAt = "accepted_at"
        case completedAt = "completed_at"
        case timeRemainingSeconds = "time_remaining_seconds"
        case durationHours = "duration_hours"
        case requiredObjectivesComplete = "required_objectives_complete"
        case totalRequiredObjectives = "total_required_objectives"
        case bonusObjectivesComplete = "bonus_objectives_complete"
        case totalBonusObjectives = "total_bonus_objectives"
        case isBossDungeon = "is_boss_dungeon"
        case isEventDungeon = "is_event_dungeon"
    }
}

struct DungeonSummaryResponse: Decodable, Identifiable {
    let id: String
    let dungeonId: String
    let name: String
    let rank: String
    let status: String
    let baseXpReward: Int
    let isStretchDungeon: Bool
    let stretchBonusPercent: Int?
    let timeRemainingSeconds: Int
    let requiredObjectivesComplete: Int
    let totalRequiredObjectives: Int
    let isBossDungeon: Bool

    /// Check if dungeon is urgent (less than 24 hours remaining)
    var isUrgent: Bool {
        timeRemainingSeconds < 86400
    }

    /// Formatted time remaining
    var timeRemainingFormatted: String {
        let hours = timeRemainingSeconds / 3600
        if hours >= 24 {
            let days = hours / 24
            return "\(days)d \(hours % 24)h"
        }
        return "\(hours)h"
    }

    enum CodingKeys: String, CodingKey {
        case id, name, rank, status
        case dungeonId = "dungeon_id"
        case baseXpReward = "base_xp_reward"
        case isStretchDungeon = "is_stretch_dungeon"
        case stretchBonusPercent = "stretch_bonus_percent"
        case timeRemainingSeconds = "time_remaining_seconds"
        case requiredObjectivesComplete = "required_objectives_complete"
        case totalRequiredObjectives = "total_required_objectives"
        case isBossDungeon = "is_boss_dungeon"
    }
}

struct DungeonsResponse: Decodable {
    let available: [DungeonSummaryResponse]
    let active: [DungeonSummaryResponse]
    let completedUnclaimed: [DungeonSummaryResponse]
    let userLevel: Int
    let userRank: String

    enum CodingKeys: String, CodingKey {
        case available, active
        case completedUnclaimed = "completed_unclaimed"
        case userLevel = "user_level"
        case userRank = "user_rank"
    }
}

struct DungeonAcceptResponse: Decodable {
    let success: Bool
    let dungeon: DungeonResponse
    let message: String
}

struct DungeonAbandonResponse: Decodable {
    let success: Bool
    let message: String
}

struct DungeonClaimResponse: Decodable {
    let success: Bool
    let xpEarned: Int
    let stretchBonusXp: Int
    let bonusObjectivesXp: Int
    let totalXp: Int
    let level: Int
    let leveledUp: Bool
    let newLevel: Int?
    let rank: String
    let rankChanged: Bool
    let newRank: String?

    enum CodingKeys: String, CodingKey {
        case success, level, rank
        case xpEarned = "xp_earned"
        case stretchBonusXp = "stretch_bonus_xp"
        case bonusObjectivesXp = "bonus_objectives_xp"
        case totalXp = "total_xp"
        case leveledUp = "leveled_up"
        case newLevel = "new_level"
        case rankChanged = "rank_changed"
        case newRank = "new_rank"
    }
}

struct DungeonHistoryResponse: Decodable {
    let dungeons: [DungeonSummaryResponse]
    let totalCompleted: Int
    let totalAbandoned: Int
    let totalExpired: Int

    enum CodingKeys: String, CodingKey {
        case dungeons
        case totalCompleted = "total_completed"
        case totalAbandoned = "total_abandoned"
        case totalExpired = "total_expired"
    }
}

// MARK: - Friends

struct FriendRequestResponse: Decodable, Identifiable {
    let id: String
    let senderId: String
    let senderUsername: String?
    let senderRank: String?
    let senderLevel: Int?
    let receiverId: String
    let receiverUsername: String?
    let receiverRank: String?
    let receiverLevel: Int?
    let status: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, status
        case senderId = "sender_id"
        case senderUsername = "sender_username"
        case senderRank = "sender_rank"
        case senderLevel = "sender_level"
        case receiverId = "receiver_id"
        case receiverUsername = "receiver_username"
        case receiverRank = "receiver_rank"
        case receiverLevel = "receiver_level"
        case createdAt = "created_at"
    }
}

struct FriendRequestsResponse: Decodable {
    let incoming: [FriendRequestResponse]
    let sent: [FriendRequestResponse]
}

struct FriendResponse: Decodable, Identifiable {
    let id: String
    let userId: String
    let friendId: String
    let friendUsername: String?
    let friendRank: String?
    let friendLevel: Int?
    let createdAt: String
    let lastWorkoutAt: String?

    /// Get initials for avatar
    var initials: String {
        guard let username = friendUsername, !username.isEmpty else {
            return "?"
        }
        let components = username.split(separator: " ")
        if components.count >= 2 {
            return String(components[0].prefix(1) + components[1].prefix(1)).uppercased()
        }
        return String(username.prefix(2)).uppercased()
    }

    /// Formatted last active time
    var lastActiveFormatted: String {
        guard let lastWorkout = lastWorkoutAt,
              let date = lastWorkout.parseISO8601Date() else {
            return "Never"
        }

        let now = Date()
        let interval = now.timeIntervalSince(date)
        let hours = Int(interval / 3600)
        let days = hours / 24

        if hours < 1 {
            return "Active now"
        } else if hours < 24 {
            return "\(hours)h ago"
        } else if days == 1 {
            return "Yesterday"
        } else if days < 7 {
            return "\(days)d ago"
        } else {
            let formatter = DateFormatter()
            formatter.dateFormat = "MMM d"
            return formatter.string(from: date)
        }
    }

    /// Check if friend is recently active (within 1 hour)
    var isRecentlyActive: Bool {
        guard let lastWorkout = lastWorkoutAt,
              let date = lastWorkout.parseISO8601Date() else {
            return false
        }
        return Date().timeIntervalSince(date) < 3600
    }

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case friendId = "friend_id"
        case friendUsername = "friend_username"
        case friendRank = "friend_rank"
        case friendLevel = "friend_level"
        case createdAt = "created_at"
        case lastWorkoutAt = "last_workout_at"
    }
}

struct RecentWorkoutSummary: Decodable, Identifiable {
    let id: String
    let date: String
    let exerciseCount: Int
    let exerciseNames: [String]
    let xpEarned: Int?

    enum CodingKeys: String, CodingKey {
        case id, date
        case exerciseCount = "exercise_count"
        case exerciseNames = "exercise_names"
        case xpEarned = "xp_earned"
    }
}

struct FriendProfileResponse: Decodable {
    let userId: String
    let username: String?
    let rank: String?
    let level: Int?
    let totalWorkouts: Int
    let currentStreak: Int
    let totalPrs: Int
    let recentWorkouts: [RecentWorkoutSummary]

    /// Get initials for avatar
    var initials: String {
        guard let username = username, !username.isEmpty else {
            return "?"
        }
        let components = username.split(separator: " ")
        if components.count >= 2 {
            return String(components[0].prefix(1) + components[1].prefix(1)).uppercased()
        }
        return String(username.prefix(2)).uppercased()
    }

    enum CodingKeys: String, CodingKey {
        case username, rank, level
        case userId = "user_id"
        case totalWorkouts = "total_workouts"
        case currentStreak = "current_streak"
        case totalPrs = "total_prs"
        case recentWorkouts = "recent_workouts"
    }
}
