import SwiftUI

// MARK: - ARISE View Extensions

extension View {

    // ============================================
    // ARISE SYSTEM PANEL STYLES
    // ============================================

    /// ARISE system panel with gradient background and glow border
    func systemPanelStyle(hasGlow: Bool = false) -> some View {
        self
            .padding(16)
            .background(Color.gradientVoid)
            .cornerRadius(4) // ARISE uses sharper corners
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
            .overlay(alignment: .top) {
                // Top gradient glow line (ARISE signature)
                LinearGradient(
                    colors: [.clear, .systemPrimary.opacity(0.6), .clear],
                    startPoint: .leading,
                    endPoint: .trailing
                )
                .frame(height: 1)
            }
            .modifier(ConditionalGlow(hasGlow: hasGlow))
    }

    /// Lift/Exercise card with colored left border
    func liftCardStyle(borderColor: Color) -> some View {
        self
            .padding(16)
            .background(Color.black.opacity(0.3))
            .overlay(alignment: .leading) {
                Rectangle()
                    .fill(borderColor)
                    .frame(width: 3)
            }
    }

    /// ARISE notification/tag style
    func notificationTagStyle() -> some View {
        self
            .font(.ariseMono(size: 12, weight: .medium))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Color.systemPrimarySubtle)
            .foregroundColor(.systemPrimary)
            .overlay(
                RoundedRectangle(cornerRadius: 2)
                    .stroke(Color.systemPrimary, lineWidth: 1)
            )
    }

    // ============================================
    // ARISE BUTTON STYLES
    // ============================================

    /// ARISE system button (squared edges, letter-spacing)
    func systemButtonStyle(isPrimary: Bool = false) -> some View {
        self
            .font(.ariseHeader(size: 16, weight: .semibold))
            .tracking(2)
            .textCase(.uppercase)
            .padding(.vertical, 16)
            .padding(.horizontal, 48)
            .background(isPrimary ? Color.systemPrimary : Color.clear)
            .foregroundColor(isPrimary ? .voidBlack : .systemPrimary)
            .overlay(
                Rectangle() // Sharp corners for ARISE
                    .stroke(Color.systemPrimary, lineWidth: 2)
            )
    }

    /// ARISE decline/cancel button
    func declineButtonStyle() -> some View {
        self
            .font(.ariseHeader(size: 16, weight: .semibold))
            .tracking(2)
            .textCase(.uppercase)
            .padding(.vertical, 16)
            .padding(.horizontal, 48)
            .background(Color.clear)
            .foregroundColor(.textMuted)
            .overlay(
                Rectangle()
                    .stroke(Color.textMuted, lineWidth: 2)
            )
    }

    // ============================================
    // ANIMATION MODIFIERS
    // ============================================

    /// Shimmer effect for progress bars
    func shimmer() -> some View {
        modifier(ShimmerModifier())
    }

    /// Pulse glow effect for active elements
    func pulseGlow(color: Color = .systemPrimary) -> some View {
        modifier(PulseGlowModifier(color: color))
    }

    /// Glitch effect for penalty/error states
    func glitch() -> some View {
        modifier(GlitchModifier())
    }

    /// Fade-in with delay for staggered reveals
    func fadeIn(delay: Double = 0) -> some View {
        modifier(FadeInModifier(delay: delay))
    }

    /// Slide in from right
    func slideInRight(delay: Double = 0) -> some View {
        modifier(SlideInRightModifier(delay: delay))
    }

    // ============================================
    // LEGACY STYLES (Backward Compatibility)
    // ============================================

    // Standard card style with border (legacy - maps to system panel)
    func cardStyle() -> some View {
        self
            .padding(16)
            .background(Color.voidMedium)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
    }

    // Elevated card with glow effect
    func elevatedCardStyle(glowColor: Color = .systemPrimary) -> some View {
        self
            .padding(16)
            .background(Color.voidMedium)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
            .shadow(color: glowColor.opacity(0.15), radius: 15, x: 0, y: 5)
    }

    // Compact card for list items
    func compactCardStyle() -> some View {
        self
            .padding(12)
            .background(Color.voidMedium)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
    }

    // Input field style
    func inputStyle() -> some View {
        self
            .padding(12)
            .background(Color.voidLight)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
    }

    // Badge style
    func badgeStyle(color: Color) -> some View {
        self
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(color.opacity(0.15))
            .cornerRadius(2)
            .overlay(
                RoundedRectangle(cornerRadius: 2)
                    .stroke(color.opacity(0.3), lineWidth: 1)
            )
    }

    // Primary button style (legacy - maps to system button)
    func primaryButtonStyle() -> some View {
        self
            .font(.ariseHeader(size: 15, weight: .semibold))
            .tracking(1)
            .foregroundColor(.voidBlack)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(Color.gradientSystem)
            .cornerRadius(4)
            .shadow(color: Color.systemPrimaryGlow, radius: 10, x: 0, y: 4)
    }

    // Secondary button style
    func secondaryButtonStyle() -> some View {
        self
            .font(.ariseHeader(size: 15, weight: .medium))
            .foregroundColor(.textSecondary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(Color.voidLight)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
    }

    // Pill/chip button style
    func pillStyle(isSelected: Bool, color: Color = .systemPrimary) -> some View {
        self
            .font(.ariseMono(size: 13, weight: .medium))
            .foregroundColor(isSelected ? .voidBlack : .textSecondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(isSelected ? color : Color.voidMedium)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(isSelected ? color : Color.ariseBorder, lineWidth: 1)
            )
    }

    // Exercise indicator bar
    func exerciseIndicator(color: Color) -> some View {
        Rectangle()
            .fill(color)
            .frame(width: 3) // ARISE uses 3px
    }

    func monospacedNumbers() -> some View {
        self.font(.ariseMono(size: 16))
    }

    // Stat value style (for numbers) - now uses ARISE display font
    func statValueStyle(size: CGFloat = 24) -> some View {
        self
            .font(.ariseDisplay(size: size, weight: .bold))
            .foregroundColor(.systemPrimary)
            .shadow(color: .systemPrimaryGlow, radius: 10, x: 0, y: 0)
    }

    // Section title style - now uses ARISE header font
    func sectionTitleStyle() -> some View {
        self
            .font(.ariseHeader(size: 13, weight: .semibold))
            .foregroundColor(.textSecondary)
            .textCase(.uppercase)
            .tracking(2)
    }

    // ============================================
    // HELPER MODIFIERS
    // ============================================

    /// Conditional modifier helper
    @ViewBuilder
    func `if`<Transform: View>(_ condition: Bool, transform: (Self) -> Transform) -> some View {
        if condition {
            transform(self)
        } else {
            self
        }
    }
}

