import Foundation
import SwiftUI

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

// MARK: - Password Reset

struct PasswordResetRequest: Encodable {
    let email: String
}

struct PasswordResetVerify: Encodable {
    let email: String
    let code: String
    let newPassword: String

    enum CodingKeys: String, CodingKey {
        case email, code
        case newPassword = "new_password"
    }
}

struct PasswordResetResponse: Decodable {
    let message: String
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

struct WorkoutCreate: Codable {
    let date: String
    /// Custom hunt name. Nil lets the backend/clients fall back to the
    /// derived suggestion ("Back & Biceps Day", "Tennis") and then the date.
    let name: String?
    let durationMinutes: Int?
    let sessionRpe: Int?
    let notes: String?
    let exercises: [WorkoutExerciseCreate]
    /// Client-generated UUID so the backend can dedupe retries from the offline queue.
    let clientId: String?

    init(
        date: String,
        name: String? = nil,
        durationMinutes: Int?,
        sessionRpe: Int?,
        notes: String?,
        exercises: [WorkoutExerciseCreate],
        clientId: String? = UUID().uuidString
    ) {
        self.date = date
        self.name = name
        self.durationMinutes = durationMinutes
        self.sessionRpe = sessionRpe
        self.notes = notes
        self.exercises = exercises
        self.clientId = clientId
    }

    enum CodingKeys: String, CodingKey {
        case date, name, notes, exercises
        case durationMinutes = "duration_minutes"
        case sessionRpe = "session_rpe"
        case clientId = "client_id"
    }
}

struct WorkoutExerciseCreate: Codable {
    let exerciseId: String
    let orderIndex: Int
    let sets: [SetCreate]
    let supersetGroupId: String?

    enum CodingKeys: String, CodingKey {
        case sets
        case exerciseId = "exercise_id"
        case orderIndex = "order_index"
        case supersetGroupId = "superset_group_id"
    }
}

struct SetCreate: Codable {
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

/// Contract mirror of `app/schemas/workout.py::AriseStrain` (ARISE v2 §7.1):
/// the one user-facing Strain, source-badged.
struct AriseStrain: Decodable {
    let value: Double          // 0-21
    let source: String         // whoop | apple_watch | screenshot
}

struct WorkoutSummaryResponse: Decodable, Identifiable {
    let id: String
    let userId: String
    let date: String
    /// User-set hunt name; `suggestedName` is the server-derived fallback.
    let name: String?
    let suggestedName: String?
    let durationMinutes: Int?
    let sessionRpe: Int?
    let notes: String?
    let exerciseCount: Int
    let totalSets: Int
    let exerciseNames: [String]?
    let primaryMuscles: [String]?
    let createdAt: String
    let updatedAt: String
    // WHOOP activity fields
    let isWhoopActivity: Bool?
    let activityType: String?
    let strain: Double?
    let calories: Int?
    // True for any pure cardio/sport session (WHOOP or Apple Watch). Drives the
    // History row's activity rendering regardless of data source.
    let isActivity: Bool?
    // 0-21 exertion score derived from HR zones (Apple-Watch strain proxy).
    let exertionScore: Double?
    // Unified Strain (ARISE v2 §7.1) — iOS renders this everywhere strain shows.
    let ariseStrain: AriseStrain?
    // Heart rate (additive — Apple Watch / WHOOP). Missing keys decode to nil.
    let avgHeartRate: Int?
    let peakHeartRate: Int?
    let hrSource: String?

