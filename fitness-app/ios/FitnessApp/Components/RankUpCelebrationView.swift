import SwiftUI

/// Full-screen dramatic rank-up celebration
/// Shows when user advances to a new rank (E→D→C→B→A→S)
struct RankUpCelebrationView: View {
    let previousRank: HunterRank
    let newRank: HunterRank
    let newLevel: Int
    let onContinue: () -> Void

    @State private var showOverlay = false
    @State private var showRankUp = false
    @State private var showOldRank = false
    @State private var showTransition = false
    @State private var showNewRank = false
    @State private var showTitle = false
    @State private var showContinue = false
    @State private var pulseScale: CGFloat = 1.0
    @State private var glowOpacity: Double = 0.3

    var body: some View {
        ZStack {
            // Animated background with rank color glow
            Color.black
                .ignoresSafeArea()
                .opacity(showOverlay ? 0.95 : 0)

            // Radial glow in new rank color
            RadialGradient(
                gradient: Gradient(colors: [
                    newRank.color.opacity(glowOpacity),
                    Color.clear
                ]),
                center: .center,
                startRadius: 50,
                endRadius: 400
            )
            .ignoresSafeArea()
            .opacity(showNewRank ? 1 : 0)

            VStack(spacing: 32) {
                Spacer()

                // "RANK UP!" header
                VStack(spacing: 8) {
                    Text("RANK UP!")
                        .font(.ariseDisplay(size: 48, weight: .bold))
                        .foregroundColor(newRank.color)
                        .shadow(color: newRank.color.opacity(0.8), radius: 30, x: 0, y: 0)
                        .shadow(color: newRank.color.opacity(0.5), radius: 60, x: 0, y: 0)
                        .scaleEffect(showRankUp ? 1 : 0.3)
                        .opacity(showRankUp ? 1 : 0)

                    Text("LEVEL \(newLevel)")
                        .font(.ariseMono(size: 14, weight: .semibold))
                        .foregroundColor(.textSecondary)
                        .tracking(3)
                        .opacity(showRankUp ? 1 : 0)
                }

                // Rank transition animation
                HStack(spacing: 24) {
                    // Old rank (fading out)
                    VStack(spacing: 8) {
                        RankBadgeView(rank: previousRank, size: .large)
                            .opacity(0.5)

                        Text("\(previousRank.rawValue)-RANK")
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.textMuted)
                    }
                    .opacity(showOldRank ? 1 : 0)
                    .offset(x: showTransition ? -20 : 0)

                    // Arrow
                    Image(systemName: "arrow.right")
                        .font(.system(size: 24, weight: .bold))
                        .foregroundColor(newRank.color)
                        .opacity(showTransition ? 1 : 0)
                        .scaleEffect(showTransition ? 1 : 0.5)

                    // New rank (appearing with glow)
                    VStack(spacing: 8) {
                        ZStack {
                            // Pulsing glow behind badge
                            Circle()
                                .fill(newRank.color.opacity(0.3))
                                .frame(width: 100, height: 100)
                                .scaleEffect(pulseScale)
                                .blur(radius: 20)

                            RankBadgeView(rank: newRank, size: .large)
                                .scaleEffect(showNewRank ? 1 : 0.5)
                        }

                        Text("\(newRank.rawValue)-RANK")
                            .font(.ariseMono(size: 14, weight: .bold))
                            .foregroundColor(newRank.color)
                    }
                    .opacity(showNewRank ? 1 : 0)
                    .offset(x: showTransition ? 20 : 0)
                }
                .padding(.vertical, 24)

                // Fantasy title
                VStack(spacing: 4) {
                    Text("YOU ARE NOW A")
                        .font(.ariseMono(size: 11))
                        .foregroundColor(.textMuted)
                        .tracking(2)

                    Text(newRank.title.uppercased())
                        .font(.ariseHeader(size: 28, weight: .bold))
                        .foregroundColor(newRank.color)
                        .shadow(color: newRank.color.opacity(0.5), radius: 15, x: 0, y: 0)
                        .tracking(1)
                }
                .opacity(showTitle ? 1 : 0)
                .scaleEffect(showTitle ? 1 : 0.9)

                Spacer()

                // Continue button
                Button {
                    onContinue()
                } label: {
                    HStack(spacing: 8) {
                        Text("CONTINUE")
                            .font(.ariseHeader(size: 16, weight: .bold))
                            .tracking(2)

                        Image(systemName: "arrow.right")
                            .font(.system(size: 14, weight: .bold))
                    }
                    .foregroundColor(.voidBlack)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(newRank.color)
                    .cornerRadius(4)
                }
                .padding(.horizontal, 32)
                .opacity(showContinue ? 1 : 0)
                .offset(y: showContinue ? 0 : 20)
            }
            .padding(.bottom, 48)
        }
        .onAppear {
            startAnimationSequence()
        }
    }

    private func startAnimationSequence() {
        // Fade in overlay
        withAnimation(.easeOut(duration: 0.3)) {
            showOverlay = true
        }

        // Show "RANK UP!" with spring
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            withAnimation(.spring(response: 0.5, dampingFraction: 0.6)) {
                showRankUp = true
            }
        }

        // Show old rank
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
            withAnimation(.easeOut(duration: 0.3)) {
                showOldRank = true
            }
        }

        // Transition animation
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
            withAnimation(.spring(response: 0.4, dampingFraction: 0.7)) {
                showTransition = true
            }
        }

        // New rank appears
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            withAnimation(.spring(response: 0.5, dampingFraction: 0.6)) {
                showNewRank = true
            }
            // Start pulsing glow
            startPulseAnimation()
        }

        // Show title
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            withAnimation(.spring(response: 0.4, dampingFraction: 0.7)) {
                showTitle = true
            }
        }

        // Show continue button
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
            withAnimation(.easeOut(duration: 0.3)) {
                showContinue = true
            }
        }
    }

    private func startPulseAnimation() {
        // Continuous pulse animation
        withAnimation(.easeInOut(duration: 1.5).repeatForever(autoreverses: true)) {
            pulseScale = 1.3
            glowOpacity = 0.5
        }
    }
}

#Preview("E to D Rank") {
    RankUpCelebrationView(
        previousRank: .e,
        newRank: .d,
        newLevel: 11,
        onContinue: {}
    )
}

#Preview("B to A Rank") {
    RankUpCelebrationView(
        previousRank: .b,
        newRank: .a,
        newLevel: 71,
        onContinue: {}
    )
}

#Preview("A to S Rank") {
    RankUpCelebrationView(
        previousRank: .a,
        newRank: .s,
        newLevel: 91,
        onContinue: {}
    )
}
