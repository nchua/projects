import Foundation

/// Client-side mirror of `backend/app/services/hunt_name_service.py`.
///
/// Used only to seed the Hunt Name field while logging (the exercises aren't
/// on the server yet). Saved sessions get their `suggested_name` from the
/// backend, so keep the two implementations in sync.
enum HuntNameSuggester {

    /// Seeded primary_muscle values -> the coarse group shown in a name.
    private static let displayGroup: [String: String] = [
        "chest": "Chest",
        "upper chest": "Chest",
        "lower chest": "Chest",
        "shoulders": "Shoulders",
        "front delts": "Shoulders",
        "side delts": "Shoulders",
        "rear delts": "Shoulders",
        "triceps": "Triceps",
        "back": "Back",
        "lats": "Back",
        "traps": "Back",
        "lower back": "Back",
        "biceps": "Biceps",
        "forearms": "Forearms",
        "quads": "Legs",
        "hamstrings": "Legs",
        "glutes": "Legs",
        "calves": "Legs",
        "adductors": "Legs",
        "legs": "Legs",
        "core": "Core",
        "abs": "Core",
        "lower abs": "Core",
        "obliques": "Core"
    ]

    private static let push: Set<String> = ["Chest", "Shoulders", "Triceps"]
    private static let pull: Set<String> = ["Back", "Biceps", "Forearms"]

    /// Suggested hunt name from the primary muscles of the selected
    /// exercises (in order), or nil when there's no signal.
    static func suggest(primaryMuscles: [String]) -> String? {
        var groups: [String] = []
        for muscle in primaryMuscles {
            let trimmed = muscle.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty else { continue }
            let group = displayGroup[trimmed.lowercased()] ?? trimmed.capitalized
            if !groups.contains(group) {
                groups.append(group)
            }
        }

        // Core and Full Body are usually accessories to the real focus —
        // drop them when anything more specific was trained.
        let specific = groups.filter { $0 != "Core" && $0 != "Full Body" }
        if specific.isEmpty {
            if groups.contains("Full Body") { return "Full Body Day" }
            if groups.contains("Core") { return "Core Day" }
            return nil
        }

        if specific.count == 1 {
            return specific[0] == "Legs" ? "Leg Day" : "\(specific[0]) Day"
        }
        if specific.count == 2 {
            return "\(specific[0]) & \(specific[1]) Day"
        }

        // 3+ groups: fall back to the classic split buckets.
        let distinct = Set(specific)
        if distinct.isSubset(of: push) { return "Push Day" }
        if distinct.isSubset(of: pull) { return "Pull Day" }
        if distinct.isSubset(of: push.union(pull)) { return "Upper Body Day" }
        return "Full Body Day"
    }
}