    enum CodingKeys: String, CodingKey {
        case id, date, name, notes, strain, calories
        case userId = "user_id"
        case suggestedName = "suggested_name"
        case durationMinutes = "duration_minutes"
        case sessionRpe = "session_rpe"
        case exerciseCount = "exercise_count"
        case totalSets = "total_sets"
        case exerciseNames = "exercise_names"
        case primaryMuscles = "primary_muscles"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case isWhoopActivity = "is_whoop_activity"
        case activityType = "activity_type"
        case isActivity = "is_activity"
        case exertionScore = "exertion_score"
        case ariseStrain = "arise_strain"
        case avgHeartRate = "avg_heart_rate"
        case peakHeartRate = "peak_heart_rate"
        case hrSource = "hr_source"
    }
}

struct WorkoutResponse: Decodable, Identifiable {
    let id: String
    let userId: String
    let date: String
    /// User-set hunt name; `suggestedName` is the server-derived fallback.
    let name: String?
    let suggestedName: String?
    let durationMinutes: Int?
    let sessionRpe: Int?
    let notes: String?
    let exercises: [WorkoutExerciseResponse]
    let createdAt: String
    let updatedAt: String
    // Heart rate (additive — Apple Watch / WHOOP). Missing keys decode to nil.
    // Mirrors backend WorkoutResponse field-for-field (Registry §3): strain included; no hk_uuid.
    let avgHeartRate: Int?
    let peakHeartRate: Int?
    let strain: Double?
    let kilojoules: Double?
    let hrZoneSeconds: [String: Int]?
    let hrSource: String?
    // 0-21 exertion score derived from HR zones (Apple-Watch strain proxy).
    let exertionScore: Double?
    // Unified Strain (ARISE v2 §7.1) — iOS renders this everywhere strain shows.
    let ariseStrain: AriseStrain?
    // Activity classification (mirrors WorkoutSummary) so the detail screen can
    // render a cardio session as an activity instead of a 0-set quest.
    let isActivity: Bool?
    let activityType: String?
    let calories: Int?

    enum CodingKeys: String, CodingKey {
        case id, date, name, notes, exercises, strain, kilojoules, calories
        case userId = "user_id"
        case suggestedName = "suggested_name"
        case durationMinutes = "duration_minutes"
        case sessionRpe = "session_rpe"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case avgHeartRate = "avg_heart_rate"
        case peakHeartRate = "peak_heart_rate"
        case hrZoneSeconds = "hr_zone_seconds"
        case hrSource = "hr_source"
        case exertionScore = "exertion_score"
        case ariseStrain = "arise_strain"
        case isActivity = "is_activity"
        case activityType = "activity_type"
    }
}

// MARK: - Hunt name helpers
// Computed only — not Codable fields, so they don't affect the decode contract.

extension WorkoutSummaryResponse {
    /// Custom name → server suggestion → nil (caller falls back to the date).
    var displayName: String? {
        name ?? suggestedName
    }
}

extension WorkoutResponse {
    /// Custom name → server suggestion → nil (caller falls back to the date).
    var displayName: String? {
        name ?? suggestedName
    }
}

/// Rename-only PUT body for `/workouts/{id}`. An empty string clears the
/// custom name (display falls back to the suggestion).
struct WorkoutRename: Codable {
    let name: String
}

// MARK: - HR display helpers (wearable-HR v1, Chunk D)
// Computed only — not Codable fields, so they don't affect the decode contract.
extension WorkoutResponse {
    /// True when any heart-rate metric is present. Gates the Biometrics section so
    /// a legacy / non-HR workout renders byte-identically to before.
    var hasHRData: Bool {
        avgHeartRate != nil
            || peakHeartRate != nil
            || strain != nil
            || AriseHRZoneBar.hasRenderableZones(hrZoneSeconds)
    }

    /// Strain originates from WHOOP only; Apple-Watch sessions never carry it.
    var isWhoopActivity: Bool { hrSource == "whoop" }
}

struct WorkoutExerciseResponse: Decodable, Identifiable {
    let id: String
    let exerciseId: String
    let exerciseName: String
    let orderIndex: Int
    let sets: [SetResponse]
    let supersetGroupId: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, sets
        case exerciseId = "exercise_id"
        case exerciseName = "exercise_name"
        case orderIndex = "order_index"
        case supersetGroupId = "superset_group_id"
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
    // Heart rate + set timing (additive — populated by HealthKit/WHOOP per-set attribution). Missing keys decode to nil.
    let startTime: String?
    let endTime: String?
    let avgHeartRate: Int?
    let peakHeartRate: Int?

