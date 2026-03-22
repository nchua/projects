import SwiftUI

/// Status banner showing monitoring state: "Monitoring Traffic" / "Leave Soon" / "Time to Leave"
struct StatusBannerView: View {
    let status: TripStatus

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 14))
            Text(message)
                .font(.departCaption)
                .fontWeight(.semibold)
        }
        .foregroundStyle(foregroundColor)
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background(backgroundColor)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var icon: String {
        switch status {
        case .pending: return "clock"
        case .monitoring: return "antenna.radiowaves.left.and.right"
        case .notified: return "bell.fill"
        case .departed: return "car.fill"
        case .completed: return "checkmark.circle.fill"
        case .cancelled: return "xmark.circle.fill"
        }
    }

    private var message: String {
        switch status {
        case .pending: return "Waiting to monitor"
        case .monitoring: return "Monitoring traffic"
        case .notified: return "Time to leave!"
        case .departed: return "You've departed"
        case .completed: return "Trip completed"
        case .cancelled: return "Trip cancelled"
        }
    }

    private var foregroundColor: Color {
        switch status {
        case .notified: return .white
        case .monitoring: return .departPrimary
        default: return .departTextSecondary
        }
    }

    private var backgroundColor: Color {
        switch status {
        case .notified: return .departRed
        case .monitoring: return .departPrimary.opacity(0.1)
        default: return .departSurface
        }
    }
}
