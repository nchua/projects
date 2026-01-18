import SwiftUI

/// Compact recovery status section for home page with tappable muscle tags
struct RecoveryStatusSection: View {
    let cooldownData: [MuscleCooldownStatus]
    @State private var selectedMuscle: MuscleCooldownStatus?

    /// Muscles still recovering (not at 100%)
    var recoveringMuscles: [MuscleCooldownStatus] {
        cooldownData.filter { $0.cooldownPercent < 100 }
    }

    /// Muscles fully recovered
    var readyMuscles: [MuscleCooldownStatus] {
        cooldownData.filter { $0.cooldownPercent >= 100 }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                Text("RECOVERY STATUS")
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(1.5)

                Spacer()
            }

            // Muscle tags or empty state
            if cooldownData.isEmpty {
                // Empty state
                HStack(spacing: 8) {
                    Image(systemName: "figure.cooldown")
                        .font(.system(size: 14))
                        .foregroundColor(.textMuted)

                    Text("No recent muscle activity tracked")
                        .font(.ariseMono(size: 12))
                        .foregroundColor(.textMuted)
                }
                .padding(.vertical, 8)
            } else {
                FlowLayout(spacing: 8) {
                    // Show recovering muscles first
                    ForEach(recoveringMuscles) { muscle in
                        RecoveryMuscleTag(muscle: muscle, isRecovering: true) {
                            selectedMuscle = muscle
                        }
                    }

                    // Then ready muscles
                    ForEach(readyMuscles) { muscle in
                        RecoveryMuscleTag(muscle: muscle, isRecovering: false) {
                            selectedMuscle = muscle
                        }
                    }
                }
            }
        }
        .padding(16)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .sheet(item: $selectedMuscle) { muscle in
            RecoveryDetailSheet(muscle: muscle)
        }
    }
}

// MARK: - Recovery Muscle Tag

struct RecoveryMuscleTag: View {
    let muscle: MuscleCooldownStatus
    let isRecovering: Bool
    let onTap: () -> Void

    var statusText: String {
        if isRecovering {
            return muscle.timeRemainingFormatted
        } else {
            return "Ready"
        }
    }

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 6) {
                Text(muscle.displayName)
                    .font(.ariseMono(size: 12, weight: .medium))

                Text("-")
                    .font(.ariseMono(size: 12))
                    .opacity(0.5)

                Text(statusText)
                    .font(.ariseMono(size: 12, weight: .semibold))

                Image(systemName: "chevron.right")
                    .font(.system(size: 9, weight: .semibold))
                    .opacity(0.6)
            }
            .foregroundColor(isRecovering ? .warningRed : .successGreen)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                isRecovering
                    ? Color.warningRed.opacity(0.15)
                    : Color.successGreen.opacity(0.15)
            )
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(
                        isRecovering
                            ? Color.warningRed.opacity(0.3)
                            : Color.successGreen.opacity(0.3),
                        lineWidth: 1
                    )
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Flow Layout for wrapping tags

struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = arrangeSubviews(proposal: proposal, subviews: subviews)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrangeSubviews(proposal: proposal, subviews: subviews)

        for (index, frame) in result.frames.enumerated() {
            subviews[index].place(
                at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                proposal: ProposedViewSize(frame.size)
            )
        }
    }

    private func arrangeSubviews(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, frames: [CGRect]) {
        let maxWidth = proposal.width ?? .infinity
        var currentX: CGFloat = 0
        var currentY: CGFloat = 0
        var lineHeight: CGFloat = 0
        var frames: [CGRect] = []

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)

            if currentX + size.width > maxWidth && currentX > 0 {
                currentX = 0
                currentY += lineHeight + spacing
                lineHeight = 0
            }

            frames.append(CGRect(x: currentX, y: currentY, width: size.width, height: size.height))
            lineHeight = max(lineHeight, size.height)
            currentX += size.width + spacing
        }

        let totalHeight = currentY + lineHeight
        let totalWidth = frames.map { $0.maxX }.max() ?? 0

        return (CGSize(width: totalWidth, height: totalHeight), frames)
    }
}

// MARK: - Preview

#Preview {
    ZStack {
        VoidBackground()

        VStack {
            RecoveryStatusSection(cooldownData: [
                MuscleCooldownStatus(
                    muscleGroup: "chest",
                    status: "cooling",
                    cooldownPercent: 35.0,
                    hoursRemaining: 8,
                    lastTrained: "2026-01-18T10:30:00",
                    affectedExercises: [],
                    fatigueBreakdown: nil
                ),
                MuscleCooldownStatus(
                    muscleGroup: "triceps",
                    status: "cooling",
                    cooldownPercent: 65.0,
                    hoursRemaining: 4,
                    lastTrained: "2026-01-18T10:30:00",
                    affectedExercises: [],
                    fatigueBreakdown: nil
                ),
                MuscleCooldownStatus(
                    muscleGroup: "quads",
                    status: "ready",
                    cooldownPercent: 100.0,
                    hoursRemaining: 0,
                    lastTrained: "2026-01-16T10:30:00",
                    affectedExercises: [],
                    fatigueBreakdown: nil
                ),
                MuscleCooldownStatus(
                    muscleGroup: "back",
                    status: "ready",
                    cooldownPercent: 100.0,
                    hoursRemaining: 0,
                    lastTrained: "2026-01-15T10:30:00",
                    affectedExercises: [],
                    fatigueBreakdown: nil
                )
            ])
            .padding()
        }
    }
}
