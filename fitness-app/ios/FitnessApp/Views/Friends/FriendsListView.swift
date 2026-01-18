import SwiftUI

struct FriendsListView: View {
    @ObservedObject var viewModel: FriendsViewModel
    @Binding var selectedFriend: FriendResponse?

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                if viewModel.friends.isEmpty && !viewModel.isLoading {
                    EmptyFriendsView()
                } else {
                    ForEach(viewModel.friends) { friend in
                        FriendRowCard(friend: friend) {
                            selectedFriend = friend
                        }
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 100)
        }
    }
}

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
    FriendsListView(viewModel: FriendsViewModel(), selectedFriend: .constant(nil))
        .background(Color.voidBlack)
}