    enum CodingKeys: String, CodingKey {
        case id, weight, reps, rpe, rir, e1rm
        case weightUnit = "weight_unit"
        case setNumber = "set_number"
        case createdAt = "created_at"
        case startTime = "start_time"
        case endTime = "end_time"
        case avgHeartRate = "avg_heart_rate"
        case peakHeartRate = "peak_heart_rate"
    }
}

// MARK: - HealthKit Workout Import

struct HealthKitHRSample: Encodable {
    let timestamp: String   // ISO8601 UTC + fractional seconds
    let bpm: Int
}

struct HealthKitWorkoutImport: Encodable {
    let hkUuid: String
    let activityType: String
    let isStrength: Bool
    let start: String                 // ISO8601 UTC w/ fractional seconds
    let end: String
    let durationSeconds: Int
    let kilojoules: Double?
    let avgHeartRate: Int?
    let peakHeartRate: Int?
    let hrZoneSeconds: [String: Int]? // dict, matches backend storage; nil if age unknown
    let heartRateSamples: [HealthKitHRSample]?
    let distanceMeters: Double?       // HKWorkout.totalDistance in meters

    enum CodingKeys: String, CodingKey {
        case start, end, kilojoules
        case hkUuid = "hk_uuid"
        case activityType = "activity_type"
        case isStrength = "is_strength"
        case durationSeconds = "duration_seconds"
        case avgHeartRate = "avg_heart_rate"
        case peakHeartRate = "peak_heart_rate"
        case hrZoneSeconds = "hr_zone_seconds"
        case heartRateSamples = "heart_rate_samples"
        case distanceMeters = "distance_meters"
    }
}

struct HealthKitImportRequest: Encodable {
    let workouts: [HealthKitWorkoutImport]
}

struct HealthKitUnmatched: Decodable {
    let hkUuid: String
    let activityType: String
    let start: String
    let end: String

    enum CodingKeys: String, CodingKey {
        case start, end
        case hkUuid = "hk_uuid"
        case activityType = "activity_type"
    }
}

struct HealthKitImportResponse: Decodable {
    let imported: [String]
    let skippedDuplicates: [String]
    let sessionsCreated: [String]
    let sessionsUpdated: [String]
    let unmatched: [HealthKitUnmatched]
    let questsCompleted: [String]

    enum CodingKeys: String, CodingKey {
        case imported, unmatched
        case skippedDuplicates = "skipped_duplicates"
        case sessionsCreated = "sessions_created"
        case sessionsUpdated = "sessions_updated"
        case questsCompleted = "quests_completed"
    }
}

// MARK: - WHOOP connection (live connect + auto-sync since ARISE v2.1)

struct WhoopStatusResponse: Decodable {
    let connected: Bool
    let configured: Bool
}

struct WhoopConnectResponse: Decodable {
    let authorizeUrl: String

    enum CodingKeys: String, CodingKey {
        case authorizeUrl = "authorize_url"
    }
}

/// Minimal mirror of POST /whoop/sync — the client only needs to know it ran;
/// the full payload (session counts, recovery days) is server-side detail.
struct WhoopSyncResponse: Decodable {
    let workoutsFetched: Int?
    let sessionsUpdated: Int?

