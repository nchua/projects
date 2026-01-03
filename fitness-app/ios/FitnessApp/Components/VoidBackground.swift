import SwiftUI

/// ARISE void background with radial glow and optional grid pattern
struct VoidBackground: View {
    var showGrid: Bool = true
    var showRadialGlow: Bool = true
    var glowIntensity: Double = 0.03

    var body: some View {
        ZStack {
            // Base void black
            Color.voidBlack

            // Radial cyan glow from top
            if showRadialGlow {
                RadialGradient(
                    colors: [
                        Color.systemPrimary.opacity(glowIntensity),
                        Color.clear
                    ],
                    center: .top,
                    startRadius: 0,
                    endRadius: UIScreen.main.bounds.height * 0.5
                )

                // Secondary glow from bottom-right
                RadialGradient(
                    colors: [
                        Color.systemPrimary.opacity(glowIntensity * 0.7),
                        Color.clear
                    ],
                    center: UnitPoint(x: 0.8, y: 0.8),
                    startRadius: 0,
                    endRadius: UIScreen.main.bounds.height * 0.4
                )
            }

            // Grid overlay
            if showGrid {
                GridPattern(spacing: 50)
                    .stroke(Color.systemPrimary.opacity(0.03), lineWidth: 1)
            }
        }
        .ignoresSafeArea()
    }
}

/// Grid pattern shape for ARISE background
struct GridPattern: Shape {
    let spacing: CGFloat

    func path(in rect: CGRect) -> Path {
        var path = Path()

        // Vertical lines
        for x in stride(from: 0, through: rect.width, by: spacing) {
            path.move(to: CGPoint(x: x, y: 0))
            path.addLine(to: CGPoint(x: x, y: rect.height))
        }

        // Horizontal lines
        for y in stride(from: 0, through: rect.height, by: spacing) {
            path.move(to: CGPoint(x: 0, y: y))
            path.addLine(to: CGPoint(x: rect.width, y: y))
        }

        return path
    }
}

/// ARISE divider with gradient glow
struct AriseDivider: View {
    var hasGlow: Bool = false

    var body: some View {
        LinearGradient(
            colors: [.clear, Color.systemPrimary.opacity(0.3), .clear],
            startPoint: .leading,
            endPoint: .trailing
        )
        .frame(height: hasGlow ? 2 : 1)
        .if(hasGlow) { view in
            view.shadow(color: .systemPrimaryGlow, radius: 10, x: 0, y: 0)
        }
    }
}

/// ARISE section header with diamond bullet
struct AriseSectionHeader: View {
    let title: String
    var trailing: AnyView? = nil

    var body: some View {
        HStack {
            HStack(spacing: 8) {
                Text("\u{25C6}") // Diamond character
                    .font(.system(size: 10))
                    .foregroundColor(.systemPrimary)

                Text(title)
                    .font(.ariseHeader(size: 14, weight: .semibold))
                    .foregroundColor(.textSecondary)
                    .textCase(.uppercase)
                    .tracking(2)
            }

            Spacer()

            if let trailing = trailing {
                trailing
            }
        }
    }
}

#Preview {
    ZStack {
        VoidBackground()

        VStack(spacing: 24) {
            AriseSectionHeader(title: "Hunter Status")

            AriseDivider()

            AriseSectionHeader(
                title: "Weekly Quest",
                trailing: AnyView(
                    Text("3/7 Days")
                        .font(.ariseMono(size: 12))
                        .foregroundColor(.systemPrimary)
                )
            )

            AriseDivider(hasGlow: true)
        }
        .padding()
    }
}
