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
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone.current
        let dateString = formatter.string(from: date)

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
