import SwiftUI

struct FriendRowCard: View {
    let friend: FriendResponse
    var onTap: (() -> Void)?

    private var rank: HunterRank {
        HunterRank(rawValue: friend.friendRank ?? "E") ?? .e
    }

    var body: some View {
        Button(action: { onTap?() }) {
            HStack(spacing: 12) {
                // Avatar
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(LinearGradient(
                            colors: [Color.voidLight, Color.voidDark],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ))
                    Text(friend.initials)
                        .font(.ariseHeader(size: 16, weight: .bold))
                        .foregroundColor(.textPrimary)
                }
                .frame(width: 48, height: 48)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(rank.color, lineWidth: 2)
                )

                // Info
                VStack(alignment: .leading, spacing: 2) {
                    // Username
                    Text("@\(friend.friendUsername ?? "unknown")")
                        .font(.ariseMono(size: 12))
                        .foregroundColor(.systemPrimary)

                    // Badges row
                    HStack(spacing: 8) {
                        // Level badge
                        HStack(spacing: 4) {
                            Text("LV")
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textMuted)
                            Text("\(friend.friendLevel ?? 1)")
                                .font(.ariseMono(size: 10, weight: .bold))
                                .foregroundColor(.systemPrimary)
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Color.voidLight)
                        .cornerRadius(2)

                        // Rank badge
                        Text(rank.rawValue)
                            .font(.ariseDisplay(size: 10, weight: .bold))
                            .foregroundColor(rank.textColor)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 2)
                            .background(rank.color)
                            .cornerRadius(2)

                        // Status indicator
                        HStack(spacing: 4) {
                            Circle()
                                .fill(friend.isRecentlyActive ? Color.successGreen : Color.textMuted)
                                .frame(width: 6, height: 6)
                                .shadow(color: friend.isRecentlyActive ? Color.successGreen : .clear, radius: 4)
                            Text(friend.lastActiveFormatted)
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textMuted)
                        }
                    }
                }

                Spacer()

                // Chevron
                Image(systemName: "chevron.right")
                    .font(.system(size: 14))
                    .foregroundColor(.textMuted)
            }
            .padding(14)
            .background(Color.voidMedium)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
            .cornerRadius(4)
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Search Result Card

struct SearchResultCard: View {
    let user: UserPublicResponse
    let status: FriendsViewModel.RequestStatus
    var onAdd: (() -> Void)?

    private var rank: HunterRank {
        HunterRank(rawValue: user.rank) ?? .e
    }

    private var initials: String {
        let username = user.username
        if username.isEmpty { return "?" }
        let components = username.split(separator: " ")
        if components.count >= 2 {
            return String(components[0].prefix(1) + components[1].prefix(1)).uppercased()
        }
        return String(username.prefix(2)).uppercased()
    }

    var body: some View {
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
                    .font(.ariseHeader(size: 14, weight: .bold))
                    .foregroundColor(.textPrimary)
            }
            .frame(width: 40, height: 40)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(rank.color, lineWidth: 2)
            )

            // Info
            VStack(alignment: .leading, spacing: 2) {
                Text("@\(user.username)")
                    .font(.ariseMono(size: 12))
                    .foregroundColor(.systemPrimary)

                HStack(spacing: 8) {
                    HStack(spacing: 4) {
                        Text("LV")
                            .font(.ariseMono(size: 10))
                            .foregroundColor(.textMuted)
                        Text("\(user.level)")
                            .font(.ariseMono(size: 10, weight: .bold))
                            .foregroundColor(.systemPrimary)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(Color.voidLight)
                    .cornerRadius(2)

                    Text(rank.rawValue)
                        .font(.ariseDisplay(size: 10, weight: .bold))
                        .foregroundColor(rank.textColor)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(rank.color)
                        .cornerRadius(2)
                }
            }

            Spacer()

            // Action button
            statusButton
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(Color.voidMedium)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .cornerRadius(4)
    }

    @ViewBuilder
    private var statusButton: some View {
        switch status {
        case .none:
            Button(action: { onAdd?() }) {
                Text("ADD")
                    .font(.ariseHeader(size: 11, weight: .bold))
                    .foregroundColor(.systemPrimary)
                    .tracking(1)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.systemPrimary, lineWidth: 1)
                    )
            }
            .buttonStyle(PlainButtonStyle())

        case .pending:
            Text("PENDING")
                .font(.ariseHeader(size: 11, weight: .bold))
                .foregroundColor(.gold)
                .tracking(1)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.gold, lineWidth: 1)
                )

        case .incoming:
            Text("INCOMING")
                .font(.ariseHeader(size: 11, weight: .bold))
                .foregroundColor(.systemPrimary)
                .tracking(1)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.systemPrimary, lineWidth: 1)
                )

        case .friends:
            HStack(spacing: 4) {
                Image(systemName: "checkmark")
                    .font(.system(size: 10, weight: .bold))
                Text("FRIENDS")
                    .font(.ariseHeader(size: 11, weight: .bold))
                    .tracking(1)
            }
            .foregroundColor(.successGreen)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.successGreen, lineWidth: 1)
            )
        }
    }
}

#Preview {
    VStack(spacing: 16) {
        // Preview would need sample data
    }
    .padding()
    .background(Color.voidBlack)
}