// MARK: - Animation View Modifiers

/// Shimmer animation for progress bars
struct ShimmerModifier: ViewModifier {
    @State private var phase: CGFloat = -1

    func body(content: Content) -> some View {
        content
            .overlay(
                GeometryReader { geo in
                    LinearGradient(
                        colors: [.clear, .white.opacity(0.3), .clear],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                    .frame(width: geo.size.width * 0.5)
                    .offset(x: geo.size.width * phase)
                }
                .mask(content)
            )
            .onAppear {
                withAnimation(.linear(duration: 2).repeatForever(autoreverses: false)) {
                    phase = 2
                }
            }
    }
}

/// Pulse glow animation
struct PulseGlowModifier: ViewModifier {
    @State private var isAnimating = false
    let color: Color

    func body(content: Content) -> some View {
        content
            .shadow(color: color.opacity(isAnimating ? 0.6 : 0.2), radius: isAnimating ? 20 : 10, x: 0, y: 0)
            .shadow(color: color.opacity(isAnimating ? 0.3 : 0.1), radius: isAnimating ? 40 : 20, x: 0, y: 0)
            .onAppear {
                withAnimation(.easeInOut(duration: 2).repeatForever(autoreverses: true)) {
                    isAnimating = true
                }
            }
    }
}

/// Glitch effect for error states
struct GlitchModifier: ViewModifier {
    @State private var offset: CGFloat = 0
    @State private var hueRotation: Double = 0

    func body(content: Content) -> some View {
        content
            .offset(x: offset)
            .hueRotation(.degrees(hueRotation))
            .onAppear {
                Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { _ in
                    offset = CGFloat.random(in: -2...2)
                    hueRotation = Double.random(in: 0...90)
                }
            }
    }
}

/// Fade-in with delay
struct FadeInModifier: ViewModifier {
    let delay: Double
    @State private var opacity: Double = 0
    @State private var offsetY: CGFloat = 10

