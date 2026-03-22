import SwiftUI

extension Color {
    // MARK: - Brand Colors

    /// #1B3A5C — Hero card, buttons, active tab
    static let departPrimary = Color(red: 0x1B / 255, green: 0x3A / 255, blue: 0x5C / 255)

    /// #2D5F8A — Gradients
    static let departPrimaryLight = Color(red: 0x2D / 255, green: 0x5F / 255, blue: 0x8A / 255)

    // MARK: - Backgrounds

    /// #F2F2F7 — App background (iOS system gray 6)
    static let departBackground = Color(uiColor: .systemGroupedBackground)

    /// #FFFFFF — Cards, sheets
    static let departSurface = Color(uiColor: .secondarySystemGroupedBackground)

    // MARK: - Text

    /// #1C1C1E — Headlines, body
    static let departTextPrimary = Color(uiColor: .label)

    /// #8E8E93 — Captions, labels
    static let departTextSecondary = Color(uiColor: .secondaryLabel)

    // MARK: - Traffic / Status

    /// #4CD964 — Light traffic, on-time
    static let departGreen = Color(red: 0x4C / 255, green: 0xD9 / 255, blue: 0x64 / 255)

    /// #FFCC02 — Moderate traffic, prepare
    static let departYellow = Color(red: 0xFF / 255, green: 0xCC / 255, blue: 0x02 / 255)

    /// #FF9500 — Increasing traffic, leave soon
    static let departOrange = Color(red: 0xFF / 255, green: 0x95 / 255, blue: 0x00 / 255)

    /// #FF3B30 — Heavy traffic, leave now, urgent
    static let departRed = Color(red: 0xFF / 255, green: 0x3B / 255, blue: 0x30 / 255)

    // MARK: - Other

    /// #E5E5EA — Dividers, separators
    static let departBorder = Color(uiColor: .separator)

    // MARK: - Hero Card Gradient

    static var heroGradient: LinearGradient {
        LinearGradient(
            colors: [.departPrimary, .departPrimaryLight],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}

// MARK: - Urgency Colors

extension Trip.UrgencyLevel {
    var color: Color {
        switch self {
        case .normal: return .departGreen
        case .warning: return .departYellow
        case .critical: return .departRed
        case .overdue: return .departRed
        }
    }
}

extension CongestionLevel {
    var color: Color {
        switch self {
        case .unknown: return .departTextSecondary
        case .light: return .departGreen
        case .moderate: return .departYellow
        case .heavy: return .departOrange
        case .severe: return .departRed
        }
    }
}
