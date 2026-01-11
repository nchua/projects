import SwiftUI

/// Full-screen overlay shown when a dungeon gate spawns after a workout
struct DungeonSpawnOverlay: View {
    let dungeon: DungeonSpawnedResponse
    @Binding var isPresented: Bool

    @State private var showGate = false
    @State private var showRank = false
    @State private var showInfo = false
    @State private var gateOpacity: Double = 0
    @State private var pulseScale: CGFloat = 1.0

    var rankColor: Color {
        switch dungeon.rank {
        case "E": return .rankE
        case "D": return .rankD
        case "C": return .rankC
        case "B": return .rankB
        case "A": return .rankA
        case "S", "S+", "S++": return .rankS
        default: return .systemPrimary
        }
    }

    var body: some View {
        ZStack {
            // Dark overlay
            Color.black.opacity(0.9)
                .ignoresSafeArea()
                .opacity(gateOpacity)

            // Radial gradient background
            RadialGradient(
                colors: [
                    rankColor.opacity(0.3),
                    rankColor.opacity(0.1),
                    Color.clear
                ],
                center: .center,
                startRadius: 50,
                endRadius: 300
            )
            .ignoresSafeArea()
            .opacity(showGate ? 1 : 0)

            VStack(spacing: 32) {
                Spacer()

                // GATE DETECTED text
                Text("[ GATE DETECTED ]")
                    .font(.ariseMono(size: 14, weight: .semibold))
                    .foregroundColor(rankColor)
                    .tracking(3)
                    .opacity(showGate ? 1 : 0)

                // Gate visual
                ZStack {
                    // Outer pulsing rings
                    ForEach(0..<3) { i in
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(rankColor.opacity(0.3 - Double(i) * 0.1), lineWidth: 2)
                            .frame(width: 180 + CGFloat(i * 20), height: 260 + CGFloat(i * 20))
                            .scaleEffect(pulseScale)
                    }

                    // Main gate frame
                    GateShape()
                        .fill(
                            LinearGradient(
                                colors: [rankColor.opacity(0.8), rankColor.opacity(0.4)],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                        .frame(width: 160, height: 240)
                        .overlay(
                            GateShape()
                                .stroke(rankColor, lineWidth: 3)
                        )
                        .shadow(color: rankColor.opacity(0.5), radius: 30, x: 0, y: 0)

                    // Inner portal effect
                    RoundedRectangle(cornerRadius: 4)
                        .fill(
                            RadialGradient(
                                colors: [
                                    Color.voidBlack,
                                    rankColor.opacity(0.3),
                                    Color.voidBlack
                                ],
                                center: .center,
                                startRadius: 0,
                                endRadius: 100
                            )
                        )
                        .frame(width: 140, height: 200)

                    // Rank badge in center
                    Text(dungeon.rank)
                        .font(.ariseDisplay(size: 48, weight: .bold))
                        .foregroundColor(rankColor)
                        .shadow(color: rankColor.opacity(0.8), radius: 20, x: 0, y: 0)
                        .opacity(showRank ? 1 : 0)
                        .scaleEffect(showRank ? 1 : 0.5)
                }
                .opacity(showGate ? 1 : 0)
                .scaleEffect(showGate ? 1 : 0.7)

                // Dungeon name
                VStack(spacing: 8) {
                    Text(dungeon.name)
                        .font(.ariseHeader(size: 24, weight: .bold))
                        .foregroundColor(.textPrimary)
                        .multilineTextAlignment(.center)

                    if dungeon.isStretchDungeon, let percent = dungeon.stretchBonusPercent {
                        HStack(spacing: 6) {
                            Image(systemName: "arrow.up.right")
                                .font(.system(size: 12, weight: .bold))
                            Text("STRETCH DUNGEON +\(percent)% XP")
                                .font(.ariseMono(size: 11, weight: .semibold))
                                .tracking(1)
                        }
                        .foregroundColor(.gold)
                    }
                }
                .opacity(showInfo ? 1 : 0)

                // XP reward
                HStack(spacing: 8) {
                    Image(systemName: "star.fill")
                        .font(.system(size: 16))
                        .foregroundColor(.gold)

                    Text("\(dungeon.baseXpReward) XP")
                        .font(.ariseDisplay(size: 24, weight: .bold))
                        .foregroundColor(.gold)
                }
                .opacity(showInfo ? 1 : 0)

                // Time limit
                HStack(spacing: 6) {
                    Image(systemName: "clock.fill")
                        .font(.system(size: 12))
                    Text(formatTimeRemaining(dungeon.timeRemainingSeconds))
                        .font(.ariseMono(size: 12, weight: .medium))
                }
                .foregroundColor(.textSecondary)
                .opacity(showInfo ? 1 : 0)

                Spacer()

                // Message
                Text(dungeon.message)
                    .font(.ariseMono(size: 12))
                    .foregroundColor(.textMuted)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                    .opacity(showInfo ? 1 : 0)

                // Continue button
                Button {
                    withAnimation(.easeOut(duration: 0.3)) {
                        gateOpacity = 0
                    }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                        isPresented = false
                    }
                } label: {
                    Text("ACCEPT QUEST")
                        .font(.ariseHeader(size: 16, weight: .semibold))
                        .tracking(2)
                        .frame(maxWidth: .infinity)
                        .frame(height: 54)
                        .background(rankColor)
                        .foregroundColor(rankColor == .rankE || rankColor == .rankD || rankColor == .rankA ? .black : .white)
                }
                .padding(.horizontal, 32)
                .padding(.bottom, 48)
                .opacity(showInfo ? 1 : 0)
            }
        }
        .onAppear {
            animateIn()
            startPulseAnimation()
        }
    }

    private func animateIn() {
        // Fade in overlay
        withAnimation(.easeIn(duration: 0.3)) {
            gateOpacity = 1
        }

        // Show gate
        withAnimation(.spring(response: 0.6, dampingFraction: 0.7).delay(0.2)) {
            showGate = true
        }

        // Show rank
        withAnimation(.spring(response: 0.5, dampingFraction: 0.6).delay(0.5)) {
            showRank = true
        }

        // Show info
        withAnimation(.easeOut(duration: 0.4).delay(0.8)) {
            showInfo = true
        }

        // Haptic feedback
        let generator = UINotificationFeedbackGenerator()
        generator.notificationOccurred(.success)
    }

    private func startPulseAnimation() {
        withAnimation(.easeInOut(duration: 1.5).repeatForever(autoreverses: true)) {
            pulseScale = 1.05
        }
    }

    private func formatTimeRemaining(_ seconds: Int) -> String {
        let hours = seconds / 3600
        if hours >= 24 {
            let days = hours / 24
            return "\(days) days remaining"
        }
        return "\(hours) hours remaining"
    }
}

// MARK: - Gate Shape

struct GateShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()

        let cornerRadius: CGFloat = 8
        let archHeight: CGFloat = rect.width * 0.3

        // Start at bottom left
        path.move(to: CGPoint(x: 0, y: rect.maxY))

        // Left side up
        path.addLine(to: CGPoint(x: 0, y: cornerRadius + archHeight))

        // Arch
        path.addQuadCurve(
            to: CGPoint(x: rect.width, y: cornerRadius + archHeight),
            control: CGPoint(x: rect.midX, y: 0)
        )

        // Right side down
        path.addLine(to: CGPoint(x: rect.width, y: rect.maxY))

        // Bottom
        path.addLine(to: CGPoint(x: 0, y: rect.maxY))

        return path
    }
}

// MARK: - Preview

#Preview {
    DungeonSpawnOverlay(
        dungeon: DungeonSpawnedResponse(
            id: "1",
            dungeonId: "shadow-temple",
            name: "Shadow Temple",
            rank: "C",
            baseXpReward: 200,
            isStretchDungeon: true,
            stretchBonusPercent: 50,
            timeRemainingSeconds: 172800,
            message: "A gate has materialized. Enter within 48 hours or it will close forever."
        ),
        isPresented: .constant(true)
    )
}
