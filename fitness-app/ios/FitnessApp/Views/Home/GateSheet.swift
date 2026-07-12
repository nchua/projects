import SwiftUI

/// Gate detail sheet (ARISE v2 §6.6): designation header, target set,
/// WHY THIS GATE with the real slope/projection numbers (the System shows
/// its work), Condition-at-spawn check, window, reward, and ACCEPT GATE.
struct GateSheet: View {
    let gate: GateResponse
    /// Called after a successful accept so the Status tab can refresh.
    var onAccepted: (() -> Void)? = nil

    @Environment(\.dismiss) private var dismiss
    @State private var isAccepting = false
    @State private var acceptError: String?
    @State private var didAccept = false

    private var isActive: Bool { didAccept || gate.status == "active" }
    private var isCleared: Bool { gate.status == "cleared" }

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(glowIntensity: 0.03)

                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        designationHeader
                            .padding(.horizontal)

                        // Target set
                        VStack(alignment: .leading, spacing: 10) {
                            AriseSectionHeader(title: "Target")

                            HStack(alignment: .lastTextBaseline, spacing: 8) {
                                Text("\(Int(gate.targetWeight))")
                                    .font(.ariseDisplay(size: 40, weight: .bold))
                                    .foregroundColor(.textPrimary)
                                Text("lb")
                                    .font(.ariseMono(size: 14))
                                    .foregroundColor(.textMuted)
                                Text("\u{00D7} \(gate.targetReps)")
                                    .font(.ariseDisplay(size: 26, weight: .bold))
                                    .foregroundColor(gate.rankColor)
                                Spacer()
                                VStack(alignment: .trailing, spacing: 2) {
                                    Text("\(Int(gate.targetE1rm)) lb")
                                        .font(.ariseDisplay(size: 16, weight: .bold))
                                        .foregroundColor(.textPrimary)
                                    Text("TARGET e1RM")
                                        .font(.ariseMono(size: 8, weight: .semibold))
                                        .foregroundColor(.textMuted)
                                        .tracking(0.5)
                                }
                            }
                            .padding(18)
                            .background(Color.voidMedium)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color.glassBorder, lineWidth: 1)
                            )
                        }
                        .padding(.horizontal)

                        // WHY THIS GATE — the System shows its work
                        VStack(alignment: .leading, spacing: 10) {
                            AriseSectionHeader(title: "Why This Gate")

                            VStack(spacing: 0) {
                                whyRow("CURRENT BEST", "\(Int(gate.baselineE1rm)) lb e1RM")
                                divider
                                whyRow(
                                    "WEEKLY TREND",
                                    String(format: "%+.1f lb/week", gate.weeklySlope)
                                )
                                divider
                                whyRow("14-DAY PROJECTION", "\(Int(gate.projectedE1rm)) lb e1RM")
                                divider
                                whyRow(
                                    "CONDITION AT SPAWN",
                                    "\(gate.conditionAtSpawn) — BATTLE READY",
                                    valueColor: .successGreen
                                )
                            }
                            .background(Color.voidMedium)
                            .cornerRadius(4)
                            .overlay(
                                RoundedRectangle(cornerRadius: 4)
                                    .stroke(Color.ariseBorder, lineWidth: 1)
                            )

                            Text("The trend engine projects a PR inside this window. The System opened the Gate.")
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textMuted)
                                .italic()
                        }
                        .padding(.horizontal)

                        // Window + reward
                        VStack(alignment: .leading, spacing: 10) {
                            AriseSectionHeader(title: "Terms")

                            HStack(spacing: 12) {
                                termTile(
                                    icon: "hourglass",
                                    value: "\(gate.daysRemaining)d",
                                    label: "REMAINING"
                                )
                                termTile(
                                    icon: "bolt.fill",
                                    value: "+\(xpForRank)",
                                    label: "XP ON CLEAR",
                                    tint: .gold
                                )
                            }
                        }
                        .padding(.horizontal)

                        // Accept CTA / states
                        VStack(spacing: 10) {
                            if isCleared {
                                clearedBanner
                            } else if isActive {
                                acceptedBanner
                            } else {
                                acceptButton
                            }

                            if let acceptError {
                                Text(acceptError)
                                    .font(.ariseMono(size: 11))
                                    .foregroundColor(.warningRed)
                            }

                            if !isCleared && !isActive {
                                Text("Or let it close. No penalty — Gates return when the data says so.")
                                    .font(.ariseMono(size: 10))
                                    .foregroundColor(.textMuted)
                            }
                        }
                        .padding(.horizontal)

                        Spacer().frame(height: 20)
                    }
                    .padding(.vertical)
                }
            }
            .navigationTitle("PR Gate")
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
    }

    // MARK: - Pieces

    private var designationHeader: some View {
        HStack(spacing: 16) {
            Text(gate.rank)
                .font(.ariseDisplay(size: 34, weight: .bold))
                .foregroundColor(.black)
                .frame(width: 64, height: 64)
                .background(gate.rankColor)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .shadow(color: gate.rankColor.opacity(0.5), radius: 12, x: 0, y: 0)

            VStack(alignment: .leading, spacing: 4) {
                Text("[ \(gate.rank)-RANK DESIGNATION ]")
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(gate.rankColor)
                    .tracking(1.5)

                Text(gate.exerciseName)
                    .font(.ariseHeader(size: 20, weight: .bold))
                    .foregroundColor(.textPrimary)
                    .lineLimit(2)
                    .minimumScaleFactor(0.7)
            }

            Spacer()
        }
        .padding(20)
        .background(Color.voidMedium)
        .clipShape(RoundedRectangle(cornerRadius: 20))
        .overlay(
            RoundedRectangle(cornerRadius: 20)
                .stroke(gate.rankColor.opacity(0.3), lineWidth: 1)
        )
    }

    private var divider: some View {
        Rectangle()
            .fill(Color.ariseBorder)
            .frame(height: 1)
            .padding(.horizontal, 16)
    }

    private func whyRow(_ label: String, _ value: String, valueColor: Color = .textPrimary) -> some View {
        HStack {
            Text(label)
                .font(.ariseMono(size: 11, weight: .semibold))
                .foregroundColor(.textMuted)
                .tracking(1)
            Spacer()
            Text(value)
                .font(.ariseMono(size: 13, weight: .bold))
                .foregroundColor(valueColor)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    private func termTile(icon: String, value: String, label: String, tint: Color = .systemPrimary) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundColor(tint)

            VStack(alignment: .leading, spacing: 2) {
                Text(value)
                    .font(.ariseDisplay(size: 16, weight: .bold))
                    .foregroundColor(.textPrimary)
                Text(label)
                    .font(.ariseMono(size: 8, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(0.5)
            }
            Spacer()
        }
        .padding(14)
        .background(Color.voidMedium)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.glassBorder, lineWidth: 1)
        )
    }

    private var acceptButton: some View {
        Button {
            Task { await accept() }
        } label: {
            HStack(spacing: 8) {
                if isAccepting {
                    SwiftUI.ProgressView()
                        .tint(.black)
                } else {
                    Image(systemName: "flag.fill")
                        .font(.system(size: 14))
                }
                Text("ACCEPT GATE")
                    .font(.ariseHeader(size: 15, weight: .semibold))
                    .tracking(1)
            }
            .foregroundColor(.black)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(gate.rankColor)
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .shadow(color: gate.rankColor.opacity(0.35), radius: 8, x: 0, y: 4)
        }
        .disabled(isAccepting)
    }

    private var acceptedBanner: some View {
        HStack(spacing: 8) {
            Image(systemName: "flag.fill")
                .font(.system(size: 13))
            Text("GATE ACCEPTED — HUNT WHEN READY")
                .font(.ariseMono(size: 12, weight: .bold))
                .tracking(1)
        }
        .foregroundColor(gate.rankColor)
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
        .background(gate.rankColor.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private var clearedBanner: some View {
        HStack(spacing: 8) {
            Image(systemName: "checkmark.seal.fill")
                .font(.system(size: 13))
            Text("GATE CLEARED\(gate.xpAwarded.map { " — +\($0) XP" } ?? "")")
                .font(.ariseMono(size: 12, weight: .bold))
                .tracking(1)
        }
        .foregroundColor(.successGreen)
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
        .background(Color.successGreen.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private var xpForRank: Int {
        switch gate.rank {
        case "C": return 300
        case "B": return 500
        case "A": return 800
        case "S": return 1200
        default: return 0
        }
    }

    private func accept() async {
        isAccepting = true
        acceptError = nil
        do {
            _ = try await APIClient.shared.acceptGate(id: gate.id)
            didAccept = true
            onAccepted?()
        } catch {
            acceptError = "Failed to accept gate: \(error.localizedDescription)"
        }
        isAccepting = false
    }
}
