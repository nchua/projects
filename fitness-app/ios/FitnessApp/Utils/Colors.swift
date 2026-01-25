import SwiftUI

extension Color {
    // MARK: - ARISE Design System (Solo Leveling Theme)

    // ============================================
    // PRIMARY - The System Blue
    // ============================================
    static let systemPrimary = Color(hex: "00D4FF")              // Bright cyan - main brand
    static let systemPrimaryDim = Color(hex: "00A8CC")           // Dimmer variant
    static let systemPrimaryGlow = Color(hex: "00D4FF").opacity(0.4)  // Glow effect
    static let systemPrimarySubtle = Color(hex: "00D4FF").opacity(0.1) // Subtle backgrounds

    // ============================================
    // BACKGROUNDS - Void Black
    // ============================================
    static let voidBlack = Color(hex: "0A0A0F")                  // Deepest black - main bg
    static let voidDark = Color(hex: "12121A")                   // Dark layer
    static let voidMedium = Color(hex: "1A1A24")                 // Card backgrounds
    static let voidLight = Color(hex: "252530")                  // Elevated surfaces

    // ============================================
    // EDGE FLOW BACKGROUNDS - Softer dark palette
    // ============================================
    static let bgVoid = Color(hex: "050508")                     // Deepest background
    static let bgCard = Color(hex: "0f1018")                     // Card background
    static let bgElevated = Color(hex: "141520")                 // Elevated/header
    static let bgInput = Color(hex: "1a1b28")                    // Input fields

    // ============================================
    // GLOW COLORS - For Edge Flow shadows
    // ============================================
    static let glowPrimary = Color(hex: "00D4FF").opacity(0.4)   // Cyan glow
    static let glowSuccess = Color(hex: "00FF88").opacity(0.3)   // Green glow
    static let glowGold = Color(hex: "FFD700").opacity(0.3)      // Gold glow
    static let glowDanger = Color(hex: "FF4757").opacity(0.3)    // Red glow

    // ============================================
    // RANK COLORS - Hunter Classification
    // ============================================
    static let rankE = Color(hex: "808080")                      // Gray - E rank
    static let rankD = Color(hex: "4A9B4A")                      // Green - D rank
    static let rankC = Color(hex: "4A7BB5")                      // Blue - C rank
    static let rankB = Color(hex: "9B4A9B")                      // Purple - B rank
    static let rankA = Color(hex: "FFD700")                      // Gold - A rank
    static let rankS = Color(hex: "FF4444")                      // Red/Crimson - S rank

    // ============================================
    // STATUS & ALERT COLORS
    // ============================================
    static let successGreen = Color(hex: "33FF88")               // Quest complete
    static let warningRed = Color(hex: "FF3333")                 // Danger/warnings
    static let penaltyCrimson = Color(hex: "8B0000")             // Penalty/failure
    static let gold = Color(hex: "FFD700")                       // Rewards/currency

    // ============================================
    // TEXT COLORS
    // ============================================
    static let textPrimary = Color(hex: "FFFFFF")                // Main text
    static let textSecondary = Color(hex: "A0A0B0")              // Secondary emphasis
    static let textMuted = Color(hex: "606070")                  // Disabled/tertiary
    static let textSystem = Color(hex: "00D4FF")                 // System/mono text

    // ============================================
    // BORDER COLORS
    // ============================================
    static let ariseBorder = Color(hex: "00D4FF").opacity(0.2)   // Panel borders
    static let ariseBorderLight = Color(hex: "00D4FF").opacity(0.1) // Subtle borders

    // ============================================
    // EXERCISE TYPE COLORS (Lift-specific)
    // ============================================
    static let liftSquat = Color(hex: "3B82F6")                  // Blue
    static let liftBench = Color(hex: "EF4444")                  // Red
    static let liftDeadlift = Color(hex: "8B5CF6")               // Violet
    static let liftRow = Color(hex: "22C55E")                    // Green
    static let liftOHP = Color(hex: "EC4899")                    // Pink
    static let liftCurl = Color(hex: "A855F7")                   // Purple
    static let liftPullup = Color(hex: "F59E0B")                 // Amber
    static let liftRDL = Color(hex: "00D4FF")                    // Cyan (updated)

    // ============================================
    // GRADIENTS
    // ============================================

