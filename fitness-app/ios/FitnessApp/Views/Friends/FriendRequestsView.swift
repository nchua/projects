import SwiftUI

struct FriendRequestsView: View {
    @ObservedObject var viewModel: FriendsViewModel

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                // Incoming Requests
                if !viewModel.incomingRequests.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        // Section header
                        HStack(spacing: 8) {
                            Text("[ INCOMING REQUESTS ]")
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.systemPrimary)
                                .tracking(2)

                            Text("\(viewModel.incomingRequests.count)")
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textSecondary)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 2)
                                .background(Color.voidLight)
                                .cornerRadius(10)
                        }

                        ForEach(viewModel.incomingRequests) { request in
                            FriendRequestCard(
                                request: request,
                                isIncoming: true,
                                onAccept: {
                                    Task {
                                        await viewModel.acceptRequest(id: request.id)
                                    }
                                },
                                onDecline: {
                                    Task {
                                        await viewModel.rejectRequest(id: request.id)
                                    }
                                }
                            )
                        }
                    }
                }

                // Divider between sections
                if !viewModel.incomingRequests.isEmpty && !viewModel.sentRequests.isEmpty {
                    Rectangle()
                        .fill(Color.ariseBorder)
                        .frame(height: 1)
                        .padding(.vertical, 4)
                }

                // Sent Requests
                if !viewModel.sentRequests.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        // Section header
                        HStack(spacing: 8) {
                            Text("[ SENT REQUESTS ]")
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.systemPrimary)
                                .tracking(2)

                            Text("\(viewModel.sentRequests.count)")
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textSecondary)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 2)
                                .background(Color.voidLight)
                                .cornerRadius(10)
                        }

                        ForEach(viewModel.sentRequests) { request in
                            FriendRequestCard(
                                request: request,
                                isIncoming: false,
                                onCancel: {
                                    Task {
                                        await viewModel.cancelRequest(id: request.id)
                                    }
                                }
                            )
                        }
                    }
                }

                // Empty state
                if viewModel.incomingRequests.isEmpty && viewModel.sentRequests.isEmpty {
                    EmptyRequestsView()
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 100)
        }
    }
}

struct EmptyRequestsView: View {
    var body: some View {
        VStack(spacing: 16) {
            ZStack {
                Circle()
                    .fill(Color.voidLight)
                    .frame(width: 64, height: 64)
                Image(systemName: "envelope")
                    .font(.system(size: 28))
                    .foregroundColor(.textMuted)
            }

            Text("No pending requests")
                .font(.ariseHeader(size: 14, weight: .semibold))
                .foregroundColor(.textPrimary)

            Text("Friend requests you send or receive\nwill appear here")
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
    FriendRequestsView(viewModel: FriendsViewModel())
        .background(Color.voidBlack)
}
