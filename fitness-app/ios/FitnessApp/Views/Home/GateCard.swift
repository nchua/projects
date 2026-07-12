import SwiftUI

/// Open Gate card on the Status tab (ARISE v2 §6.6) — between the Directive
/// and This Week, shown only while a gate is open or active. Rank sigil in
/// rank color, lift + target set, proximity bar, closes-in countdown.
struct GateCard: View {
    let gate: GateResponse
    var onTap: (() -> Void)? = nil

    var body: some View {
        Button {
            onTap?()
        } label: {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    // Rank sigil
                    Text(gate.rank)
                        .font(.ariseDisplay(size: 22, weight: .bold))
                        .foregroundColor(.black)
                        .frame(width: 40, height: 40)
                        .background(gate.rankColor)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .shadow(color: gate.rankColor.opacity(0.5), radius: 8, x: 0, y: 0)

                    VStack(alignment: .leading, spacing: 3) {
                        Text("[ GATE \(gate.status == "active" ? "ACCEPTED" : "OPEN") ]")
                            .font(.ariseMono(size: 9, weight: .semibold))
                            .foregroundColor(gate.rankColor)
                            .tracking(1.5)

                        Text(gate.name)
                            .font(.ariseHeader(size: 16, weight: .semibold))
                            .foregroundColor(.textPrimary)
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                    }

                    Spacer()

                    // Countdown
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("\(gate.daysRemaining)")
                            .font(.ariseDisplay(size: 20, weight: .bold))
                            .foregroundColor(gate.daysRemaining <= 3 ? .warningRed : .textPrimary)
                        Text(gate.daysRemaining == 1 ? "DAY LEFT" : "DAYS LEFT")
                            .font(.ariseMono(size: 8, weight: .semibold))
                            .foregroundColor(.textMuted)
                            .tracking(0.5)
                    }
                }

                // Proximity bar: how close the current best is to the target
                VStack(alignment: .leading, spacing: 5) {
                    GeometryReader { geometry in
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 3)
                                .fill(Color.white.opacity(0.08))

                            RoundedRectangle(cornerRadius: 3)
                                .fill(
                                    LinearGradient(
                                        colors: [gate.rankColor.opacity(0.6), gate.rankColor],
                                        startPoint: .leading,
                                        endPoint: .trailing
                                    )
                                )
                                .frame(width: geometry.size.width * CGFloat(gate.proximity))
                        }
                    }
                    .frame(height: 6)

                    HStack {
                        Text("BEST \(Int(gate.baselineE1rm)) lb e1RM")
                            .font(.ariseMono(size: 9))
                            .foregroundColor(.textMuted)
                        Spacer()
                        Text("TARGET \(Int(gate.targetE1rm)) lb")
                            .font(.ariseMono(size: 9, weight: .semibold))
                            .foregroundColor(gate.rankColor)
                    }
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.voidMedium)
            .clipShape(RoundedRectangle(cornerRadius: 20))
            .overlay(
                RoundedRectangle(cornerRadius: 20)
                    .stroke(gate.rankColor.opacity(0.35), lineWidth: 1)
            )
            .shadow(color: gate.rankColor.opacity(0.08), radius: 12, x: 0, y: 0)
        }
        .buttonStyle(PlainButtonStyle())
        .accessibilityLabel(
            "\(gate.name), \(gate.daysRemaining) days left, "
                + "target \(Int(gate.targetWeight)) pounds for \(gate.targetReps) reps"
        )
        .accessibilityHint("Opens gate details")
    }
}
