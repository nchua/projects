import SwiftUI

/// Compact Hunter Network section embedded in the Hunter tab (ARISE v2 §8.4).
/// Replaces the old full-screen Friends tab: inline request-accept rows on top,
/// then the friend list. Reuses FriendsViewModel, AddFriendSheet, FriendProfileView.
struct HunterNetworkSection: View {
    @StateObject private var viewModel = FriendsViewModel()
    @State private var showAddFriendSheet = false
    @State private var selectedFriend: FriendResponse?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                AriseSectionHeader(title: "Hunter Network")

                Spacer()

                Button(action: { showAddFriendSheet = true }) {
                    Image(systemName: "plus")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.systemPrimary)
                        .frame(width: 28, height: 28)
                        .background(Color.voidLight)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.ariseBorder, lineWidth: 1)
                        )
                        .cornerRadius(4)
                }
                .accessibilityLabel("Add hunter")
            }
            .padding(.horizontal)

            VStack(spacing: 10) {
                // Inline incoming requests (accept/decline without leaving the tab)
                ForEach(viewModel.incomingRequests) { request in
                    FriendRequestCard(
                        request: request,
                        isIncoming: true,
                        onAccept: {
                            Task { await viewModel.acceptRequest(id: request.id) }
                        },
                        onDecline: {
                            Task { await viewModel.rejectRequest(id: request.id) }
                        }
                    )
                }

                // Friend list
                if viewModel.friends.isEmpty && viewModel.incomingRequests.isEmpty && !viewModel.isLoading {
                    EmptyFriendsView()
                } else {
                    ForEach(viewModel.friends) { friend in
                        FriendRowCard(friend: friend) {
                            selectedFriend = friend
                        }
                    }
                }
            }
            .padding(.horizontal)
        }
        .sheet(isPresented: $showAddFriendSheet) {
            AddFriendSheet(viewModel: viewModel)
        }
        .sheet(item: $selectedFriend) { friend in
            FriendProfileView(friend: friend, viewModel: viewModel)
        }
        .task {
            await viewModel.loadAll()
        }
    }
}

/// Empty state shown when the hunter has no friends and no pending requests.
struct EmptyFriendsView: View {
    var body: some View {
        VStack(spacing: 16) {
            ZStack {
                Circle()
                    .fill(Color.voidLight)
                    .frame(width: 64, height: 64)
                Image(systemName: "person.2")
                    .font(.system(size: 28))
                    .foregroundColor(.textMuted)
            }

            Text("No hunters in your network yet")
                .font(.ariseHeader(size: 14, weight: .semibold))
                .foregroundColor(.textPrimary)

            Text("Search for other hunters by username\nto add them to your network and\ntrack their progress.")
                .font(.ariseMono(size: 11))
                .foregroundColor(.textMuted)
                .multilineTextAlignment(.center)
                .lineSpacing(4)
        }
        .padding(40)
        .frame(maxWidth: .infinity)
        .background(Color.voidMedium)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .cornerRadius(4)
    }
}

#Preview {
    ScrollView {
        HunterNetworkSection()
    }
    .background(Color.voidBlack)
}
