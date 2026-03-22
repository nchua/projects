import SwiftUI

extension View {
    /// Card style: rounded corners, shadow, background.
    func departCard() -> some View {
        self
            .padding(16)
            .background(Color.departSurface)
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .shadow(color: .black.opacity(0.06), radius: 8, x: 0, y: 2)
    }

    /// Section title style: uppercase, caption2, secondary text.
    func departSectionTitle() -> some View {
        self
            .font(.departCaption2)
            .foregroundStyle(Color.departTextSecondary)
            .textCase(.uppercase)
            .tracking(0.5)
    }
}
