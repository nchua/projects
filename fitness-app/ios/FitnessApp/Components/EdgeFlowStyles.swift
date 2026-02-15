import SwiftUI

// MARK: - Edge Flow Card Style

/// View modifier for Edge Flow cards with left accent bar and optional glow
struct EdgeFlowCardStyle: ViewModifier {
    var accentColor: Color = .clear
    var hasGlow: Bool = false
    var cornerRadius: CGFloat = 20

    func body(content: Content) -> some View {
        content
            .background(Color.voidMedium)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .overlay(
                // Left accent bar
                HStack {
                    if accentColor != .clear {
                        RoundedRectangle(cornerRadius: cornerRadius)
                            .fill(accentColor)
                            .frame(width: 3)
                    }
                    Spacer()
                },
                alignment: .leading
            )
            .shadow(
                color: hasGlow && accentColor != .clear ? accentColor.opacity(0.2) : .clear,
                radius: 15, x: 0, y: 0
            )
    }
}

// MARK: - Pill Button Style

/// View modifier for pill-shaped buttons with gradient and glow
struct EdgeFlowPillButtonStyle: ViewModifier {
    var isPrimary: Bool

    func body(content: Content) -> some View {
        content
            .padding(.vertical, 14)
            .padding(.horizontal, 20)
            .frame(maxWidth: .infinity)
            .background(
                isPrimary
                    ? AnyView(LinearGradient(
                        colors: [Color(hex: "00D4FF"), Color(hex: "0099CC")],
                        startPoint: .leading,
                        endPoint: .trailing
                    ))
                    : AnyView(Color.voidMedium)
            )
            .foregroundColor(isPrimary ? .black : .white)
            .clipShape(Capsule())
            .overlay(
                !isPrimary ?
                    Capsule()
                        .stroke(Color.white.opacity(0.05), lineWidth: 1)
                : nil
            )
            .shadow(
                color: isPrimary ? Color.systemPrimary.opacity(0.4) : .clear,
                radius: 10, x: 0, y: 4
            )
    }
}

// MARK: - Edge Flow Stat Card

/// Compact stat card for horizontal scroll sections
struct EdgeFlowStatCard: View {
    let value: String
    let label: String
    var accentColor: Color? = nil

    var body: some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.system(size: 26, weight: .bold))
                .foregroundColor(accentColor ?? Color.systemPrimary)

            Text(label.uppercased())
                .font(.system(size: 11))
                .foregroundColor(.textSecondary)
        }
        .frame(minWidth: 100)
        .padding(16)
        .edgeFlowCard(accent: accentColor ?? .clear)
    }
}

// MARK: - View Extensions

extension View {
    /// Apply Edge Flow card styling with optional left accent bar and glow
    func edgeFlowCard(accent: Color = .clear, glow: Bool = false, cornerRadius: CGFloat = 20) -> some View {
        modifier(EdgeFlowCardStyle(accentColor: accent, hasGlow: glow, cornerRadius: cornerRadius))
    }

    /// Apply pill button styling
    func edgeFlowPillButton(isPrimary: Bool = true) -> some View {
        modifier(EdgeFlowPillButtonStyle(isPrimary: isPrimary))
    }
}