    enum CodingKeys: String, CodingKey {
        case workoutsFetched = "workouts_fetched"
        case sessionsUpdated = "sessions_updated"
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

// MARK: - Weekly Progress Report

struct GoalProgressReportResponse: Decodable, Identifiable {
    let goalId: String
    let exerciseName: String
    let exerciseId: String
    let targetWeight: Double
    let targetReps: Int
    let weightUnit: String
    let deadline: String
    let startingE1rm: Double?
    let currentE1rm: Double?
    let progressPercent: Double
    let requiredWeeklyGain: Double?
    let actualWeeklyGain: Double?
    let status: String  // "on_track" | "ahead" | "behind"
    let projectedCompletionDate: String?
    let weeksRemaining: Double
    let actualPoints: [ProgressPoint]
    let projectedPoints: [ProgressPoint]

    var id: String { goalId }

    enum CodingKeys: String, CodingKey {
        case deadline, status
        case goalId = "goal_id"
        case exerciseName = "exercise_name"
        case exerciseId = "exercise_id"
        case targetWeight = "target_weight"
        case targetReps = "target_reps"
        case weightUnit = "weight_unit"
        case startingE1rm = "starting_e1rm"
        case currentE1rm = "current_e1rm"
        case progressPercent = "progress_percent"
        case requiredWeeklyGain = "required_weekly_gain"
        case actualWeeklyGain = "actual_weekly_gain"
        case projectedCompletionDate = "projected_completion_date"
        case weeksRemaining = "weeks_remaining"
        case actualPoints = "actual_points"
        case projectedPoints = "projected_points"
    }
}

struct CoachingSuggestionResponse: Decodable, Identifiable {
    let type: String      // "volume" | "plateau" | "frequency" | "slowdown" | "motivation"
    let priority: String  // "high" | "medium" | "low"
    let title: String
    let description: String
    let exerciseName: String?

    var id: String { title + type }

    enum CodingKeys: String, CodingKey {
        case type, priority, title, description
        case exerciseName = "exercise_name"
    }
}

struct WeeklyProgressReportResponse: Decodable {
    let weekStart: String
    let weekEnd: String
    let totalWorkouts: Int
    let totalSets: Int
    let totalVolume: Double
    let volumeChangePercent: Double?
    let prsAchieved: [PRResponse]
    let goalReports: [GoalProgressReportResponse]
    let suggestions: [CoachingSuggestionResponse]
    let hasSufficientData: Bool

    enum CodingKeys: String, CodingKey {
        case suggestions
        case weekStart = "week_start"
        case weekEnd = "week_end"
        case totalWorkouts = "total_workouts"
        case totalSets = "total_sets"
        case totalVolume = "total_volume"
        case volumeChangePercent = "volume_change_percent"
        case prsAchieved = "prs_achieved"
        case goalReports = "goal_reports"
        case hasSufficientData = "has_sufficient_data"
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

// MARK: - Notifications

struct DeviceTokenResponse: Decodable {
    let message: String
}

struct NotificationPreferenceResponse: Decodable {
    let notificationType: String
    let enabled: Bool

    enum CodingKeys: String, CodingKey {
        case notificationType = "notification_type"
        case enabled
    }
}

struct NotificationPreferencesResponse: Decodable {
    let preferences: [NotificationPreferenceResponse]
}

struct NotificationPreferenceUpdate: Encodable {
    let notificationType: String
    let enabled: Bool

    enum CodingKeys: String, CodingKey {
        case notificationType = "notification_type"
        case enabled
    }
}

// MARK: - Scan Balance

struct ScanBalanceResponse: Decodable {
    let scanCredits: Int
    let hasUnlimited: Bool
    let freeScansResetAt: String?

    enum CodingKeys: String, CodingKey {
        case scanCredits = "scan_credits"
        case hasUnlimited = "has_unlimited"
        case freeScansResetAt = "free_scans_reset_at"
    }
}

struct PurchaseVerifyResponse: Decodable {
    let success: Bool
    let creditsAdded: Int
    let newBalance: Int
    let hasUnlimited: Bool

