import SwiftUI

/// ARISE stat card with icon, value, and label
struct StatCard: View {
    let icon: String  // Emoji or SF Symbol name
    let value: String
    let label: String
    var useSystemIcon: Bool = false
    var valueColor: Color = .systemPrimary
    var showGlow: Bool = true

    var body: some View {
        VStack(spacing: 8) {
            // Icon
            if useSystemIcon {
                Image(systemName: icon)
                    .font(.system(size: 20))
                    .foregroundColor(.textSecondary)
                    .accessibilityHidden(true)
            } else {
                Text(icon)
                    .font(.system(size: 20))
                    .accessibilityHidden(true)
            }

            // Value
            Text(value)
                .font(.ariseDisplay(size: 24, weight: .bold))
                .foregroundColor(valueColor)
                .if(showGlow) { view in
                    view.shadow(color: valueColor.opacity(0.4), radius: 10, x: 0, y: 0)
                }

            // Label
            Text(label)
                .font(.ariseMono(size: 10, weight: .medium))
                .foregroundColor(.textMuted)
                .textCase(.uppercase)
                .tracking(0.5)
        }
        .frame(maxWidth: .infinity)
        .padding(16)
        .background(Color.systemPrimarySubtle.opacity(0.2))
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.systemPrimarySubtle, lineWidth: 1)
        )
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(label)
        .accessibilityValue(value)
    }
}

#Preview {
    ZStack {
        VoidBackground()

        VStack(spacing: 12) {
            StatCard(icon: "flame.fill", value: "42", label: "Streak", useSystemIcon: true)
            StatCard(icon: "bolt.fill", value: "1,250", label: "Total XP", useSystemIcon: true)
        }
        .padding(24)
    }
}
