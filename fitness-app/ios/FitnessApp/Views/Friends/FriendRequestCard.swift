import SwiftUI

struct FriendRequestCard: View {
    let request: FriendRequestResponse
    let isIncoming: Bool
    var onAccept: (() -> Void)?
    var onDecline: (() -> Void)?
    var onCancel: (() -> Void)?

    private var rank: HunterRank {
        if isIncoming {
            return HunterRank(rawValue: request.senderRank ?? "E") ?? .e
        } else {
            return HunterRank(rawValue: request.receiverRank ?? "E") ?? .e
        }
    }

    private var username: String {
        if isIncoming {
            return request.senderUsername ?? "unknown"
        } else {
            return request.receiverUsername ?? "unknown"
        }
    }

    private var level: Int {
        if isIncoming {
            return request.senderLevel ?? 1
        } else {
            return request.receiverLevel ?? 1
        }
    }

    private var initials: String {
        let name = username
        if name.isEmpty || name == "unknown" { return "?" }
        let components = name.split(separator: " ")
        if components.count >= 2 {
            return String(components[0].prefix(1) + components[1].prefix(1)).uppercased()
        }
        return String(name.prefix(2)).uppercased()
    }

    private var timeAgo: String {
        guard let date = request.createdAt.parseISO8601Date() else {
            return ""
        }
        let now = Date()
        let interval = now.timeIntervalSince(date)
        let hours = Int(interval / 3600)
        let days = hours / 24

        if hours < 1 {
            return "Just now"
        } else if hours < 24 {
            return "\(hours)h ago"
        } else if days == 1 {
            return "1d ago"
        } else {
            return "\(days)d ago"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Top row with avatar and info
            HStack(spacing: 12) {
                // Avatar
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(LinearGradient(
                            colors: [Color.voidLight, Color.voidDark],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ))
                    Text(initials)
                        .font(.ariseHeader(size: 16, weight: .bold))
                        .foregroundColor(.textPrimary)
                }
                .frame(width: 48, height: 48)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(rank.color, lineWidth: 2)
                )

                // Info
                VStack(alignment: .leading, spacing: 4) {
                    Text("@\(username)")
                        .font(.ariseMono(size: 13, weight: .medium))
                        .foregroundColor(.textPrimary)

                    // Badges
                    HStack(spacing: 8) {
                        Text(rank.rawValue)
                            .font(.ariseDisplay(size: 10, weight: .bold))
                            .foregroundColor(rank.textColor)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 2)
                            .background(rank.color)
                            .cornerRadius(2)

                        HStack(spacing: 4) {
                            Text("LV")
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textMuted)
                            Text("\(level)")
                                .font(.ariseMono(size: 10, weight: .bold))
                                .foregroundColor(.systemPrimary)
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Color.voidLight)
                        .cornerRadius(2)
                    }

                    // Status text
                    if isIncoming {
                        Text("wants to join your network")
                            .font(.system(size: 12))
                            .foregroundColor(.textSecondary)
                    } else {
                        Text("Request pending")
                            .font(.system(size: 12))
                            .foregroundColor(.gold)
                    }

                    // Time
                    Text(timeAgo)
                        .font(.ariseMono(size: 10))
                        .foregroundColor(.textMuted)
                }
            }

            // Action buttons
            HStack(spacing: 8) {
                if isIncoming {
                    // Accept button
                    Button(action: { onAccept?() }) {
                        Text("ACCEPT")
                            .font(.ariseHeader(size: 12, weight: .bold))
                            .tracking(1)
                            .foregroundColor(.voidBlack)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .background(Color.systemPrimary)
                            .cornerRadius(4)
                    }
                    .buttonStyle(PlainButtonStyle())

                    // Decline button
                    Button(action: { onDecline?() }) {
                        Text("DECLINE")
                            .font(.ariseHeader(size: 12, weight: .bold))
                            .tracking(1)
                            .foregroundColor(.warningRed)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .overlay(
                                RoundedRectangle(cornerRadius: 4)
                                    .stroke(Color.warningRed, lineWidth: 1)
                            )
                    }
                    .buttonStyle(PlainButtonStyle())
                } else {
                    // Cancel button for sent requests
                    Button(action: { onCancel?() }) {
                        Text("CANCEL REQUEST")
                            .font(.ariseHeader(size: 12, weight: .bold))
                            .tracking(1)
                            .foregroundColor(.textMuted)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .overlay(
                                RoundedRectangle(cornerRadius: 4)
                                    .stroke(Color.textMuted, lineWidth: 1)
                            )
                    }
                    .buttonStyle(PlainButtonStyle())
                }
            }
        }
        .padding(14)
        .background(Color.voidMedium)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .cornerRadius(4)
    }
}

#Preview {
    VStack(spacing: 16) {
        // Preview would need sample data
    }
    .padding()
    .background(Color.voidBlack)
}