    enum CodingKeys: String, CodingKey {
        case success
        case creditsAdded = "credits_added"
        case newBalance = "new_balance"
        case hasUnlimited = "has_unlimited"
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

// Codable (not just Decodable): the §7.3 edit-before-save flow re-encodes
// extracted zones into ActivitySaveRequest.
struct HeartRateZone: Codable {
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

// MARK: - Hunter Condition (ARISE v2 §4)

/// Contract mirror of backend `app/schemas/condition.py::ConditionBand` values.
enum ConditionBand: String, Decodable {
    case peak
    case battleReady = "battle_ready"
    case strained
    case critical

    /// Mirrors backend `condition_service.band_for_score` (§4.2 thresholds:
    /// peak ≥85, battle ready ≥65, strained ≥40) for scores that arrive
    /// without a band, e.g. `GateResponse.conditionAtSpawn`.
    init(score: Int) {
        switch score {
        case 85...: self = .peak
        case 65..<85: self = .battleReady
        case 40..<65: self = .strained
        default: self = .critical
        }
    }

    var label: String {
        switch self {
        case .peak: return "PEAK"
        case .battleReady: return "BATTLE READY"
        case .strained: return "STRAINED"
        case .critical: return "CRITICAL"
        }
    }

    var copy: String {
        switch self {
        case .peak: return "The System favors you."
        case .battleReady: return "Cleared for battle."
        case .strained: return "Fight carefully."
        case .critical: return "REST DECREED."
        }
    }

    var color: Color {
        switch self {
        case .peak: return .systemPrimary
        case .battleReady: return .successGreen
        case .strained: return .gold
        case .critical: return .warningRed
        }
    }
}

/// Contract mirror of `app/schemas/condition.py::ConditionInput`.
struct ConditionInput: Decodable, Identifiable {
    let key: String            // recovery | cooldowns | sleep | strain_yesterday | rhr_trend
    let label: String
    let raw: Double?
    let subscore: Int?         // nil when unavailable
    let weight: Double
    let effectiveWeight: Double  // post-renormalization; 0 when unavailable
    let available: Bool
    let source: String?        // whoop | apple_watch | app

    var id: String { key }

    enum CodingKeys: String, CodingKey {
        case key, label, raw, subscore, weight, available, source
        case effectiveWeight = "effective_weight"
    }
}

/// Contract mirror of `app/schemas/condition.py::ConditionResponse`.
struct ConditionResponse: Decodable {
    let score: Int             // 0-100
    let band: ConditionBand
    let generatedAt: String
    let inputs: [ConditionInput]
    let musclesCooling: [MuscleCooldownStatus]

    enum CodingKeys: String, CodingKey {
        case score, band, inputs
        case generatedAt = "generated_at"
        case musclesCooling = "muscles_cooling"
    }
}

// MARK: - System Directive (ARISE v2 §5)

/// Heterogeneous JSON value for the directive's type-specific `params`
/// (lift, muscle, delta_pct, target_sets, ...).
enum DirectiveParamValue: Decodable {
    case bool(Bool)
    case int(Int)
    case double(Double)
    case string(String)
    case stringList([String])  // e.g. LIFT_LAG exercise_ids (v2.1)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Int.self) {
            self = .int(value)
        } else if let value = try? container.decode(Double.self) {
            self = .double(value)
        } else if let value = try? container.decode([String].self) {
            self = .stringList(value)
        } else {
            self = .string(try container.decode(String.self))
        }
    }

    var displayString: String {
        switch self {
        case .bool(let value): return value ? "YES" : "NO"
        case .int(let value): return "\(value)"
        case .double(let value): return String(format: "%.1f", value)
        case .string(let value): return value
        case .stringList(let value): return value.joined(separator: ", ")
        }
    }
}

/// Contract mirror of `app/schemas/directive.py::DirectiveResponse`.
struct DirectiveResponse: Decodable, Identifiable {
    let id: String
    let date: String           // YYYY-MM-DD (user-local day)
    let directiveType: String  // rest | streak_save | reclaim_volume | break_plateau
    //                            | frequency | gate_reminder | lift_lag | maintain
    let message: String
    let params: [String: DirectiveParamValue]?
    let xpReward: Int
    let isCompleted: Bool
    let completedAt: String?   // ISO8601

