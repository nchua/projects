import SwiftUI

/// System Directive card (ARISE v2 §5.4) — one line from the System per day,
/// directly under the Condition gauge. This card (and its sheet) keep the
/// sharp System Window dialect: mono type, bracket tags, 4px corners.
struct DirectiveCard: View {
    let directive: DirectiveResponse
    var onTap: (() -> Void)? = nil

    var body: some View {
        Button {
            onTap?()
        } label: {
            VStack(alignment: .leading, spacing: 10) {
                // Header row: bracket tag + status
                HStack {
                    Text("[ SYSTEM DIRECTIVE ]")
                        .font(.ariseMono(size: 10, weight: .semibold))
                        .foregroundColor(.systemPrimary)
                        .tracking(1.5)

                    Spacer()

                    if directive.isCompleted {
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark")
                                .font(.system(size: 9, weight: .bold))
                            Text("COMPLETE +\(directive.xpReward) XP")
                                .font(.ariseMono(size: 10, weight: .bold))
                                .tracking(1)
                        }
                        .foregroundColor(.successGreen)
                    } else {
                        Text("ACTIVE")
                            .font(.ariseMono(size: 10, weight: .bold))
                            .foregroundColor(.gold)
                            .tracking(1)
                    }
                }

                // The System speaks
                HStack(alignment: .top, spacing: 8) {
                    Text("\u{25C6}")  // ◆ section marker
                        .font(.system(size: 10))
                        .foregroundColor(.systemPrimary)
                        .padding(.top, 3)

                    Text(directive.message)
                        .font(.ariseMono(size: 14))
                        .foregroundColor(.textPrimary)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.voidMedium)
            .overlay(
                Rectangle()
                    .fill(
                        (directive.isCompleted ? Color.successGreen : Color.systemPrimary)
                            .opacity(0.4)
                    )
                    .frame(height: 1),
                alignment: .top
            )
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
        }
        .buttonStyle(PlainButtonStyle())
        .accessibilityLabel(
            "System Directive: \(directive.message). "
                + (directive.isCompleted ? "Complete." : "Active.")
        )
        .accessibilityHint("Opens directive details")
    }
}
