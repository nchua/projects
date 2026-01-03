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
        case id, age, sex, email
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
    var trainingExperience: String?
    var preferredUnit: String?
    var e1rmFormula: String?

    enum CodingKeys: String, CodingKey {
        case age, sex
        case bodyweightLb = "bodyweight_lb"
        case trainingExperience = "training_experience"
        case preferredUnit = "preferred_unit"
        case e1rmFormula = "e1rm_formula"
    }
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
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, date, notes
        case userId = "user_id"
        case durationMinutes = "duration_minutes"
        case sessionRpe = "session_rpe"
        case exerciseCount = "exercise_count"
        case totalSets = "total_sets"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
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

struct DataPoint: Decodable, Identifiable {
    let date: String
    let value: Double

    var id: String { date }
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
    let prType: String
    let value: Double?
    let reps: Int?
    let weight: Double?
    let achievedAt: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, value, reps, weight
        case exerciseId = "exercise_id"
        case exerciseName = "exercise_name"
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

struct ScreenshotProcessResponse: Decodable {
    let sessionDate: String?
    let sessionName: String?
    let durationMinutes: Int?
    let summary: ExtractedSummary?
    let exercises: [ExtractedExercise]
    let processingConfidence: String

    enum CodingKeys: String, CodingKey {
        case exercises
        case sessionDate = "session_date"
        case sessionName = "session_name"
        case durationMinutes = "duration_minutes"
        case summary
        case processingConfidence = "processing_confidence"
    }
}