    func body(content: Content) -> some View {
        content
            .opacity(opacity)
            .offset(y: offsetY)
            .onAppear {
                withAnimation(.easeOut(duration: 0.5).delay(delay)) {
                    opacity = 1
                    offsetY = 0
                }
            }
    }
}

/// Slide in from right
struct SlideInRightModifier: ViewModifier {
    let delay: Double
    @State private var opacity: Double = 0
    @State private var offsetX: CGFloat = 100

    func body(content: Content) -> some View {
        content
            .opacity(opacity)
            .offset(x: offsetX)
            .onAppear {
                withAnimation(.easeOut(duration: 0.5).delay(delay)) {
                    opacity = 1
                    offsetX = 0
                }
            }
    }
}

/// Conditional glow helper
struct ConditionalGlow: ViewModifier {
    let hasGlow: Bool

    func body(content: Content) -> some View {
        if hasGlow {
            content
                .shadow(color: Color.systemPrimaryGlow.opacity(0.1), radius: 20, x: 0, y: 0)
        } else {
            content
        }
    }
}

// MARK: - Date Extensions

extension Date {
    var startOfDay: Date {
        Calendar.current.startOfDay(for: self)
    }

    var startOfWeek: Date {
        let calendar = Calendar.current
        let components = calendar.dateComponents([.yearForWeekOfYear, .weekOfYear], from: self)
        return calendar.date(from: components) ?? self
    }

    var endOfWeek: Date {
        let calendar = Calendar.current
        return calendar.date(byAdding: .day, value: 6, to: startOfWeek) ?? self
    }

    func daysAgo(_ days: Int) -> Date {
        Calendar.current.date(byAdding: .day, value: -days, to: self) ?? self
    }

    var formattedShort: String {
        let formatter = DateFormatter()
        formatter.dateStyle = .short
        return formatter.string(from: self)
    }

    var formattedMedium: String {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        return formatter.string(from: self)
    }

    var formattedRelative: String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: self, relativeTo: Date())
    }

    var formattedDayMonth: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "EEEE, MMMM d"
        return formatter.string(from: self)
    }

    var formattedMonthDay: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d, yyyy"
        return formatter.string(from: self)
    }
}

// MARK: - Double Extensions

extension Double {
    var formattedWeight: String {
        if self.truncatingRemainder(dividingBy: 1) == 0 {
            return String(format: "%.0f", self)
        } else {
            return String(format: "%.1f", self)
        }
    }

    var formattedE1RM: String {
        String(format: "%.1f", self)
    }

    var formattedPercentage: String {
        String(format: "%.1f%%", self)
    }

    var formattedVolume: String {
        if self >= 1000 {
            return String(format: "%.1fK", self / 1000)
        }
        return String(format: "%.0f", self)
    }
}

// MARK: - String Extensions

extension String {
    var isValidEmail: Bool {
        let emailRegex = "[A-Z0-9a-z._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,64}"
        let emailPredicate = NSPredicate(format: "SELF MATCHES %@", emailRegex)
        return emailPredicate.evaluate(with: self)
    }

    /// Formats ISO date string (YYYY-MM-DD) to readable format (Jan 15, 2025)
    var formattedDateString: String {
        let inputFormatter = DateFormatter()
        inputFormatter.dateFormat = "yyyy-MM-dd"

        let outputFormatter = DateFormatter()
        outputFormatter.dateStyle = .medium

        if let date = inputFormatter.date(from: self) {
            return outputFormatter.string(from: date)
        }
        return self
    }

    /// Parse ISO8601 date string to Date (handles both with and without fractional seconds)
    func parseISO8601Date() -> Date? {
        let formatterWithFraction = ISO8601DateFormatter()
        formatterWithFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatterWithFraction.date(from: self) {
            return date
        }

        let standardFormatter = ISO8601DateFormatter()
        return standardFormatter.date(from: self)
    }

    /// Formatted month-day from ISO8601 string
    var formattedMonthDayFromISO: String {
        parseISO8601Date()?.formattedMonthDay ?? self
    }
}

// MARK: - Array Extensions

extension Array {
    func chunked(into size: Int) -> [[Element]] {
        return stride(from: 0, to: count, by: size).map {
            Array(self[$0 ..< Swift.min($0 + size, count)])
        }
    }
}

// MARK: - Animation Extensions

extension Animation {
    static let smoothSpring = Animation.spring(response: 0.4, dampingFraction: 0.8)
    static let quickSpring = Animation.spring(response: 0.3, dampingFraction: 0.7)
}
