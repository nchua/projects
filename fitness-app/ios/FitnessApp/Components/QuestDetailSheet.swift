import SwiftUI

/// Detail sheet showing full quest information with progress visualization
struct QuestDetailSheet: View {
    let quest: QuestResponse
    let onClaim: (String) -> Void
    var onViewWorkout: ((String) -> Void)? = nil

    @Environment(\.dismiss) private var dismiss

    var progressPercent: Double {
        guard quest.targetValue > 0 else { return 0 }
        return min(1.0, Double(quest.progress) / Double(quest.targetValue))
    }

    var questEmoji: String {
        switch quest.questType {
        case "total_reps": return "\u{1F4AA}"      // Flexed bicep
        case "compound_sets": return "\u{1F3AF}"  // Target
        case "total_volume": return "\u{1F4C8}"   // Chart
        case "training_time": return "\u{23F1}"   // Stopwatch
        default: return "\u{2694}"                // Crossed swords
        }
    }

    var difficultyColor: Color {
        switch quest.difficulty.lowercased() {
        case "easy": return Color(hex: "4ADE80")     // Green
        case "hard": return Color(hex: "F87171")     // Red
        default: return Color(hex: "FBBF24")         // Yellow/gold for normal
        }
    }

    var difficultyLabel: String {
        quest.difficulty.capitalized
    }

    var progressText: String {
        // Format based on quest type
        switch quest.questType {
        case "total_volume":
            return "\(quest.progress.formatted()) / \(quest.targetValue.formatted()) lbs"
        case "training_time":
            return "\(quest.progress) / \(quest.targetValue) min"
        default:
            return "\(quest.progress) / \(quest.targetValue)"
        }
    }

    var isClaimable: Bool {
        quest.isCompleted && !quest.isClaimed
    }