    // System panel background gradient
    static let gradientVoid = LinearGradient(
        colors: [
            Color(hex: "1A1A24").opacity(0.95),
            Color(hex: "12121A").opacity(0.98)
        ],
        startPoint: .top,
        endPoint: .bottom
    )

    // Primary accent gradient
    static let gradientSystem = LinearGradient(
        colors: [Color(hex: "00A8CC"), Color(hex: "00D4FF")],
        startPoint: .leading,
        endPoint: .trailing
    )

    // XP bar fill gradient
    static let gradientXP = LinearGradient(
        colors: [Color(hex: "1A4A5E"), Color(hex: "00D4FF")],
        startPoint: .leading,
        endPoint: .trailing
    )

    // Progress bar gradient
    static let gradientProgress = LinearGradient(
        colors: [systemPrimaryDim, systemPrimary],
        startPoint: .leading,
        endPoint: .trailing
    )

    // Rank gradients for special effects
    static let gradientGold = LinearGradient(
        colors: [Color(hex: "B8860B"), Color(hex: "FFD700")],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    static let gradientCrimson = LinearGradient(
        colors: [Color(hex: "8B0000"), Color(hex: "FF4444")],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    // ============================================
    // EDGE FLOW GRADIENTS
    // ============================================

    // Primary action button gradient
    static let gradientActionPrimary = LinearGradient(
        colors: [Color(hex: "00D4FF"), Color(hex: "0099CC")],
        startPoint: .leading,
        endPoint: .trailing
    )

    // Success/claim button gradient
    static let gradientActionSuccess = LinearGradient(
        colors: [Color(hex: "00FF88"), Color(hex: "00CC6A")],
        startPoint: .leading,
        endPoint: .trailing
    )

    // Header fade gradient (elevated to void)
    static let gradientHeaderFade = LinearGradient(
        colors: [bgElevated, bgVoid],
        startPoint: .top,
        endPoint: .bottom
    )

    // ============================================
    // LEGACY ALIASES (Backward Compatibility)
    // ============================================
    static let appPrimary = systemPrimary
    static let appBackground = voidBlack
    static let appSurface = voidDark
    static let appCard = voidMedium
    static let appElevated = voidLight
    static let appInput = voidLight
    static let appBorder = ariseBorder
    static let appBorderLight = ariseBorderLight
    static let appPrimaryMuted = systemPrimarySubtle
    static let appSecondary = systemPrimary
    static let appSuccess = successGreen
    static let appWarning = gold
    static let appDanger = warningRed
    static let appEnergy = Color(hex: "F97316")
    static let appStrength = Color(hex: "EF4444")
    static let appCardio = successGreen
    static let appRecovery = Color(hex: "8B5CF6")
    static let appGoal = gold
    static let textTertiary = textMuted

    // Legacy gradients
    static let gradientPrimary = gradientSystem
    static let gradientEnergy = LinearGradient(
        colors: [Color(hex: "F97316"), Color(hex: "EF4444")],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )
    static let gradientStrength = LinearGradient(
        colors: [Color(hex: "EF4444"), Color(hex: "EC4899")],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )
    static let gradientCardio = LinearGradient(
        colors: [successGreen, systemPrimary],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    // Initialize from hex string
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }

    // Helper to get exercise color based on name
    static func exerciseColor(for name: String) -> Color {
        let lowercased = name.lowercased()
        if lowercased.contains("squat") { return .liftSquat }
        if lowercased.contains("bench") { return .liftBench }
        if lowercased.contains("deadlift") && !lowercased.contains("romanian") { return .liftDeadlift }
        if lowercased.contains("row") { return .liftRow }
        if lowercased.contains("overhead") || lowercased.contains("ohp") || lowercased.contains("press") && !lowercased.contains("bench") { return .liftOHP }
        if lowercased.contains("curl") { return .liftCurl }
        if lowercased.contains("pull") { return .liftPullup }
        if lowercased.contains("romanian") || lowercased.contains("rdl") { return .liftRDL }
        return .systemPrimary
    }
}

// MARK: - Hunter Rank System

/// Hunter classification ranks from E (lowest) to S (highest)
enum HunterRank: String, CaseIterable, Codable {
    case e = "E"
    case d = "D"
    case c = "C"
    case b = "B"
    case a = "A"
    case s = "S"

    /// The color associated with this rank
    var color: Color {
        switch self {
        case .e: return .rankE
        case .d: return .rankD
        case .c: return .rankC
        case .b: return .rankB
        case .a: return .rankA
        case .s: return .rankS
        }
    }

    /// Text color for contrast on rank badge
    var textColor: Color {
        switch self {
        case .e, .d, .a: return .black
        case .c, .b, .s: return .white
        }
    }

    /// Fantasy title for the rank
    var title: String {
        switch self {
        case .e: return "Awakened"
        case .d: return "Hunter"
        case .c: return "Warrior"
        case .b: return "Elite"
        case .a: return "Commander"
        case .s: return "Shadow Monarch"
        }
    }

    /// Minimum level required for this rank (matches backend thresholds)
    var minLevel: Int {
        switch self {
        case .e: return 1
        case .d: return 11
        case .c: return 26
        case .b: return 46
        case .a: return 71
        case .s: return 91
        }
    }

    /// Get rank based on level (matches backend: xp_service.py RANK_THRESHOLDS)
    static func forLevel(_ level: Int) -> HunterRank {
        switch level {
        case 91...: return .s
        case 71..<91: return .a
        case 46..<71: return .b
        case 26..<46: return .c
        case 11..<26: return .d
        default: return .e
        }
    }

    /// Get rank based on lift strength standard (bodyweight multiplier)
    static func forStrengthStandard(_ bwMultiplier: Double, lift: String) -> HunterRank {
        // Strength standards vary by lift
        let lowerLift = lift.lowercased()

        if lowerLift.contains("squat") {
            switch bwMultiplier {
            case 2.5...: return .s
            case 2.0..<2.5: return .a
            case 1.5..<2.0: return .b
            case 1.25..<1.5: return .c
            case 1.0..<1.25: return .d
            default: return .e
            }
        } else if lowerLift.contains("bench") {
            switch bwMultiplier {
            case 2.0...: return .s
            case 1.5..<2.0: return .a
            case 1.25..<1.5: return .b
            case 1.0..<1.25: return .c
            case 0.75..<1.0: return .d
            default: return .e
            }
        } else if lowerLift.contains("deadlift") {
            switch bwMultiplier {
            case 3.0...: return .s
            case 2.5..<3.0: return .a
            case 2.0..<2.5: return .b
            case 1.5..<2.0: return .c
            case 1.25..<1.5: return .d
            default: return .e
            }
        } else {
            // Default standards
            switch bwMultiplier {
            case 2.0...: return .s
            case 1.5..<2.0: return .a
            case 1.25..<1.5: return .b
            case 1.0..<1.25: return .c
            case 0.75..<1.0: return .d
            default: return .e
            }
        }
    }
}

// MARK: - Fantasy Exercise Names

/// Maps exercise names to Solo Leveling themed fantasy names
struct ExerciseFantasyNames {
    static let mapping: [String: String] = [
        "squat": "Earth Shaker",
        "back squat": "Earth Shaker",
        "bench press": "Titan's Press",
        "bench": "Titan's Press",
        "deadlift": "Grave Riser",
        "barbell row": "Serpent's Pull",
        "row": "Serpent's Pull",
        "overhead press": "Sky Piercer",
        "ohp": "Sky Piercer",
        "shoulder press": "Sky Piercer",
        "barbell curl": "Iron Coil",
        "curl": "Iron Coil",
        "tricep pulldown": "Shadow Strike",
        "tricep": "Shadow Strike",
        "pull-up": "Ascension",
        "pullup": "Ascension",
        "chin-up": "Ascension",
        "romanian deadlift": "Dark Harvest",
        "rdl": "Dark Harvest",
        "leg press": "Mountain Crusher",
        "lat pulldown": "Wing Fury",
        "dumbbell press": "Twin Hammers",
        "incline bench": "Rising Force",
        "dip": "Descent of Shadows",
        "lunge": "Stalker's Stride"
    ]

    static func fantasyName(for exercise: String) -> String {
        let lowercased = exercise.lowercased()
        for (key, value) in mapping {
            if lowercased.contains(key) {
                return value
            }
        }
        return exercise // Return original if no mapping found
    }
}
