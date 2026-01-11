import SwiftUI

struct DungeonRewardSheet: View {
    let result: DungeonClaimResponse
    @Environment(\.dismiss) private var dismiss
    @State private var showContent = false
    @State private var showXP = false
    @State private var showDetails = false

    var body: some View {
        ZStack {
            // Background
            Color.voidBlack.ignoresSafeArea()

            // Animated particles
            ParticleEmitterView()
                .opacity(showContent ? 1 : 0)

            VStack(spacing: 32) {
                Spacer()

                // Victory icon
                ZStack {
                    // Glow rings
                    ForEach(0..<3) { i in
                        Circle()
                            .stroke(Color.gold.opacity(0.2 - Double(i) * 0.06), lineWidth: 2)
                            .frame(width: 120 + CGFloat(i * 30), height: 120 + CGFloat(i * 30))
                            .scaleEffect(showContent ? 1 : 0.5)
                            .opacity(showContent ? 1 : 0)
                            .animation(.easeOut(duration: 0.8).delay(Double(i) * 0.1), value: showContent)
                    }

                    Circle()
                        .fill(Color.gold.opacity(0.2))
                        .frame(width: 100, height: 100)
                        .scaleEffect(showContent ? 1 : 0.5)

                    Image(systemName: "trophy.fill")
                        .font(.system(size: 48))
                        .foregroundColor(.gold)
                        .shadow(color: .gold.opacity(0.5), radius: 20, x: 0, y: 0)
                }
                .opacity(showContent ? 1 : 0)
                .scaleEffect(showContent ? 1 : 0.3)

                // Title
                VStack(spacing: 8) {
                    Text("[ DUNGEON CLEARED ]")
                        .font(.ariseMono(size: 12, weight: .semibold))
                        .foregroundColor(.gold)
                        .tracking(2)

                    Text("VICTORY")
                        .font(.ariseDisplay(size: 40, weight: .bold))
                        .foregroundColor(.textPrimary)
                        .shadow(color: .gold.opacity(0.3), radius: 10, x: 0, y: 0)
                }
                .opacity(showContent ? 1 : 0)

                // XP earned
                VStack(spacing: 16) {
                    // Total XP
                    HStack(alignment: .lastTextBaseline, spacing: 8) {
                        Text("+\(result.xpEarned)")
                            .font(.ariseDisplay(size: 56, weight: .bold))
                            .foregroundColor(.gold)
                            .shadow(color: .gold.opacity(0.5), radius: 15, x: 0, y: 0)

                        Text("XP")
                            .font(.ariseHeader(size: 24, weight: .semibold))
                            .foregroundColor(.textMuted)
                    }
                    .opacity(showXP ? 1 : 0)
                    .scaleEffect(showXP ? 1 : 0.8)

                    // Breakdown
                    if showDetails {
                        VStack(spacing: 8) {
                            if result.stretchBonusXp > 0 {
                                XPBreakdownRow(label: "Stretch Bonus", value: result.stretchBonusXp)
                            }
                            if result.bonusObjectivesXp > 0 {
                                XPBreakdownRow(label: "Bonus Objectives", value: result.bonusObjectivesXp)
                            }
                        }
                        .transition(.opacity.combined(with: .move(edge: .top)))
                    }
                }

                // Level up notification
                if result.leveledUp, let newLevel = result.newLevel {
                    LevelUpBanner(newLevel: newLevel)
                        .opacity(showDetails ? 1 : 0)
                        .offset(y: showDetails ? 0 : 20)
                }

                // Rank up notification
                if result.rankChanged, let newRank = result.newRank {
                    RankUpBanner(newRank: newRank)
                        .opacity(showDetails ? 1 : 0)
                        .offset(y: showDetails ? 0 : 20)
                }

                Spacer()

                // Close button
                Button {
                    dismiss()
                } label: {
                    Text("CONTINUE")
                        .font(.ariseHeader(size: 16, weight: .semibold))
                        .tracking(2)
                        .frame(maxWidth: .infinity)
                        .frame(height: 54)
                        .background(Color.gold)
                        .foregroundColor(.voidBlack)
                }
                .opacity(showDetails ? 1 : 0)
                .padding(.horizontal, 32)
                .padding(.bottom, 32)
            }
        }
        .onAppear {
            // Animate in sequence
            withAnimation(.easeOut(duration: 0.6)) {
                showContent = true
            }
            withAnimation(.easeOut(duration: 0.5).delay(0.4)) {
                showXP = true
            }
            withAnimation(.easeOut(duration: 0.4).delay(0.8)) {
                showDetails = true
            }

            // Haptic feedback
            let generator = UINotificationFeedbackGenerator()
            generator.notificationOccurred(.success)
        }
    }
}