    var canNavigateToWorkout: Bool {
        quest.isClaimed && quest.completedByWorkoutId != nil
    }

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                ScrollView {
                    VStack(spacing: 24) {
                        // Quest Header Card
                        VStack(spacing: 20) {
                            // Emoji and Name
                            HStack(spacing: 14) {
                                Text(questEmoji)
                                    .font(.system(size: 36))

                                VStack(alignment: .leading, spacing: 4) {
                                    Text(quest.name)
                                        .font(.system(size: 20, weight: .bold))
                                        .foregroundColor(.textPrimary)

                                    // Difficulty badge
                                    Text(difficultyLabel)
                                        .font(.system(size: 12, weight: .semibold))
                                        .foregroundColor(difficultyColor)
                                        .padding(.horizontal, 10)
                                        .padding(.vertical, 4)
                                        .background(difficultyColor.opacity(0.15))
                                        .clipShape(Capsule())
                                }

                                Spacer()
                            }

                            // Description
                            Text(quest.description)
                                .font(.system(size: 14))
                                .foregroundColor(.textSecondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .lineLimit(nil)

                            // XP Reward
                            HStack {
                                Image(systemName: "star.fill")
                                    .font(.system(size: 14))
                                    .foregroundColor(.gold)

                                Text("+\(quest.xpReward) XP")
                                    .font(.system(size: 16, weight: .semibold))
                                    .foregroundColor(.gold)

                                Spacer()
                            }
                        }
                        .padding(20)
                        .background(Color.voidMedium)
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                        .overlay(
                            RoundedRectangle(cornerRadius: 14)
                                .stroke(Color.ariseBorder, lineWidth: 1)
                        )

                        // Progress Section
                        VStack(alignment: .leading, spacing: 16) {
                            Text("Progress")
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundColor(.textPrimary)

                            // Progress Bar
                            GeometryReader { geometry in
                                ZStack(alignment: .leading) {
                                    // Background track
                                    RoundedRectangle(cornerRadius: 8)
                                        .fill(Color.voidLight)

                                    // Filled portion
                                    RoundedRectangle(cornerRadius: 8)
                                        .fill(
                                            LinearGradient(
                                                colors: quest.isCompleted
                                                    ? [Color(hex: "00FF88"), Color(hex: "00CC6A")]
                                                    : [Color.systemPrimary, Color(hex: "7B61FF")],
                                                startPoint: .leading,
                                                endPoint: .trailing
                                            )
                                        )
                                        .frame(width: geometry.size.width * CGFloat(progressPercent))
                                        .shadow(
                                            color: (quest.isCompleted ? Color(hex: "00FF88") : Color.systemPrimary).opacity(0.4),
                                            radius: 8,
                                            x: 0,
                                            y: 0
                                        )
                                }
                            }
                            .frame(height: 16)

                            // Progress Text
                            HStack {
                                Text(progressText)
                                    .font(.system(size: 14, weight: .medium))
                                    .foregroundColor(.textSecondary)

                                Spacer()

                                Text("\(Int(progressPercent * 100))%")
                                    .font(.system(size: 14, weight: .bold))
                                    .foregroundColor(quest.isCompleted ? Color(hex: "00FF88") : .systemPrimary)
                            }
                        }
                        .padding(20)
                        .background(Color.voidMedium)
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                        .overlay(
                            RoundedRectangle(cornerRadius: 14)
                                .stroke(Color.ariseBorder, lineWidth: 1)
                        )

                        // Action Section
                        VStack(spacing: 16) {
                            if quest.isClaimed {
                                // Completed state
                                HStack(spacing: 12) {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 24))
                                        .foregroundColor(Color(hex: "00FF88"))

                                    Text("Completed!")
                                        .font(.system(size: 18, weight: .semibold))
                                        .foregroundColor(Color(hex: "00FF88"))
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 16)
                                .background(Color(hex: "00FF88").opacity(0.1))
                                .clipShape(RoundedRectangle(cornerRadius: 12))

                                // View workout button if available
                                if let workoutId = quest.completedByWorkoutId {
                                    Button {
                                        dismiss()
                                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                                            onViewWorkout?(workoutId)
                                        }
                                    } label: {
                                        HStack(spacing: 8) {
                                            Image(systemName: "eye")
                                                .font(.system(size: 14, weight: .medium))
                                            Text("View Workout")
                                                .font(.system(size: 14, weight: .semibold))
                                        }
                                        .foregroundColor(.systemPrimary)
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 14)
                                        .background(Color.voidMedium)
                                        .clipShape(RoundedRectangle(cornerRadius: 12))
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 12)
                                                .stroke(Color.systemPrimary.opacity(0.3), lineWidth: 1)
                                        )
                                    }
                                }
                            } else if isClaimable {
                                // Claim button
                                Button {
                                    onClaim(quest.id)
                                    dismiss()
                                } label: {
                                    HStack(spacing: 8) {
                                        Image(systemName: "gift.fill")
                                            .font(.system(size: 16))
                                        Text("Claim Reward")
                                            .font(.system(size: 16, weight: .bold))
                                    }
                                    .foregroundColor(.black)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 16)
                                    .background(
                                        LinearGradient(
                                            colors: [Color(hex: "00FF88"), Color(hex: "00CC6A")],
                                            startPoint: .leading,
                                            endPoint: .trailing
                                        )
                                    )
                                    .clipShape(RoundedRectangle(cornerRadius: 12))
                                    .shadow(color: Color(hex: "00FF88").opacity(0.4), radius: 15, x: 0, y: 0)
                                }
                            } else {
                                // In-progress motivational text
                                VStack(spacing: 8) {
                                    Text(motivationalText)
                                        .font(.system(size: 14, weight: .medium))
                                        .foregroundColor(.textSecondary)
                                        .multilineTextAlignment(.center)

                                    Text("Keep going!")
                                        .font(.system(size: 16, weight: .semibold))
                                        .foregroundColor(.systemPrimary)
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 20)
                                .background(Color.voidMedium)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                            }
                        }

                        Spacer().frame(height: 20)
                    }
                    .padding(20)
                }
            }
            .navigationTitle("Quest Details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.voidDark, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(.systemPrimary)
                }
            }
        }
    }

    private var motivationalText: String {
        let remaining = quest.targetValue - quest.progress
        switch quest.questType {
        case "total_reps":
            return "\(remaining) reps to go!"
        case "compound_sets":
            return "\(remaining) sets remaining!"
        case "total_volume":
            return "\(remaining.formatted()) lbs to lift!"
        case "training_time":
            return "\(remaining) minutes left!"
        default:
            return "You're \(Int(progressPercent * 100))% there!"
        }
    }
}

#Preview {
    QuestDetailSheet(
        quest: QuestResponse(
            id: "1",
            questId: "volume_5k",
            name: "Volume Builder",
            description: "Lift 5,000 lbs total weight across all exercises in a single workout.",
            questType: "total_volume",
            targetValue: 5000,
            xpReward: 25,
            progress: 3750,
            isCompleted: false,
            isClaimed: false,
            difficulty: "normal",
            completedByWorkoutId: nil
        ),
        onClaim: { _ in }
    )
}
