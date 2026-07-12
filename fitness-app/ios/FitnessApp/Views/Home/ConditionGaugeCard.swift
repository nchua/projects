import SwiftUI

/// Status-tab hero: the Hunter Condition arc gauge (ARISE v2 §4.4).
///
/// Renders the 0-100 readiness score inside a 270° arc tinted by the band
/// color, with the band label, System copy line, and provenance chips for the
/// live inputs. Tapping opens `ConditionDetailSheet`.
struct ConditionGaugeCard: View {
    let condition: ConditionResponse?
    var onTap: (() -> Void)? = nil

    private var band: ConditionBand? { condition?.band }
    private var gaugeColor: Color { band?.color ?? .textMuted }

    /// Fraction of the arc to fill (score / 100).
    private var fillFraction: Double {
        guard let condition else { return 0 }
        return Double(condition.score) / 100.0
    }

    /// Available inputs, in server (weight) order, for the provenance chips.
    private var liveInputs: [ConditionInput] {
        condition?.inputs.filter { $0.available } ?? []
    }

    var body: some View {
        Button {
            onTap?()
        } label: {
            VStack(spacing: 14) {
                ZStack {
                    // Track: 270° arc opening at the bottom
                    Circle()
                        .trim(from: 0, to: 0.75)
                        .stroke(Color.white.opacity(0.08), style: StrokeStyle(lineWidth: 10, lineCap: .round))
                        .rotationEffect(.degrees(135))

                    // Fill
                    Circle()
                        .trim(from: 0, to: 0.75 * fillFraction)
                        .stroke(
                            AngularGradient(
                                colors: [gaugeColor.opacity(0.5), gaugeColor],
                                center: .center,
                                startAngle: .degrees(135),
                                endAngle: .degrees(405)
                            ),
                            style: StrokeStyle(lineWidth: 10, lineCap: .round)
                        )
                        .rotationEffect(.degrees(135))
                        .shadow(color: gaugeColor.opacity(0.4), radius: 8, x: 0, y: 0)
                        .animation(.easeOut(duration: 0.6), value: fillFraction)

                    // Score + band
                    VStack(spacing: 4) {
                        if let condition {
                            Text("\(condition.score)")
                                .font(.ariseDisplay(size: 44, weight: .bold))
                                .foregroundColor(.textPrimary)
                        } else {
                            Text("--")
                                .font(.ariseDisplay(size: 44, weight: .bold))
                                .foregroundColor(.textMuted)
                        }

                        Text(band?.label ?? "SYNCING")
                            .font(.ariseMono(size: 12, weight: .bold))
                            .foregroundColor(gaugeColor)
                            .tracking(2)
                    }
                }
                .frame(width: 170, height: 170)

                // System copy line
                Text(band?.copy ?? "Awaiting signal...")
                    .font(.ariseMono(size: 12))
                    .foregroundColor(.textSecondary)
                    .italic()

                // Provenance chips for live inputs
                if !liveInputs.isEmpty {
                    HStack(spacing: 6) {
                        ForEach(liveInputs) { input in
                            Text(input.label.uppercased())
                                .font(.ariseMono(size: 8, weight: .semibold))
                                .tracking(0.5)
                                .foregroundColor(.textMuted)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 3)
                                .background(Color.white.opacity(0.05))
                                .clipShape(Capsule())
                        }
                    }
                }

                // Header label row (System Window accent)
                HStack {
                    Text("[ HUNTER CONDITION ]")
                        .font(.ariseMono(size: 10, weight: .semibold))
                        .foregroundColor(.textMuted)
                        .tracking(1)

                    Spacer()

                    Image(systemName: "chevron.right")
                        .font(.system(size: 11))
                        .foregroundColor(.textMuted)
                }
            }
            .padding(20)
            .frame(maxWidth: .infinity)
            .background(Color.voidMedium)
            .clipShape(RoundedRectangle(cornerRadius: 20))
            .overlay(
                RoundedRectangle(cornerRadius: 20)
                    .stroke(Color.glassBorder, lineWidth: 1)
            )
            .shadow(color: gaugeColor.opacity(0.06), radius: 15, x: 0, y: 0)
        }
        .buttonStyle(PlainButtonStyle())
        .accessibilityLabel(
            condition.map { "Hunter Condition \($0.score), \($0.band.label)" }
                ?? "Hunter Condition loading"
        )
        .accessibilityHint("Opens the Condition breakdown")
    }
}

#Preview {
    ZStack {
        VoidBackground()
        ConditionGaugeCard(condition: nil)
            .padding()
    }
}
