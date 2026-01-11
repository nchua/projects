import SwiftUI

/// Compact PR celebration overlay
/// Shows when user achieves a new personal record
struct PRCelebrationView: View {
    let exerciseName: String
    let prType: PRType
    let value: String  // e.g., "225 lb" or "315 lb x 5"
    let onDismiss: () -> Void

    // Optional counter for multiple PRs (e.g., "1 of 3")
    var currentIndex: Int = 1
    var totalCount: Int = 1

    enum PRType {
        case e1rm      // New estimated 1RM
        case repPR     // New rep PR at a weight

        var label: String {
            switch self {
            case .e1rm: return "NEW E1RM"
            case .repPR: return "REP PR"
            }
        }

        var icon: String {
            switch self {
            case .e1rm: return "crown.fill"
            case .repPR: return "flame.fill"
            }
        }
    }

    @State private var showCard = false
    @State private var showContent = false
    @State private var iconScale: CGFloat = 0.5
    @State private var shimmerOffset: CGFloat = -200

    var body: some View {
        VStack {
            Spacer()

            // PR Card
            VStack(spacing: 16) {
                // Trophy icon with glow
                ZStack {
                    // Glow background
                    Circle()
                        .fill(Color.gold.opacity(0.3))
                        .frame(width: 70, height: 70)
                        .blur(radius: 15)

                    // Icon
                    Image(systemName: prType.icon)
                        .font(.system(size: 32, weight: .bold))
                        .foregroundColor(.gold)
                        .scaleEffect(iconScale)
                }

                // PR Type label
                Text(prType.label)
                    .font(.ariseMono(size: 11, weight: .semibold))
                    .foregroundColor(.gold)
                    .tracking(2)
                    .opacity(showContent ? 1 : 0)

                // Exercise name
                Text(exerciseName.uppercased())
                    .font(.ariseHeader(size: 18, weight: .bold))
                    .foregroundColor(.textPrimary)
                    .multilineTextAlignment(.center)
                    .opacity(showContent ? 1 : 0)

                // Value
                Text(value)
                    .font(.ariseDisplay(size: 36, weight: .bold))
                    .foregroundColor(.gold)
                    .shadow(color: .gold.opacity(0.5), radius: 15, x: 0, y: 0)
                    .opacity(showContent ? 1 : 0)
                    .scaleEffect(showContent ? 1 : 0.8)

                // XP bonus
                HStack(spacing: 4) {
                    Image(systemName: "plus")
                        .font(.system(size: 12, weight: .bold))
                    Text("100 XP")
                        .font(.ariseMono(size: 14, weight: .bold))
                }
                .foregroundColor(.systemPrimary)
                .opacity(showContent ? 1 : 0)

                // Counter badge for multiple PRs
                if totalCount > 1 {
                    Text("\(currentIndex) of \(totalCount) PRs")
                        .font(.ariseMono(size: 12))
                        .foregroundColor(.textSecondary)
                        .padding(.top, 8)
                        .opacity(showContent ? 1 : 0)
                }
            }
            .padding(.vertical, 32)
            .padding(.horizontal, 48)
            .background(
                ZStack {
                    // Base background
                    Color.voidDark

                    // Shimmer effect
                    LinearGradient(
                        gradient: Gradient(colors: [
                            Color.clear,
                            Color.gold.opacity(0.1),
                            Color.clear
                        ]),
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                    .offset(x: shimmerOffset)
                    .mask(
                        RoundedRectangle(cornerRadius: 12)
                    )
                }
            )
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(
                        LinearGradient(
                            gradient: Gradient(colors: [
                                Color.gold.opacity(0.6),
                                Color.gold.opacity(0.2),
                                Color.gold.opacity(0.6)
                            ]),
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: 2
                    )
            )
            .shadow(color: .gold.opacity(0.3), radius: 30, x: 0, y: 10)
            .scaleEffect(showCard ? 1 : 0.8)
            .opacity(showCard ? 1 : 0)
            .padding(.horizontal, 32)

            Spacer()
                .frame(height: 100)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black.opacity(showCard ? 0.7 : 0))
        .onTapGesture {
            dismissWithAnimation()
        }
        .onAppear {
            startAnimations()
        }
    }

    private func startAnimations() {
        // Card appears
        withAnimation(.spring(response: 0.5, dampingFraction: 0.7)) {
            showCard = true
        }

        // Icon bounces
        withAnimation(.spring(response: 0.4, dampingFraction: 0.5).delay(0.2)) {
            iconScale = 1.0
        }

        // Content fades in
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            withAnimation(.easeOut(duration: 0.3)) {
                showContent = true
            }
        }

        // Shimmer effect
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            withAnimation(.easeInOut(duration: 1.0)) {
                shimmerOffset = 400
            }
        }

        // Auto-dismiss after 3 seconds
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) {
            dismissWithAnimation()
        }
    }

    private func dismissWithAnimation() {
        withAnimation(.easeOut(duration: 0.2)) {
            showCard = false
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
            onDismiss()
        }
    }
}

#Preview("E1RM PR") {
    PRCelebrationView(
        exerciseName: "Bench Press",
        prType: .e1rm,
        value: "225 lb",
        onDismiss: {}
    )
}

#Preview("Rep PR") {
    PRCelebrationView(
        exerciseName: "Squat",
        prType: .repPR,
        value: "315 lb × 5",
        onDismiss: {}
    )
}

#Preview("Multiple PRs - 2 of 3") {
    PRCelebrationView(
        exerciseName: "Deadlift",
        prType: .e1rm,
        value: "405 lb",
        onDismiss: {},
        currentIndex: 2,
        totalCount: 3
    )
}