// MARK: - XP Breakdown Row

struct XPBreakdownRow: View {
    let label: String
    let value: Int

    var body: some View {
        HStack {
            Text(label)
                .font(.ariseMono(size: 12))
                .foregroundColor(.textSecondary)

            Spacer()

            Text("+\(value) XP")
                .font(.ariseMono(size: 12, weight: .semibold))
                .foregroundColor(.gold)
        }
        .padding(.horizontal, 24)
    }
}

// MARK: - Level Up Banner

struct LevelUpBanner: View {
    let newLevel: Int

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "arrow.up.circle.fill")
                .font(.system(size: 24))
                .foregroundColor(.systemPrimary)

            VStack(alignment: .leading, spacing: 2) {
                Text("LEVEL UP!")
                    .font(.ariseMono(size: 10, weight: .bold))
                    .foregroundColor(.systemPrimary)
                    .tracking(1)

                Text("You reached Level \(newLevel)")
                    .font(.ariseHeader(size: 14, weight: .medium))
                    .foregroundColor(.textPrimary)
            }

            Spacer()

            Text("LV \(newLevel)")
                .font(.ariseDisplay(size: 24, weight: .bold))
                .foregroundColor(.systemPrimary)
        }
        .padding(16)
        .background(Color.systemPrimary.opacity(0.1))
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.systemPrimary.opacity(0.3), lineWidth: 1)
        )
        .padding(.horizontal, 24)
    }
}

// MARK: - Rank Up Banner

struct RankUpBanner: View {
    let newRank: String

    var rankColor: Color {
        switch newRank {
        case "E": return .rankE
        case "D": return .rankD
        case "C": return .rankC
        case "B": return .rankB
        case "A": return .rankA
        case "S": return .rankS
        default: return .textMuted
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "crown.fill")
                .font(.system(size: 24))
                .foregroundColor(rankColor)

            VStack(alignment: .leading, spacing: 2) {
                Text("RANK UP!")
                    .font(.ariseMono(size: 10, weight: .bold))
                    .foregroundColor(rankColor)
                    .tracking(1)

                Text("You are now \(newRank)-Rank")
                    .font(.ariseHeader(size: 14, weight: .medium))
                    .foregroundColor(.textPrimary)
            }

            Spacer()

            Text(newRank)
                .font(.ariseDisplay(size: 28, weight: .bold))
                .foregroundColor(rankColor)
                .padding(.horizontal, 12)
                .padding(.vertical, 4)
                .background(rankColor.opacity(0.2))
                .cornerRadius(4)
        }
        .padding(16)
        .background(rankColor.opacity(0.1))
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(rankColor.opacity(0.3), lineWidth: 1)
        )
        .padding(.horizontal, 24)
    }
}

// MARK: - Particle Emitter

struct ParticleEmitterView: View {
    @State private var particles: [Particle] = []

    struct Particle: Identifiable {
        let id = UUID()
        var x: CGFloat
        var y: CGFloat
        var size: CGFloat
        var opacity: Double
        var speed: Double
    }

    var body: some View {
        GeometryReader { geometry in
            ForEach(particles) { particle in
                Circle()
                    .fill(Color.gold)
                    .frame(width: particle.size, height: particle.size)
                    .position(x: particle.x, y: particle.y)
                    .opacity(particle.opacity)
            }
            .onAppear {
                generateParticles(in: geometry.size)
            }
        }
    }

    private func generateParticles(in size: CGSize) {
        for _ in 0..<30 {
            let particle = Particle(
                x: CGFloat.random(in: 0...size.width),
                y: size.height + 20,
                size: CGFloat.random(in: 2...6),
                opacity: Double.random(in: 0.3...0.8),
                speed: Double.random(in: 2...5)
            )
            particles.append(particle)
        }

        // Animate particles upward
        Timer.scheduledTimer(withTimeInterval: 0.016, repeats: true) { timer in
            for i in particles.indices {
                particles[i].y -= CGFloat(particles[i].speed)
                if particles[i].y < -20 {
                    particles[i].y = size.height + 20
                    particles[i].x = CGFloat.random(in: 0...size.width)
                }
            }
        }
    }
}

// MARK: - Preview

#Preview {
    DungeonRewardSheet(result: DungeonClaimResponse(
        success: true,
        xpEarned: 150,
        stretchBonusXp: 75,
        bonusObjectivesXp: 25,
        totalXp: 1500,
        level: 8,
        leveledUp: true,
        newLevel: 8,
        rank: "D",
        rankChanged: true,
        newRank: "D"
    ))
}
