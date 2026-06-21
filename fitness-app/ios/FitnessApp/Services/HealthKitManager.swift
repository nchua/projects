import Foundation
import HealthKit

/// Manages all HealthKit interactions for syncing activity data
@MainActor
class HealthKitManager: ObservableObject {
    static let shared = HealthKitManager()

    private let healthStore = HKHealthStore()

    @Published var isAuthorized = false
    @Published var authorizationError: String?
    @Published var todaySteps: Int = 0
    @Published var todayActiveCalories: Int = 0
    @Published var todayExerciseMinutes: Int = 0
    @Published var todayStandHours: Int = 0
    @Published var isSyncing = false
    @Published var lastSyncDate: Date?

    /// Separate from `isSyncing` (daily activity sync) so the two paths never block each other.
    @Published var isImportingWorkouts = false

    // Weekly stats (last 7 days)
    @Published var weeklySteps: Int = 0
    @Published var weeklyCalories: Int = 0
    @Published var weeklyExerciseMinutes: Int = 0
    @Published var weeklyAvgSteps: Int = 0

    // HealthKit types we want to read
    private let readTypes: Set<HKObjectType> = {
        var types = Set<HKObjectType>()
        if let stepCount = HKQuantityType.quantityType(forIdentifier: .stepCount) {
            types.insert(stepCount)
        }
        if let activeEnergy = HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned) {
            types.insert(activeEnergy)
        }
        if let basalEnergy = HKQuantityType.quantityType(forIdentifier: .basalEnergyBurned) {
            types.insert(basalEnergy)
        }
        if let exerciseTime = HKQuantityType.quantityType(forIdentifier: .appleExerciseTime) {
            types.insert(exerciseTime)
        }
        if let standHour = HKCategoryType.categoryType(forIdentifier: .appleStandHour) {
            types.insert(standHour)
        }
        // Workout + heart-rate reads (Chunk C — wearable HR import). The enlarged set means
        // the single Apple Health permission sheet now covers steps/calories + workouts/HR,
        // so permission is still only asked once.
        types.insert(HKObjectType.workoutType())
        if let heartRate = HKQuantityType.quantityType(forIdentifier: .heartRate) {
            types.insert(heartRate)
        }
        if let restingHeartRate = HKQuantityType.quantityType(forIdentifier: .restingHeartRate) {
            types.insert(restingHeartRate)
        }
        if let hrv = HKQuantityType.quantityType(forIdentifier: .heartRateVariabilitySDNN) {
            types.insert(hrv)
        }
        return types
    }()

    private init() {}

    // MARK: - Authorization

    var isHealthDataAvailable: Bool {
        HKHealthStore.isHealthDataAvailable()
    }

    func requestAuthorization() async {
        guard isHealthDataAvailable else {
            authorizationError = "Health data is not available on this device"
            return
        }

        do {
            try await healthStore.requestAuthorization(toShare: [], read: readTypes)
            isAuthorized = true
            authorizationError = nil
            await fetchTodayStats()
        } catch {
            authorizationError = error.localizedDescription
            isAuthorized = false
        }
    }

    // MARK: - Fetch Today's Stats

    func fetchTodayStats() async {
        let today = Calendar.current.startOfDay(for: Date())
        let endOfDay = Calendar.current.date(byAdding: .day, value: 1, to: today)!

        async let steps = fetchSum(.stepCount, start: today, end: endOfDay)
        async let activeCalories = fetchSum(.activeEnergyBurned, start: today, end: endOfDay)
        async let exerciseMinutes = fetchSum(.appleExerciseTime, start: today, end: endOfDay)
        async let standHours = fetchStandHours(start: today, end: endOfDay)

        let (s, ac, em, sh) = await (steps, activeCalories, exerciseMinutes, standHours)

        todaySteps = Int(s)
        todayActiveCalories = Int(ac)
        todayExerciseMinutes = Int(em)
        todayStandHours = sh

        await fetchWeeklyStats()
    }

    // MARK: - Fetch Weekly Stats (Last 7 Days)

    func fetchWeeklyStats() async {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        let sevenDaysAgo = calendar.date(byAdding: .day, value: -6, to: today)!
        let endOfToday = calendar.date(byAdding: .day, value: 1, to: today)!

        async let steps = fetchSum(.stepCount, start: sevenDaysAgo, end: endOfToday)
        async let calories = fetchSum(.activeEnergyBurned, start: sevenDaysAgo, end: endOfToday)
        async let exercise = fetchSum(.appleExerciseTime, start: sevenDaysAgo, end: endOfToday)

        let (s, c, e) = await (steps, calories, exercise)

        weeklySteps = Int(s)
        weeklyCalories = Int(c)
        weeklyExerciseMinutes = Int(e)
        weeklyAvgSteps = Int(s) / 7
    }

    // MARK: - Fetch Data for Date Range

    func fetchDailyStats(for date: Date) async -> DailyHealthData {
        let startOfDay = Calendar.current.startOfDay(for: date)
        let endOfDay = Calendar.current.date(byAdding: .day, value: 1, to: startOfDay)!

        async let steps = fetchSum(.stepCount, start: startOfDay, end: endOfDay)
        async let activeCalories = fetchSum(.activeEnergyBurned, start: startOfDay, end: endOfDay)
        async let basalCalories = fetchSum(.basalEnergyBurned, start: startOfDay, end: endOfDay)
        async let exerciseMinutes = fetchSum(.appleExerciseTime, start: startOfDay, end: endOfDay)
        async let standHours = fetchStandHours(start: startOfDay, end: endOfDay)

        let (s, ac, bc, em, sh) = await (steps, activeCalories, basalCalories, exerciseMinutes, standHours)

        return DailyHealthData(
            date: startOfDay,
            steps: Int(s),
            activeCalories: Int(ac),
            totalCalories: Int(ac + bc),
            exerciseMinutes: Int(em),
            standHours: sh,
            moveCalories: Int(ac)
        )
    }

    // MARK: - Sync to Backend

    func syncToBackend() async {
        guard !isSyncing else { return }
        isSyncing = true
        defer { isSyncing = false }

        do {
            // Check last sync date
            let lastSync = try await APIClient.shared.getLastSync()
            let lastSyncedDate = lastSync.lastSyncedDate.flatMap { dateFromISO($0) }

            // Determine date range to sync
            let today = Calendar.current.startOfDay(for: Date())
            var datesToSync: [Date] = []

            if let lastDate = lastSyncedDate {
                // Sync from day after last sync to today
                var current = Calendar.current.date(byAdding: .day, value: 1, to: lastDate)!
                while current <= today {
                    datesToSync.append(current)
                    current = Calendar.current.date(byAdding: .day, value: 1, to: current)!
                }
                // Always include today for updates
                if !datesToSync.contains(today) {
                    datesToSync.append(today)
                }
            } else {
                // First sync - sync last 7 days
                for dayOffset in 0..<7 {
                    if let date = Calendar.current.date(byAdding: .day, value: -dayOffset, to: today) {
                        datesToSync.append(date)
                    }
                }
            }

            // Fetch and sync data
            guard !datesToSync.isEmpty else { return }

            var activities: [ActivityCreate] = []
            for date in datesToSync {
                let stats = await fetchDailyStats(for: date)
                activities.append(stats.toActivityCreate())
            }

            // Bulk sync to backend
            _ = try await APIClient.shared.syncActivityBulk(activities)
            lastSyncDate = Date()

            // Refresh today's stats
            await fetchTodayStats()

        } catch {
            print("HealthKit sync error: \(error)")
        }
    }

    func syncTodayOnly() async {
        guard !isSyncing else { return }
        isSyncing = true
        defer { isSyncing = false }

        do {
            let today = Calendar.current.startOfDay(for: Date())
            let stats = await fetchDailyStats(for: today)
            _ = try await APIClient.shared.syncActivity(stats.toActivityCreate())
            lastSyncDate = Date()
            await fetchTodayStats()
        } catch {
            print("HealthKit sync error: \(error)")
        }
    }

    // MARK: - Workout Import (Wearable HR)

    /// Read completed `HKWorkout`s + their raw HR samples since the stored cursor, build the
    /// import payload (zones from `220 − age`, decimated samples), dedup locally, and POST to
    /// `/workouts/import-healthkit` (chunked to stay under the 10s request timeout).
    ///
    /// Silent and side-effect-light: returns `nil` (not an error) when Health is unavailable,
    /// permission hasn't been granted, an import is already in flight, or nothing new is found.
    /// On Simulator (no Watch data) this legitimately returns `nil` — not a bug.
    ///
    /// - Parameter age: the user's age (from `ProfileResponse.age`); when `nil`, `hr_zone_seconds`
    ///   is omitted (avg/peak + raw samples are still sent so the backend derives per-set HR).
    @discardableResult
    func importNewWorkouts(age: Int?) async -> HealthKitImportResponse? {
        guard isHealthDataAvailable else { return nil }
        guard isAuthorized else { return nil }
        guard !isImportingWorkouts else { return nil }
        isImportingWorkouts = true
        defer { isImportingWorkouts = false }

        let now = Date()
        // Query window. A workout can land in HealthKit with a *past* start date (Watch→iPhone
        // sync lags, sometimes by days), so a high-water-mark cursor alone would silently skip
        // late arrivals. We always re-scan at least a generous fixed floor, and further back on a
        // long absence (cursor − buffer). This is cheap: already-sent uuids are filtered out
        // before any per-workout HR query, so re-scanning costs only the workout-list query, and
        // the idempotent backend makes any overlap free on the wire.
        let queryStart: Date
        let lookbackFloor = Calendar.current.date(byAdding: .day, value: -Self.steadyStateLookbackDays, to: now)
            ?? now.addingTimeInterval(-Double(Self.steadyStateLookbackDays) * 86_400)
        if let cursor = WorkoutImportStore.shared.lastWorkoutImportDate {
            queryStart = min(cursor.addingTimeInterval(-Self.reScanBuffer), lookbackFloor)
        } else {
            queryStart = Calendar.current.date(byAdding: .day, value: -30, to: now) ?? now.addingTimeInterval(-30 * 86_400)
        }

        let workouts = await fetchWorkouts(start: queryStart, end: now)
        guard !workouts.isEmpty else {
            // Nothing in range. Advancing the cursor here is safe: the next run still re-scans the
            // fixed lookback floor, so a workout that syncs in later (with a past start date) is
            // still caught — the cursor is a perf bound, not the correctness guarantee.
            WorkoutImportStore.shared.advanceCursor(to: now)
            return nil
        }

        // Skip workouts already sent before doing the (more expensive) per-workout HR queries.
        var imports: [HealthKitWorkoutImport] = []
        for workout in workouts where !WorkoutImportStore.shared.isImported(workout.uuid.uuidString) {
            imports.append(await buildImport(for: workout, age: age))
        }

        guard !imports.isEmpty else {
            WorkoutImportStore.shared.advanceCursor(to: now)
            return nil
        }

        var aggregate: HealthKitImportResponse?
        var acknowledged: [String] = []
        do {
            for chunk in imports.chunked(into: Self.importChunkSize) {
                let response = try await APIClient.shared.importHealthKitWorkouts(chunk)
                // imported + skipped both mean "the backend has it" → safe to never resend.
                acknowledged.append(contentsOf: response.imported + response.skippedDuplicates)
                aggregate = Self.merge(aggregate, response)
            }
            WorkoutImportStore.shared.markImported(acknowledged)
            WorkoutImportStore.shared.advanceCursor(to: now)
        } catch {
            // Persist whatever chunks did succeed; leave the cursor so the next run retries the rest.
            WorkoutImportStore.shared.markImported(acknowledged)
            print("HealthKit workout import error: \(error)")
        }
        return aggregate
    }

    // MARK: - Workout Import Helpers

    /// ~1 sample / 5s decimation target, capped so a long workout can't blow the payload up.
    private static let decimationIntervalSeconds: TimeInterval = 5
    private static let maxHRSamplesPerWorkout = 720
    /// Per-POST workout cap so the first-run 30-day batch stays under the 10s request timeout.
    private static let importChunkSize = 10
    /// Re-scan window before the cursor to catch late Watch→iPhone syncs (see `importNewWorkouts`).
    private static let reScanBuffer: TimeInterval = 2 * 86_400 // 2 days
    /// Steady-state minimum lookback: every run re-scans at least this far back regardless of the
    /// cursor, so a workout that syncs from the Watch days late is still picked up (dedup keeps it cheap).
    private static let steadyStateLookbackDays = 14

    private static let hrUnit = HKUnit.count().unitDivided(by: .minute())

    private static let iso8601UTCFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    private static func merge(_ lhs: HealthKitImportResponse?, _ rhs: HealthKitImportResponse) -> HealthKitImportResponse {
        guard let lhs = lhs else { return rhs }
        // imported/sessions*/unmatched are disjoint across chunks (different workouts); only a
        // quest spanning days touched by two chunks can repeat, so dedup that one to keep the count honest.
        var quests = lhs.questsCompleted
        let seen = Set(quests)
        quests.append(contentsOf: rhs.questsCompleted.filter { !seen.contains($0) })
        return HealthKitImportResponse(
            imported: lhs.imported + rhs.imported,
            skippedDuplicates: lhs.skippedDuplicates + rhs.skippedDuplicates,
            sessionsCreated: lhs.sessionsCreated + rhs.sessionsCreated,
            sessionsUpdated: lhs.sessionsUpdated + rhs.sessionsUpdated,
            unmatched: lhs.unmatched + rhs.unmatched,
            questsCompleted: quests
        )
    }

    /// Map `HKWorkoutActivityType` → the backend's controlled `activity_type` vocab + the
    /// client-declared strength/cardio flag. Strings are chosen to fuzz-match (≥70) the seeded
    /// Sport/Cardio exercise *names* (`"running"`→"Running"=100); short/partial labels that would
    /// score <70 are avoided (Amendment Log 2026-06-21, Chunk A). Cardio types with no seeded
    /// exercise (e.g. `"hiit"`, `"elliptical"`, `"core_training"`, `"other"`) still create a
    /// session server-side — just unlinked, which is acceptable for v1.
    static func mapActivityType(_ type: HKWorkoutActivityType) -> (activityType: String, isStrength: Bool) {
        switch type {
        case .traditionalStrengthTraining, .functionalStrengthTraining:
            return ("strength_training", true)
        case .running:
            return ("running", false)
        case .walking:
            return ("walking", false)
        case .cycling:
            return ("cycling", false)
        case .highIntensityIntervalTraining:
            return ("hiit", false)
        case .coreTraining:
            return ("core_training", false)
        case .yoga:
            return ("yoga", false)
        case .rowing:
            return ("rowing", false)
        case .elliptical:
            return ("elliptical", false)
        default:
            return ("other", false)
        }
    }

    private func fetchWorkouts(start: Date, end: Date) async -> [HKWorkout] {
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)
        let sort = [NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)]

        return await withCheckedContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: .workoutType(),
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: sort
            ) { _, samples, _ in
                continuation.resume(returning: (samples as? [HKWorkout]) ?? [])
            }
            healthStore.execute(query)
        }
    }

    private func fetchHeartRateSamples(for workout: HKWorkout) async -> [HKQuantitySample] {
        guard let hrType = HKQuantityType.quantityType(forIdentifier: .heartRate) else { return [] }
        let predicate = HKQuery.predicateForObjects(from: workout)
        let sort = [NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)]

        return await withCheckedContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: hrType,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: sort
            ) { _, samples, _ in
                continuation.resume(returning: (samples as? [HKQuantitySample]) ?? [])
            }
            healthStore.execute(query)
        }
    }

    private func buildImport(for workout: HKWorkout, age: Int?) async -> HealthKitWorkoutImport {
        let (activityType, isStrength) = Self.mapActivityType(workout.workoutActivityType)
        let rawSamples = await fetchHeartRateSamples(for: workout)

        // avg/peak from ALL raw samples (most accurate); payload uses the decimated set.
        let bpms = rawSamples.map { Int($0.quantity.doubleValue(for: Self.hrUnit).rounded()) }
        let avgHeartRate = bpms.isEmpty ? nil : Int((Double(bpms.reduce(0, +)) / Double(bpms.count)).rounded())
        let peakHeartRate = bpms.max()

        let decimated = decimate(rawSamples)
        let heartRateSamples: [HealthKitHRSample]? = decimated.isEmpty ? nil : decimated.map {
            HealthKitHRSample(
                timestamp: Self.iso8601UTCFormatter.string(from: $0.startDate),
                bpm: Int($0.quantity.doubleValue(for: Self.hrUnit).rounded())
            )
        }

        let hrZoneSeconds = zoneSeconds(from: decimated, age: age)

        var kilojoules: Double?
        if let energyType = HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned),
           let stats = workout.statistics(for: energyType),
           let sum = stats.sumQuantity() {
            kilojoules = sum.doubleValue(for: .kilocalorie()) * 4.184 // kcal → kJ
        }

        return HealthKitWorkoutImport(
            hkUuid: workout.uuid.uuidString,
            activityType: activityType,
            isStrength: isStrength,
            start: Self.iso8601UTCFormatter.string(from: workout.startDate),
            end: Self.iso8601UTCFormatter.string(from: workout.endDate),
            durationSeconds: Int(workout.duration),
            kilojoules: kilojoules,
            avgHeartRate: avgHeartRate,
            peakHeartRate: peakHeartRate,
            hrZoneSeconds: hrZoneSeconds,
            heartRateSamples: heartRateSamples,
            distanceMeters: nil // deferred v1
        )
    }

    /// Keep ~1 sample per `decimationIntervalSeconds`, capped at `maxHRSamplesPerWorkout`.
    /// Input is assumed sorted ascending by `startDate`.
    private func decimate(_ samples: [HKQuantitySample]) -> [HKQuantitySample] {
        guard !samples.isEmpty else { return [] }
        var result: [HKQuantitySample] = []
        var lastKept: Date?
        for sample in samples {
            if let last = lastKept, sample.startDate.timeIntervalSince(last) < Self.decimationIntervalSeconds {
                continue
            }
            result.append(sample)
            lastKept = sample.startDate
            if result.count >= Self.maxHRSamplesPerWorkout { break }
        }
        return result
    }

    /// HR-zone seconds from `220 − age`: walk consecutive samples, attribute each inter-sample
    /// interval to the earlier sample's zone. Returns `nil` when age is unknown (zones can't be
    /// computed) — the import still proceeds with avg/peak + raw samples.
    private func zoneSeconds(from samples: [HKQuantitySample], age: Int?) -> [String: Int]? {
        guard let age = age, age > 0, samples.count >= 2 else { return nil }
        let maxHR = Double(220 - age)
        guard maxHR > 0 else { return nil }

        var zones: [String: Int] = [:]
        for index in 0..<(samples.count - 1) {
            let interval = samples[index + 1].startDate.timeIntervalSince(samples[index].startDate)
            guard interval > 0, interval < 600 else { continue } // skip gaps (paused workouts etc.)
            let bpm = samples[index].quantity.doubleValue(for: Self.hrUnit)
            zones[Self.zoneKey(forPercent: bpm / maxHR), default: 0] += Int(interval.rounded())
        }
        return zones.isEmpty ? nil : zones
    }

    /// %MaxHR → zone key. Endpoints match Chunk D's bar: z1 <60, z2 60–70, z3 70–80, z4 80–90, z5 90+.
    private static func zoneKey(forPercent percent: Double) -> String {
        switch percent {
        case ..<0.60: return "z1"
        case ..<0.70: return "z2"
        case ..<0.80: return "z3"
        case ..<0.90: return "z4"
        default: return "z5"
        }
    }

    // MARK: - Private Helpers

    private func fetchSum(_ identifier: HKQuantityTypeIdentifier, start: Date, end: Date) async -> Double {
        guard let type = HKQuantityType.quantityType(forIdentifier: identifier) else {
            return 0
        }

        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)
        let unit = self.unit(for: identifier)  // Capture before closure to avoid actor isolation issues

        return await withCheckedContinuation { continuation in
            let query = HKStatisticsQuery(
                quantityType: type,
                quantitySamplePredicate: predicate,
                options: .cumulativeSum
            ) { _, result, error in
                if error != nil {
                    continuation.resume(returning: 0)
                    return
                }

                let value = result?.sumQuantity()?.doubleValue(for: unit) ?? 0
                continuation.resume(returning: value)
            }
            healthStore.execute(query)
        }
    }

    private func fetchStandHours(start: Date, end: Date) async -> Int {
        guard let type = HKCategoryType.categoryType(forIdentifier: .appleStandHour) else {
            return 0
        }

        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)

        return await withCheckedContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: type,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: nil
            ) { _, samples, error in
                if error != nil {
                    continuation.resume(returning: 0)
                    return
                }

                let standCount = (samples as? [HKCategorySample])?.filter {
                    $0.value == HKCategoryValueAppleStandHour.stood.rawValue
                }.count ?? 0

                continuation.resume(returning: standCount)
            }
            healthStore.execute(query)
        }
    }

    private func unit(for identifier: HKQuantityTypeIdentifier) -> HKUnit {
        switch identifier {
        case .stepCount:
            return .count()
        case .activeEnergyBurned, .basalEnergyBurned:
            return .kilocalorie()
        case .appleExerciseTime:
            return .minute()
        default:
            return .count()
        }
    }

    private func dateFromISO(_ string: String) -> Date? {
        // Use the robust parseISO8601Date() from Extensions.swift
        // which handles full ISO8601, date-only, and various other formats
        return string.parseISO8601Date()
    }
}

// MARK: - Data Models

struct DailyHealthData {
    let date: Date
    let steps: Int
    let activeCalories: Int
    let totalCalories: Int
    let exerciseMinutes: Int
    let standHours: Int
    let moveCalories: Int

    func toActivityCreate() -> ActivityCreate {
        // Use local timezone DateFormatter so the date reflects user's local date
        let dateString = DateFormatter.localDate.string(from: date)

        return ActivityCreate(
            date: dateString,
            source: ActivitySource.appleFitness.rawValue,
            steps: steps,
            activeCalories: activeCalories,
            totalCalories: totalCalories,
            activeMinutes: nil,
            exerciseMinutes: exerciseMinutes,
            standHours: standHours,
            moveCalories: moveCalories,
            strain: nil,
            recoveryScore: nil,
            hrv: nil,
            restingHeartRate: nil,
            sleepHours: nil
        )
    }
}
