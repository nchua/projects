import SwiftUI

/// Card showing chronological notification history for a trip.
struct AlertHistoryCard: View {
    let notifications: [NotificationLogEntry]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Alert History")
                .font(.departHeadline)

            if notifications.isEmpty {
                Text("No alerts sent yet")
                    .font(.departCaption)
                    .foregroundStyle(Color.departTextSecondary)
                    .padding(.vertical, 8)
            } else {
                ForEach(notifications) { entry in
                    AlertHistoryRow(entry: entry)

                    if entry.id != notifications.last?.id {
                        Divider()
                    }
                }
            }
        }
        .departCard()
    }
}

/// Single alert history entry: dot + message + timestamp.
struct AlertHistoryRow: View {
    let entry: NotificationLogEntry

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            // Tier dot
            Circle()
                .fill(tierColor)
                .frame(width: 8, height: 8)
                .padding(.top, 5)

            VStack(alignment: .leading, spacing: 2) {
                Text(entry.title)
                    .font(.departBody)
                    .foregroundStyle(Color.departTextPrimary)
                Text(entry.body)
                    .font(.departCaption)
                    .foregroundStyle(Color.departTextSecondary)
                    .lineLimit(2)
            }

            Spacer()

            Text(entry.sentAt.shortTimeString)
                .font(.departCaption)
                .foregroundStyle(Color.departTextSecondary)
        }
    }

    private var tierColor: Color {
        switch entry.typeEnum {
        case .headsUp: return .departGreen
        case .prepare: return .departPrimary
        case .leaveSoon: return .departOrange
        case .leaveNow: return .departRed
        case .runningLate: return .departRed
        }
    }
}
