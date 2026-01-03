import SwiftUI

// MARK: - ARISE Typography System
// Fonts: Orbitron (display), Rajdhani (headers), Inter (body), JetBrains Mono (system)
// Font files are in Resources/Fonts/ and registered in Info.plist

extension Font {

    // MARK: - Font Family Names
    private static let orbitronFamily = "Orbitron"
    private static let rajdhaniFamily = "Rajdhani"
    private static let interFamily = "Inter"
    private static let jetbrainsFamily = "JetBrains Mono"

    // MARK: - ARISE Display Font (Orbitron)
    // Used for: Large titles, stat values, rank badges, level numbers

    static func ariseDisplay(size: CGFloat, weight: Font.Weight = .bold) -> Font {
        // Orbitron is a variable font - use family name with weight
        if let _ = UIFont(name: "Orbitron-Regular", size: size) {
            return .custom(orbitronFamily, size: size).weight(weight)
        }
        // Fallback to system font with similar characteristics
        return .system(size: size, weight: weight, design: .monospaced)
    }

    // MARK: - ARISE Header Font (Rajdhani)
    // Used for: Section headers, lift names, quest titles, navigation

    static func ariseHeader(size: CGFloat, weight: Font.Weight = .semibold) -> Font {
        let fontName = rajdhaniFontName(for: weight)
        if UIFont(name: fontName, size: size) != nil {
            return .custom(fontName, size: size)
        }
        // Fallback to system font
        return .system(size: size, weight: weight, design: .default)
    }

    private static func rajdhaniFontName(for weight: Font.Weight) -> String {
        switch weight {
        case .light: return "Rajdhani-Light"
        case .regular: return "Rajdhani-Regular"
        case .medium: return "Rajdhani-Medium"
        case .semibold: return "Rajdhani-SemiBold"
        case .bold, .heavy, .black: return "Rajdhani-Bold"
        default: return "Rajdhani-Regular"
        }
    }

    // MARK: - ARISE Body Font (Inter)
    // Used for: General text, descriptions, instructions

    static func ariseBody(size: CGFloat, weight: Font.Weight = .regular) -> Font {
        // Inter is a variable font - use family name with weight
        if let _ = UIFont(name: "Inter-Regular", size: size) {
            return .custom(interFamily, size: size).weight(weight)
        }
        // Fallback to system font
        return .system(size: size, weight: weight, design: .default)
    }

    // MARK: - ARISE Mono Font (JetBrains Mono)
    // Used for: System tags, metrics, timestamps, code-like text

    static func ariseMono(size: CGFloat, weight: Font.Weight = .regular) -> Font {
        let fontName = jetbrainsFontName(for: weight)
        if UIFont(name: fontName, size: size) != nil {
            return .custom(fontName, size: size)
        }
        // Fallback to system monospaced font
        return .system(size: size, weight: weight, design: .monospaced)
    }

    private static func jetbrainsFontName(for weight: Font.Weight) -> String {
        switch weight {
        case .regular: return "JetBrainsMono-Regular"
        case .medium: return "JetBrainsMono-Medium"
        case .semibold: return "JetBrainsMono-SemiBold"
        case .bold, .heavy, .black: return "JetBrainsMono-Bold"
        default: return "JetBrainsMono-Regular"
        }
    }
}

// MARK: - Typography View Modifiers

extension View {

    /// ARISE display text style - uppercase, wide tracking
    func ariseDisplayStyle(size: CGFloat = 24) -> some View {
        self
            .font(.ariseDisplay(size: size, weight: .bold))
            .textCase(.uppercase)
            .tracking(size * 0.1) // 10% of font size
    }

    /// ARISE header text style - uppercase, moderate tracking
    func ariseHeaderStyle(size: CGFloat = 14) -> some View {
        self
            .font(.ariseHeader(size: size, weight: .semibold))
            .textCase(.uppercase)
            .tracking(size * 0.07) // 7% of font size
    }

    /// ARISE system/mono text style - cyan colored
    func ariseSystemStyle(size: CGFloat = 12) -> some View {
        self
            .font(.ariseMono(size: size, weight: .medium))
            .foregroundColor(.systemPrimary)
    }

    /// Text glow effect for display numbers
    func ariseGlow(color: Color = .systemPrimary, radius: CGFloat = 10) -> some View {
        self
            .shadow(color: color.opacity(0.4), radius: radius, x: 0, y: 0)
            .shadow(color: color.opacity(0.2), radius: radius * 2, x: 0, y: 0)
    }

    /// Subtle text glow
    func ariseGlowSubtle(color: Color = .systemPrimary) -> some View {
        self
            .shadow(color: color.opacity(0.4), radius: 10, x: 0, y: 0)
    }
}

// MARK: - Font Registration Helper

struct FontRegistration {
    /// Call this once at app startup to verify fonts are loaded
    static func verifyFonts() {
        #if DEBUG
        let requiredFonts = [
            ("Orbitron", "Orbitron-Regular"),
            ("Rajdhani", "Rajdhani-SemiBold"),
            ("Inter", "Inter-Regular"),
            ("JetBrains Mono", "JetBrainsMono-Regular")
        ]

        print("ARISE: Verifying custom fonts...")
        for (family, fontName) in requiredFonts {
            if UIFont(name: fontName, size: 12) != nil {
                print("  ✓ \(family) loaded successfully")
            } else {
                print("  ✗ \(family) not found - using fallback")
            }
        }
        #endif
    }

    /// List all available font families (for debugging)
    static func listAvailableFonts() {
        print("Available Font Families:")
        for family in UIFont.familyNames.sorted() {
            print("  \(family)")
            for name in UIFont.fontNames(forFamilyName: family) {
                print("    - \(name)")
            }
        }
    }

    /// List ARISE-related fonts only
    static func listARISEFonts() {
        let ariseFamilies = ["Orbitron", "Rajdhani", "Inter", "JetBrains Mono"]
        print("ARISE Fonts:")
        for family in UIFont.familyNames.sorted() {
            if ariseFamilies.contains(where: { family.contains($0) }) {
                print("  \(family)")
                for name in UIFont.fontNames(forFamilyName: family) {
                    print("    - \(name)")
                }
            }
        }
    }
}
