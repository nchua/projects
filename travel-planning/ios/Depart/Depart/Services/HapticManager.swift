import UIKit

/// Centralized haptic feedback for key interactions.
enum HapticManager {
    private static let lightGenerator = UIImpactFeedbackGenerator(style: .light)
    private static let mediumGenerator = UIImpactFeedbackGenerator(style: .medium)
    private static let heavyGenerator = UIImpactFeedbackGenerator(style: .heavy)
    private static let selectionGenerator = UISelectionFeedbackGenerator()
    private static let notificationGenerator = UINotificationFeedbackGenerator()

    /// Light tap — buffer stepper increment/decrement.
    static func light() {
        lightGenerator.impactOccurred()
    }

    /// Medium tap — transport mode selection.
    static func medium() {
        mediumGenerator.impactOccurred()
    }

    /// Heavy tap — leave now alert.
    static func heavy() {
        heavyGenerator.impactOccurred()
    }

    /// Selection change — chip/toggle selection.
    static func selection() {
        selectionGenerator.selectionChanged()
    }

    /// Success — trip saved.
    static func success() {
        notificationGenerator.notificationOccurred(.success)
    }

    /// Warning — approaching departure.
    static func warning() {
        notificationGenerator.notificationOccurred(.warning)
    }

    /// Error — save failed.
    static func error() {
        notificationGenerator.notificationOccurred(.error)
    }
}