    enum CodingKeys: String, CodingKey {
        case id, date, message, params
        case directiveType = "directive_type"
        case xpReward = "xp_reward"
        case isCompleted = "is_completed"
        case completedAt = "completed_at"
    }
}

/// Contract mirror of `app/schemas/directive.py::DirectiveHistoryResponse`.
struct DirectiveHistoryResponse: Decodable {
    let directives: [DirectiveResponse]
}

// MARK: - Exertion analytics (ARISE v2 §7.2)

/// Contract mirror of `app/schemas/exertion.py::ExertionWeekPoint`.
struct ExertionWeekPoint: Decodable, Identifiable {
    let weekStart: String              // YYYY-MM-DD (Monday)
    let strainTotal: Double?           // nil when no strain data that week
    let strainAvg: Double?
    let workoutCount: Int
    let volumeLb: Double
    let zoneSeconds: [String: Int]     // {z1..z5}, may be empty

    var id: String { weekStart }

    enum CodingKeys: String, CodingKey {
        case weekStart = "week_start"
        case strainTotal = "strain_total"
        case strainAvg = "strain_avg"
        case workoutCount = "workout_count"
        case volumeLb = "volume_lb"
        case zoneSeconds = "zone_seconds"
    }
}

/// Contract mirror of `app/schemas/exertion.py::MatchedSet`.
struct CardiacCostMatchedSet: Decodable {
    let weight: Double
    let reps: Int
}

/// Contract mirror of `app/schemas/exertion.py::CardiacCostPoint`.
struct CardiacCostPoint: Decodable, Identifiable {
    let weekStart: String
    let deltaHrMedian: Double
    let nSets: Int

    var id: String { weekStart }

    enum CodingKeys: String, CodingKey {
        case weekStart = "week_start"
        case deltaHrMedian = "delta_hr_median"
        case nSets = "n_sets"
    }
}

/// Contract mirror of `app/schemas/exertion.py::CardiacCostResponse`.
struct CardiacCostResponse: Decodable {
    let exerciseId: String
    let matchedSet: CardiacCostMatchedSet?
    let points: [CardiacCostPoint]
    let percentChange: Double?
    let trendDirection: String        // improving | regressing | stable | insufficient_data
    let caveats: [String]

    enum CodingKeys: String, CodingKey {
        case points, caveats
        case exerciseId = "exercise_id"
        case matchedSet = "matched_set"
        case percentChange = "percent_change"
        case trendDirection = "trend_direction"
    }
}

// MARK: - Activity save (ARISE v2 §7.3 edit-before-save)

/// Contract mirror of `app/schemas/screenshot.py::ActivitySaveRequest`.
struct ActivitySaveRequest: Encodable {
    let activityType: String?
    let sessionDate: String?           // YYYY-MM-DD
    let timeRange: String?
    let durationMinutes: Int?
    let strain: Double?
    let steps: Int?
    let calories: Int?
    let avgHr: Int?
    let maxHr: Int?
    let heartRateZones: [HeartRateZone]

    enum CodingKeys: String, CodingKey {
        case strain, steps, calories
        case activityType = "activity_type"
        case sessionDate = "session_date"
        case timeRange = "time_range"
        case durationMinutes = "duration_minutes"
        case avgHr = "avg_hr"
        case maxHr = "max_hr"
        case heartRateZones = "heart_rate_zones"
    }
}

/// Contract mirror of `app/schemas/screenshot.py::ActivitySaveResponse`.
struct ActivitySaveResponse: Decodable {
    let activityId: String
    let workoutId: String
    let activitySaved: Bool

