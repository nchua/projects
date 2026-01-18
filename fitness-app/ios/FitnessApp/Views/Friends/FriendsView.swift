import SwiftUI

struct FriendsView: View {
    @StateObject private var viewModel = FriendsViewModel()
    @State private var selectedTab = 0
    @State private var showAddFriendSheet = false
    @State private var selectedFriend: FriendResponse?

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                VStack(spacing: 0) {
                    // Header
                    header

                    // Segment control
                    segmentControl

                    // Content
                    if viewModel.isLoading && viewModel.friends.isEmpty {
                        loadingView
                    } else {
                        TabView(selection: $selectedTab) {
                            FriendsListView(viewModel: viewModel, selectedFriend: $selectedFriend)
                                .tag(0)

                            FriendRequestsView(viewModel: viewModel)
                                .tag(1)
                        }
                        .tabViewStyle(.page(indexDisplayMode: .never))
                    }
                }
            }
            .navigationBarHidden(true)
            .sheet(isPresented: $showAddFriendSheet) {
                AddFriendSheet(viewModel: viewModel)
            }
            .sheet(item: $selectedFriend) { friend in
                FriendProfileView(friend: friend, viewModel: viewModel)
            }
            .task {
                await viewModel.loadAll()
            }
            .refreshable {
                await viewModel.loadAll()
            }
        }
    }

    // MARK: - Header

    private var header: some View {
        VStack(spacing: 8) {
            // Tag
            Text("[ HUNTER NETWORK ]")
                .font(.ariseMono(size: 10))
                .foregroundColor(.systemPrimary)
                .tracking(2)

            // Title row
            HStack {
                Text("Friends")
                    .font(.ariseHeader(size: 20, weight: .bold))
                    .foregroundColor(.textPrimary)

                Spacer()

                // Add button
                Button(action: { showAddFriendSheet = true }) {
                    Image(systemName: "plus")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundColor(.systemPrimary)
                        .frame(width: 36, height: 36)
                        .background(Color.voidLight)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.ariseBorder, lineWidth: 1)
                        )
                        .cornerRadius(4)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 16)
        .padding(.bottom, 16)
        .background(Color.voidMedium)
        .overlay(
            Rectangle()
                .fill(Color.systemPrimary)
                .frame(height: 2),
            alignment: .top
        )
        .overlay(
            Rectangle()
                .fill(Color.ariseBorder)
                .frame(height: 1),
            alignment: .bottom
        )
    }

    // MARK: - Segment Control

    private var segmentControl: some View {
        HStack(spacing: 0) {
            // All Friends tab
            Button(action: { withAnimation { selectedTab = 0 } }) {
                Text("ALL FRIENDS")
                    .font(.ariseHeader(size: 12, weight: .semibold))
                    .tracking(1)
                    .foregroundColor(selectedTab == 0 ? .voidBlack : .textSecondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(selectedTab == 0 ? Color.systemPrimary : Color.clear)
                    .cornerRadius(2)
            }
            .buttonStyle(PlainButtonStyle())

            // Requests tab
            Button(action: { withAnimation { selectedTab = 1 } }) {
                HStack(spacing: 6) {
                    Text("REQUESTS")
                        .font(.ariseHeader(size: 12, weight: .semibold))
                        .tracking(1)

                    if viewModel.totalPendingRequests > 0 {
                        Text("\(viewModel.totalPendingRequests)")
                            .font(.ariseMono(size: 10, weight: .bold))
                            .foregroundColor(selectedTab == 1 ? .systemPrimary : .white)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(selectedTab == 1 ? Color.voidBlack : Color.warningRed)
                            .cornerRadius(10)
                    }
                }
                .foregroundColor(selectedTab == 1 ? .voidBlack : .textSecondary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 10)
                .background(selectedTab == 1 ? Color.systemPrimary : Color.clear)
                .cornerRadius(2)
            }
            .buttonStyle(PlainButtonStyle())
        }
        .padding(4)
        .background(Color.voidDark)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .cornerRadius(4)
        .padding(.horizontal, 16)
        .padding(.vertical, 16)
    }

    // MARK: - Loading View

    private var loadingView: some View {
        VStack {
            Spacer()
            ProgressView()
                .tint(.systemPrimary)
                .scaleEffect(1.5)
            Spacer()
        }
    }
}

#Preview {
    FriendsView()
}
