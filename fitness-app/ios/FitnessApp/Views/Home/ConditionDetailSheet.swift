import SwiftUI

/// Condition detail sheet (ARISE v2 §4.4): per-input contribution bars, the
/// muscle cooldown pills (absorbing the old RecoveryStatusSection), and
/// HRV + sleep rows. Missing inputs render `NO SIGNAL — weight redistributed`,
/// never zero.
struct ConditionDetailSheet: View {
    let condition: ConditionResponse

    @Environment(\.dismiss) private var dismiss
    @State private var selectedMuscle: MuscleCooldownStatus?
    @State private var hrv: Int?

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(glowIntensity: 0.03)

                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        header
                            .padding(.horizontal)

                        // Per-input contribution bars
                        VStack(alignment: .leading, spacing: 12) {
                            AriseSectionHeader(title: "Signal Inputs")

                            ForEach(condition.inputs) { input in
                                ConditionInputRow(input: input)
                            }
                        }
                        .padding(.horizontal)

                        // Muscle pills (RecoveryStatusSection absorbed here)
                        VStack(alignment: .leading, spacing: 12) {
                            AriseSectionHeader(title: "Muscle Recovery")

                            if condition.musclesCooling.isEmpty {
                                HStack(spacing: 8) {
                                    Image(systemName: "figure.cooldown")
                                        .font(.system(size: 14))
                                        .foregroundColor(.textMuted)
                                    Text("All muscle groups fresh")
                                        .font(.system(size: 12))
                                        .foregroundColor(.textMuted)
                                }
                                .padding(.vertical, 4)
                            } else {
                                ScrollView(.horizontal, showsIndicators: false) {
                                    HStack(spacing: 8) {
                                        ForEach(
                                            condition.musclesCooling
                                                .sorted { $0.cooldownPercent < $1.cooldownPercent }
                                        ) { muscle in
                                            RecoveryPill(
                                                name: muscle.displayName,
                                                level: recoveryLevel(for: muscle)
                                            ) {
                                                selectedMuscle = muscle
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        .padding(.horizontal)

                        // Biometric rows: HRV (from today's activity) + sleep
                        if hrv != nil || sleepHours != nil {
                            VStack(alignment: .leading, spacing: 12) {
                                AriseSectionHeader(title: "Biometrics")

                                if let hrv {
                                    biometricRow(
                                        icon: "waveform.path.ecg",
                                        label: "HRV",
                                        value: "\(hrv) ms"
                                    )
                                }

                                if let sleepHours {
                                    biometricRow(
                                        icon: "moon.zzz.fill",
                                        label: "SLEEP",
                                        value: String(format: "%.1f h", sleepHours)
                                    )
                                }
                            }
                            .padding(.horizontal)
                        }

                        Spacer().frame(height: 20)
                    }
                    .padding(.vertical)
                }
            }
            .navigationTitle("Hunter Condition")
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
        .sheet(item: $selectedMuscle) { muscle in
            RecoveryDetailSheet(muscle: muscle)
        }
        .task {
            await loadHRV()
        }
    }

    // MARK: - Pieces

    private var header: some View {
        HStack(spacing: 16) {
            Text("\(condition.score)")
                .font(.ariseDisplay(size: 48, weight: .bold))
                .foregroundColor(condition.band.color)

            VStack(alignment: .leading, spacing: 4) {
                Text("[ \(condition.band.label) ]")
                    .font(.ariseMono(size: 13, weight: .bold))
                    .foregroundColor(condition.band.color)
                    .tracking(1.5)

                Text(condition.band.copy)
                    .font(.ariseMono(size: 12))
                    .foregroundColor(.textSecondary)
                    .italic()
            }

            Spacer()
        }
        .padding(20)
        .background(Color.voidMedium)
        .clipShape(RoundedRectangle(cornerRadius: 20))
        .overlay(
            RoundedRectangle(cornerRadius: 20)
                .stroke(condition.band.color.opacity(0.25), lineWidth: 1)
        )
    }

    private func biometricRow(icon: String, label: String, value: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundColor(.systemPrimary)
                .frame(width: 28)

            Text(label)
                .font(.ariseMono(size: 11, weight: .semibold))
                .foregroundColor(.textMuted)
                .tracking(1)

            Spacer()

            Text(value)
                .font(.ariseDisplay(size: 16, weight: .bold))
                .foregroundColor(.textPrimary)
        }
        .padding(14)
        .background(Color.voidMedium)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.glassBorder, lineWidth: 1)
        )
    }

    private var sleepHours: Double? {
        condition.inputs.first(where: { $0.key == "sleep" })?.raw
    }

    private func recoveryLevel(for muscle: MuscleCooldownStatus) -> RecoveryLevel {
        if muscle.cooldownPercent >= 100 {
            return .fresh
        } else if muscle.cooldownPercent >= 50 {
            return .moderate
        } else {
            return .fatigued
        }
    }

    /// HRV lands on the WHOOP-sourced daily_activity row; fall back to the
    /// default source if no WHOOP scan exists today.
    private func loadHRV() async {
        for source in ["whoop_screenshot", "apple_fitness"] {
            if let activity = try? await APIClient.shared.getTodayActivity(source: source),
               let value = activity.hrv {
                hrv = value
                return
            }
        }
    }
}

// MARK: - Input Row

/// One Condition input: label + source badge, subscore bar scaled by the
/// effective (post-renormalization) weight, or the NO SIGNAL state.
struct ConditionInputRow: View {
    let input: ConditionInput

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(input.label.uppercased())
                    .font(.ariseMono(size: 11, weight: .semibold))
                    .foregroundColor(input.available ? .textPrimary : .textMuted)
                    .tracking(1)

                AriseSourceBadge(source: input.source, compact: true)

                Spacer()

                if let subscore = input.subscore {
                    HStack(spacing: 6) {
                        Text("\(subscore)")
                            .font(.ariseDisplay(size: 15, weight: .bold))
                            .foregroundColor(.textPrimary)

                        Text("w \(Int((input.effectiveWeight * 100).rounded()))%")
                            .font(.ariseMono(size: 10))
                            .foregroundColor(.textMuted)
                    }
                }
            }

            if input.available, let subscore = input.subscore {
                GeometryReader { geometry in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(Color.white.opacity(0.08))

                        RoundedRectangle(cornerRadius: 2)
                            .fill(barColor(for: subscore))
                            .frame(width: geometry.size.width * CGFloat(subscore) / 100)
                    }
                }
                .frame(height: 4)
            } else {
                Text("NO SIGNAL — weight redistributed")
                    .font(.ariseMono(size: 10))
                    .foregroundColor(.textMuted)
                    .italic()
            }
        }
        .padding(14)
        .background(Color.voidMedium)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.glassBorder, lineWidth: 1)
        )
        .opacity(input.available ? 1.0 : 0.7)
    }

    private func barColor(for subscore: Int) -> Color {
        if subscore >= 85 { return .systemPrimary }
        if subscore >= 65 { return .successGreen }
        if subscore >= 40 { return .gold }
        return .warningRed
    }
}