    enum CodingKeys: String, CodingKey {
        case activityId = "activity_id"
        case workoutId = "workout_id"
        case activitySaved = "activity_saved"
    }
}

// MARK: - PR Gates (ARISE v2 §6)

/// Contract mirror of `app/schemas/gate.py::GateResponse`.
struct GateResponse: Decodable, Identifiable {
    let id: String
    let exerciseId: String
    let exerciseName: String
    let rank: String               // C | B | A | S
    let name: String               // "B-Rank Gate: Bench 225×4"
    let targetWeight: Double
    let targetReps: Int
    let targetE1rm: Double
    let baselineE1rm: Double
    let projectedE1rm: Double
    let weeklySlope: Double        // lb/week at spawn
    let conditionAtSpawn: Int
    let status: String             // open | active | cleared | expired
    let spawnedAt: String          // ISO8601
    let expiresAt: String          // ISO8601
    let acceptedAt: String?
    let clearedAt: String?
    let clearedBySetId: String?
    let xpAwarded: Int?

    /// Progress toward the target (baseline / target) for the proximity bar.
    var proximity: Double {
        guard targetE1rm > 0 else { return 0 }
        return min(1.0, baselineE1rm / targetE1rm)
    }

    /// Whole days until the window closes (0 when past due).
    var daysRemaining: Int {
        guard let expiry = expiresAt.parseISO8601Date() else { return 0 }
        return max(0, Calendar.current.dateComponents([.day], from: Date(), to: expiry).day ?? 0)
    }

    /// Rank sigil color — reuses the hunter rank palette (spec §9.8).
    var rankColor: Color {
        HunterRank(rawValue: rank.uppercased())?.color ?? .textMuted
    }

    enum CodingKeys: String, CodingKey {
        case id, rank, name, status
        case exerciseId = "exercise_id"
        case exerciseName = "exercise_name"
        case targetWeight = "target_weight"
        case targetReps = "target_reps"
        case targetE1rm = "target_e1rm"
        case baselineE1rm = "baseline_e1rm"
        case projectedE1rm = "projected_e1rm"
        case weeklySlope = "weekly_slope"
        case conditionAtSpawn = "condition_at_spawn"
        case spawnedAt = "spawned_at"
        case expiresAt = "expires_at"
        case acceptedAt = "accepted_at"
        case clearedAt = "cleared_at"
        case clearedBySetId = "cleared_by_set_id"
        case xpAwarded = "xp_awarded"
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

// MARK: - Goals

struct GoalCreate: Encodable {
    let exerciseId: String
    let targetWeight: Double
    let targetReps: Int  // Target reps (1 = true 1RM goal)
    let weightUnit: String
    let deadline: String  // ISO date string
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case notes, deadline
        case exerciseId = "exercise_id"
        case targetWeight = "target_weight"
        case targetReps = "target_reps"
        case weightUnit = "weight_unit"
    }
}

struct GoalUpdate: Encodable {
    let targetWeight: Double?
    let targetReps: Int?
    let weightUnit: String?
    let deadline: String?
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case notes, deadline
        case targetWeight = "target_weight"
        case targetReps = "target_reps"
        case weightUnit = "weight_unit"
    }
}

struct GoalResponse: Decodable, Identifiable {
    let id: String
    let exerciseId: String
    let exerciseName: String
    let targetWeight: Double
    let targetReps: Int  // Target reps (1 = true 1RM goal)
    let targetE1rm: Double  // Calculated e1RM for target
    let weightUnit: String
    let deadline: String
    let startingE1rm: Double?
    let currentE1rm: Double?
    let status: String
    let notes: String?
    let createdAt: String
    let progressPercent: Double
    let weightToGo: Double  // Actually e1RM to go
    let weeksRemaining: Int

