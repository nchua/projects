import Foundation

/// Client-side XP calculations that match the backend formula
/// This ensures XP display is always accurate without depending on cached API values
struct XPCalculator {
    /// XP required to reach a given level (matches backend: 100 * level^1.5)
    static func xpForLevel(_ level: Int) -> Int {
        return Int(100.0 * pow(Double(level), 1.5))
    }

    /// XP remaining to reach next level
    static func xpToNextLevel(currentLevel: Int, totalXp: Int) -> Int {
        let xpNeeded = xpForLevel(currentLevel + 1)
        return max(0, xpNeeded - totalXp)
    }

    /// Progress percentage toward next level (0.0 - 1.0)
    static func levelProgress(currentLevel: Int, totalXp: Int) -> Double {
        let xpForCurrent = xpForLevel(currentLevel)
        let xpForNext = xpForLevel(currentLevel + 1)
        let xpInLevel = totalXp - xpForCurrent
        let xpNeeded = xpForNext - xpForCurrent
        guard xpNeeded > 0 else { return 1.0 }
        return min(1.0, max(0.0, Double(xpInLevel) / Double(xpNeeded)))
    }
}
