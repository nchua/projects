import SwiftUI

/// Directive detail sheet (ARISE v2 §5.4): the message, the "why" with the
/// real numbers the rule fired on, the reward, and the last-7-days history.
/// System Window dialect (mono/bracket, sharp corners) like the card.
struct DirectiveSheet: View {
    let directive: DirectiveResponse

    @Environment(\.dismiss) private var dismiss
    @State private var history: [DirectiveResponse] = []

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(glowIntensity: 0.03)

                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        messageCard
                            .padding(.horizontal)

                        // WHY — the rule's real inputs
                        if !whyRows.isEmpty {
                            VStack(alignment: .leading, spacing: 10) {
                                AriseSectionHeader(title: "Why This Directive")

                                VStack(spacing: 0) {
                                    ForEach(Array(whyRows.enumerated()), id: \.offset) { index, row in
                                        HStack {
                                            Text(row.label)
                                                .font(.ariseMono(size: 11, weight: .semibold))
                                                .foregroundColor(.textMuted)
                                                .tracking(1)

                                            Spacer()

                                            Text(row.value)
                                                .font(.ariseMono(size: 13, weight: .bold))
                                                .foregroundColor(.textPrimary)
                                        }
                                        .padding(.horizontal, 16)
                                        .padding(.vertical, 12)

                                        if index < whyRows.count - 1 {
                                            Rectangle()
                                                .fill(Color.ariseBorder)
                                                .frame(height: 1)
                                                .padding(.horizontal, 16)
                                        }
                                    }
                                }
                                .background(Color.voidMedium)
                                .cornerRadius(4)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 4)
                                        .stroke(Color.ariseBorder, lineWidth: 1)
                                )
                            }
                            .padding(.horizontal)
                        }

                        // Reward
                        VStack(alignment: .leading, spacing: 10) {
                            AriseSectionHeader(title: "Reward")

                            HStack(spacing: 10) {
                                Image(systemName: "bolt.fill")
                                    .font(.system(size: 14))
                                    .foregroundColor(.gold)

                                Text("+\(directive.xpReward) XP")
                                    .font(.ariseDisplay(size: 18, weight: .bold))
                                    .foregroundColor(.gold)

                                Spacer()

                                Text(directive.isCompleted ? "AWARDED" : "ON COMPLETION")
                                    .font(.ariseMono(size: 10, weight: .semibold))
                                    .foregroundColor(directive.isCompleted ? .successGreen : .textMuted)
                                    .tracking(1)
                            }
                            .padding(16)
                            .background(Color.voidMedium)
                            .cornerRadius(4)
                            .overlay(
                                RoundedRectangle(cornerRadius: 4)
                                    .stroke(Color.ariseBorder, lineWidth: 1)
                            )
                        }
                        .padding(.horizontal)

                        // 7-day history
                        if !history.isEmpty {
                            VStack(alignment: .leading, spacing: 10) {
                                AriseSectionHeader(title: "Directive Log")

                                VStack(spacing: 8) {
                                    ForEach(history) { entry in
                                        DirectiveHistoryRow(entry: entry)
                                    }
                                }
                            }
                            .padding(.horizontal)
                        }

                        Spacer().frame(height: 20)
                    }
                    .padding(.vertical)
                }
            }
            .navigationTitle("System Directive")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.voidDark, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { dismiss() }
                        .font(.ariseMono(size: 14, weight: .medium))
                        .foregroundColor(.systemPrimary)
                }
            }
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
        .task {
            history = (try? await APIClient.shared.getDirectiveHistory(limit: 7).directives) ?? []
        }
    }

    // MARK: - Pieces

    private var messageCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("[ SYSTEM DIRECTIVE ]")
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.systemPrimary)
                    .tracking(1.5)

                Spacer()

                if directive.isCompleted {
                    Text("COMPLETE")
                        .font(.ariseMono(size: 10, weight: .bold))
                        .foregroundColor(.successGreen)
                        .tracking(1)
                } else {
                    Text("ACTIVE")
                        .font(.ariseMono(size: 10, weight: .bold))
                        .foregroundColor(.gold)
                        .tracking(1)
                }
            }

            Text(directive.message)
                .font(.ariseMono(size: 16))
                .foregroundColor(.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(20)
        .background(Color.voidMedium)
        .overlay(
            Rectangle()
                .fill(Color.systemPrimary.opacity(0.4))
                .frame(height: 1),
            alignment: .top
        )
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }

    /// Human-readable rows for the type-specific params (the "why" section).
    private var whyRows: [(label: String, value: String)] {
        guard let params = directive.params else { return [] }
        var rows: [(String, String)] = []

        if let score = params["condition_score"] {
            rows.append(("CONDITION", score.displayString))
        }
        if let lift = params["lift"] {
            rows.append(("LIFT", lift.displayString))
        }
        if let muscle = params["muscle"] {
            rows.append(("MUSCLE CLEARED", muscle.displayString.capitalized))
        }
        if let delta = params["delta_pct"] {
            rows.append(("VOLUME DOWN", "\(delta.displayString)%"))
        }
        if let targetSets = params["target_sets"] {
            rows.append(("SETS TO RECLAIM", targetSets.displayString))
        }
        if let streak = params["streak"] {
            rows.append(("STREAK AT RISK", "\(streak.displayString) days"))
        }
        if let perWeek = params["workouts_per_week"] {
            rows.append(("HUNTS / WEEK", perWeek.displayString))
        }
        if let hunts = params["hunts_this_week"] {
            rows.append(("HUNTS THIS WEEK", hunts.displayString))
        }
        return rows
    }
}

// MARK: - History Row

private struct DirectiveHistoryRow: View {
    let entry: DirectiveResponse

    private var dayLabel: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        guard let date = formatter.date(from: entry.date) else { return entry.date }
        formatter.dateFormat = "EEE MMM d"
        return formatter.string(from: date)
    }

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: entry.isCompleted ? "checkmark.square.fill" : "square")
                .font(.system(size: 14))
                .foregroundColor(entry.isCompleted ? .successGreen : .textMuted)

            VStack(alignment: .leading, spacing: 2) {
                Text(dayLabel.uppercased())
                    .font(.ariseMono(size: 9, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(1)

                Text(entry.message)
                    .font(.ariseMono(size: 12))
                    .foregroundColor(.textSecondary)
                    .lineLimit(2)
            }

            Spacer()

            if entry.isCompleted {
                Text("+\(entry.xpReward)")
                    .font(.ariseMono(size: 11, weight: .bold))
                    .foregroundColor(.successGreen)
            }
        }
        .padding(12)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }
}
