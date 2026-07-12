import SwiftUI

// The RecoveryStatusSection pill row was absorbed into ConditionDetailSheet
// (ARISE v2 Phase 1, spec §4.4). RecoveryLevel + RecoveryPill survive here as
// the shared muscle-pill visual language; RecoveryDetailSheet remains the
// per-muscle drill-down.

enum RecoveryLevel {
    case fresh
    case moderate
    case fatigued

    var color: Color {
        switch self {
        case .fresh: return Color(hex: "00FF88")      // Success green
        case .moderate: return Color(hex: "FF9500")   // Warning orange
        case .fatigued: return Color(hex: "FF4757")   // Danger red
        }
    }
}

// MARK: - Recovery Pill (Edge Flow)

struct RecoveryPill: View {
    let name: String
    let level: RecoveryLevel
    var onTap: (() -> Void)? = nil

    var body: some View {
        Button {
            onTap?()
        } label: {
            HStack(spacing: 6) {
                // Status dot with glow
                Circle()
                    .fill(level.color)
                    .frame(width: 6, height: 6)
                    .shadow(color: level.color.opacity(0.5), radius: 3, x: 0, y: 0)

                // Muscle group name
                Text(name)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.white)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(Color.voidMedium)
            .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Preview

#Preview {
    ZStack {
        VoidBackground()

        HStack {
            RecoveryPill(name: "Chest", level: .fatigued)
            RecoveryPill(name: "Triceps", level: .moderate)
            RecoveryPill(name: "Quads", level: .fresh)
        }
        .padding()
    }
}
