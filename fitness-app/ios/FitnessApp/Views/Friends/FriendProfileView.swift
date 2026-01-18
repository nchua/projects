import SwiftUI

struct FriendProfileView: View {
    @Environment(\.dismiss) private var dismiss
    let friend: FriendResponse
    @ObservedObject var viewModel: FriendsViewModel
    @State private var showRemoveConfirmation = false

    private var rank: HunterRank {
        HunterRank(rawValue: friend.friendRank ?? "E") ?? .e
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.voidBlack.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 20) {
                        // Profile Header
                        profileHeader

                        // Stats Panel
                        if let profile = viewModel.selectedFriendProfile {
                            statsPanel(profile: profile)
                        }

                        // Action Buttons
                        actionButtons

                        // Recent Activity
                        if let profile = viewModel.selectedFriendProfile, !profile.recentWorkouts.isEmpty {
                            recentActivitySection(profile: profile)
                        }
                    }
                    .padding(.bottom, 40)
                }
            }
            .navigationBarHidden(true)
            .task {
                await viewModel.loadFriendProfile(userId: friend.friendId)
            }
            .confirmationDialog(
                "Remove Friend",
                isPresented: $showRemoveConfirmation,
                titleVisibility: .visible
            ) {
                Button("Remove Friend", role: .destructive) {
                    Task {
                        await viewModel.removeFriend(userId: friend.friendId)
                        dismiss()
                    }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Are you sure you want to remove @\(friend.friendUsername ?? "this user") from your network?")
            }
        }
    }

    // MARK: - Profile Header

    private var profileHeader: some View {
        VStack(spacing: 16) {
            // Close button
            HStack {
                Spacer()
                Button(action: { dismiss() }) {
                    Image(systemName: "xmark")
                        .font(.system(size: 16))
                        .foregroundColor(.textSecondary)
                        .frame(width: 32, height: 32)
                        .background(Color.voidLight)
                        .cornerRadius(4)
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 16)

            // Avatar
            ZStack {
                RoundedRectangle(cornerRadius: 4)
                    .fill(LinearGradient(
                        colors: [Color.voidLight, Color.voidDark],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ))
                Text(friend.initials)
                    .font(.ariseDisplay(size: 24, weight: .bold))
                    .foregroundColor(.textPrimary)
            }
            .frame(width: 80, height: 80)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(rank.color, lineWidth: 3)
            )

            // Username
            Text("@\(friend.friendUsername ?? "unknown")")
                .font(.ariseMono(size: 14))
                .foregroundColor(.systemPrimary)

            // Badges
            HStack(spacing: 8) {
                // Level badge
                HStack(spacing: 4) {
                    Text("LEVEL")
                        .font(.ariseMono(size: 12))
                        .foregroundColor(.textMuted)
                    Text("\(friend.friendLevel ?? 1)")
                        .font(.ariseMono(size: 16, weight: .bold))
                        .foregroundColor(.systemPrimary)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 4)
                .background(Color.voidLight)
                .cornerRadius(2)

                // Rank badge
                Text("\(rank.rawValue)-RANK")
                    .font(.ariseDisplay(size: 12, weight: .bold))
                    .foregroundColor(rank.textColor)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 4)
                    .background(rank.color)
                    .cornerRadius(2)
            }
        }
        .padding(.bottom, 20)
        .background(
            LinearGradient(
                colors: [Color.systemPrimary.opacity(0.05), Color.clear],
                startPoint: .top,
                endPoint: .bottom
            )
        )
    }

    // MARK: - Stats Panel

    private func statsPanel(profile: FriendProfileResponse) -> some View {
        HStack {
            statItem(value: "\(profile.totalWorkouts)", label: "QUESTS")
            Spacer()
            statItem(value: "\(profile.currentStreak)", label: "STREAK")
            Spacer()
            statItem(value: "\(profile.totalPrs)", label: "PRs")
        }
        .padding(16)
        .background(Color.voidMedium)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .cornerRadius(4)
        .padding(.horizontal, 16)
    }

    private func statItem(value: String, label: String) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.ariseDisplay(size: 24, weight: .bold))
                .foregroundColor(.systemPrimary)
            Text(label)
                .font(.ariseMono(size: 10))
                .foregroundColor(.textMuted)
                .tracking(1)
        }
    }

    // MARK: - Action Buttons

    private var actionButtons: some View {
        VStack(spacing: 10) {
            // Challenge button (placeholder)
            Button(action: {
                // TODO: Implement challenge feature
            }) {
                HStack {
                    Image(systemName: "flag.fill")
                    Text("CHALLENGE")
                        .font(.ariseHeader(size: 13, weight: .bold))
                        .tracking(1)
                }
                .foregroundColor(.gold)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.gold, lineWidth: 1)
                )
            }
            .buttonStyle(PlainButtonStyle())

            // Remove friend button
            Button(action: { showRemoveConfirmation = true }) {
                HStack {
                    Image(systemName: "person.badge.minus")
                    Text("REMOVE FRIEND")
                        .font(.ariseHeader(size: 13, weight: .bold))
                        .tracking(1)
                }
                .foregroundColor(.warningRed)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.warningRed, lineWidth: 1)
                )
            }
            .buttonStyle(PlainButtonStyle())
        }
        .padding(.horizontal, 16)
    }

    // MARK: - Recent Activity

    private func recentActivitySection(profile: FriendProfileResponse) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            // Section header
            Text("[ RECENT ACTIVITY ]")
                .font(.ariseMono(size: 10))
                .foregroundColor(.systemPrimary)
                .tracking(2)
                .padding(.horizontal, 16)

            VStack(spacing: 8) {
                ForEach(profile.recentWorkouts) { workout in
                    activityCard(workout: workout)
                }
            }
            .padding(.horizontal, 16)
        }
    }

    private func activityCard(workout: RecentWorkoutSummary) -> some View {
        HStack(spacing: 12) {
            // Icon
            ZStack {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.voidLight)
                    .frame(width: 36, height: 36)
                Image(systemName: "dumbbell.fill")
                    .font(.system(size: 16))
                    .foregroundColor(.systemPrimary)
            }

            // Info
            VStack(alignment: .leading, spacing: 2) {
                Text(workout.exerciseNames.first ?? "Workout")
                    .font(.ariseHeader(size: 13, weight: .medium))
                    .foregroundColor(.textPrimary)
                Text(formatWorkoutDate(workout.date))
                    .font(.ariseMono(size: 10))
                    .foregroundColor(.textMuted)
            }

            Spacer()

            // XP earned if available
            if let xp = workout.xpEarned {
                Text("+\(xp) XP")
                    .font(.ariseMono(size: 12, weight: .bold))
                    .foregroundColor(.gold)
            }
        }
        .padding(12)
        .background(Color.voidMedium)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .cornerRadius(4)
    }

    private func formatWorkoutDate(_ dateString: String) -> String {
        guard let date = dateString.parseISO8601Date() else {
            return dateString
        }

        let now = Date()
        let calendar = Calendar.current
        let daysDiff = calendar.dateComponents([.day], from: date, to: now).day ?? 0

        if calendar.isDateInToday(date) {
            let formatter = DateFormatter()
            formatter.dateFormat = "h:mm a"
            return "Today at \(formatter.string(from: date))"
        } else if calendar.isDateInYesterday(date) {
            return "Yesterday"
        } else if daysDiff < 7 {
            return "\(daysDiff) days ago"
        } else {
            let formatter = DateFormatter()
            formatter.dateFormat = "MMM d"
            return formatter.string(from: date)
        }
    }
}

#Preview {
    // Preview would need sample data
    Color.voidBlack
}