    enum CodingKeys: String, CodingKey {
        case id, deadline, status, notes
        case exerciseId = "exercise_id"
        case exerciseName = "exercise_name"
        case targetWeight = "target_weight"
        case targetReps = "target_reps"
        case targetE1rm = "target_e1rm"
        case weightUnit = "weight_unit"
        case startingE1rm = "starting_e1rm"
        case currentE1rm = "current_e1rm"
        case createdAt = "created_at"
        case progressPercent = "progress_percent"
        case weightToGo = "weight_to_go"
        case weeksRemaining = "weeks_remaining"
    }
}

struct GoalSummaryResponse: Decodable, Identifiable {
    let id: String
    let exerciseName: String
    let targetWeight: Double
    let targetReps: Int  // Target reps (1 = true 1RM goal)
    let targetE1rm: Double  // Calculated e1RM for target
    let weightUnit: String
    let deadline: String
    let progressPercent: Double
    let status: String

    enum CodingKeys: String, CodingKey {
        case id, deadline, status
        case exerciseName = "exercise_name"
        case targetWeight = "target_weight"
        case targetReps = "target_reps"
        case targetE1rm = "target_e1rm"
        case weightUnit = "weight_unit"
        case progressPercent = "progress_percent"
    }
}

struct GoalsListResponse: Decodable {
    let goals: [GoalSummaryResponse]
    let activeCount: Int
    let completedCount: Int
    let canAddMore: Bool
    let maxGoals: Int

    enum CodingKeys: String, CodingKey {
        case goals
        case activeCount = "active_count"
        case completedCount = "completed_count"
        case canAddMore = "can_add_more"
        case maxGoals = "max_goals"
    }
}

// MARK: - Batch Goal Creation

struct GoalBatchCreate: Encodable {
    let goals: [GoalCreate]
}

struct GoalBatchCreateResponse: Decodable {
    let goals: [GoalResponse]
    let createdCount: Int
    let activeCount: Int

    enum CodingKeys: String, CodingKey {
        case goals
        case createdCount = "created_count"
        case activeCount = "active_count"
    }
}

// MARK: - Goal Progress

struct ProgressPoint: Decodable {
    let date: String
    let e1rm: Double
}

struct GoalProgressResponse: Decodable {
    let goalId: String
    let exerciseName: String
    let targetWeight: Double
    let targetReps: Int
    let targetE1rm: Double
    let targetDate: String
    let startingE1rm: Double?
    let currentE1rm: Double?
    let weightUnit: String

    // Graph data
    let actualPoints: [ProgressPoint]
    let projectedPoints: [ProgressPoint]

    // Status
    let status: String  // "ahead", "on_track", "behind"
    let weeksDifference: Int  // positive = ahead, negative = behind
    let weeklyGainRate: Double  // lbs per week based on actual progress
    let requiredGainRate: Double  // lbs per week needed to hit target

    enum CodingKeys: String, CodingKey {
        case status
        case goalId = "goal_id"
        case exerciseName = "exercise_name"
        case targetWeight = "target_weight"
        case targetReps = "target_reps"
        case targetE1rm = "target_e1rm"
        case targetDate = "target_date"
        case startingE1rm = "starting_e1rm"
        case currentE1rm = "current_e1rm"
        case weightUnit = "weight_unit"
        case actualPoints = "actual_points"
        case projectedPoints = "projected_points"
        case weeksDifference = "weeks_difference"
        case weeklyGainRate = "weekly_gain_rate"
        case requiredGainRate = "required_gain_rate"
    }

    /// Whether the user is on track or ahead of schedule
    var isOnTrack: Bool {
        status == "on_track" || status == "ahead"
    }

    /// Human-readable status message
    var statusMessage: String {
        switch status {
        case "ahead":
            return weeksDifference > 0 ? "+\(weeksDifference) weeks ahead" : "On track"
        case "on_track":
            return "On track"
        case "behind":
            return weeksDifference < 0 ? "\(abs(weeksDifference)) weeks behind" : "Behind schedule"
        default:
            return status.capitalized
        }
    }
}
