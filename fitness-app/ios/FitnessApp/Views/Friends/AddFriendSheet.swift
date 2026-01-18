import SwiftUI

struct AddFriendSheet: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var viewModel: FriendsViewModel
    @State private var searchText = ""
    @FocusState private var isSearchFocused: Bool

    var body: some View {
        NavigationStack {
            ZStack {
                Color.voidBlack.ignoresSafeArea()

                VStack(spacing: 0) {
                    // Header
                    HStack {
                        Text("Add Hunter")
                            .font(.ariseHeader(size: 18, weight: .bold))
                            .foregroundColor(.textPrimary)

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
                    .padding(.bottom, 16)

                    // Search input
                    VStack(spacing: 0) {
                        HStack {
                            Text("@")
                                .font(.ariseMono(size: 14))
                                .foregroundColor(.systemPrimary)

                            TextField("username", text: $searchText)
                                .font(.ariseMono(size: 14))
                                .foregroundColor(.textPrimary)
                                .autocapitalization(.none)
                                .disableAutocorrection(true)
                                .focused($isSearchFocused)
                                .onChange(of: searchText) { _, newValue in
                                    Task {
                                        // Debounce search
                                        try? await Task.sleep(nanoseconds: 300_000_000)
                                        if searchText == newValue {
                                            await viewModel.searchUsers(query: newValue)
                                        }
                                    }
                                }
                        }
                        .padding(12)
                        .background(Color.voidDark)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.systemPrimary, lineWidth: 2)
                        )
                        .cornerRadius(4)
                        .shadow(color: Color.systemPrimaryGlow, radius: 15)
                    }
                    .padding(.horizontal, 16)
                    .padding(.bottom, 20)

                    // Results
                    ScrollView {
                        VStack(spacing: 10) {
                            if viewModel.isSearching {
                                ProgressView()
                                    .tint(.systemPrimary)
                                    .padding(.top, 40)
                            } else if !searchText.isEmpty && viewModel.searchResults.isEmpty {
                                VStack(spacing: 12) {
                                    Text("No hunters found")
                                        .font(.ariseHeader(size: 14, weight: .semibold))
                                        .foregroundColor(.textSecondary)
                                    Text("Try a different username")
                                        .font(.ariseMono(size: 11))
                                        .foregroundColor(.textMuted)
                                }
                                .padding(.top, 40)
                            } else if !viewModel.searchResults.isEmpty {
                                // Section header
                                HStack {
                                    Text("[ SEARCH RESULTS ]")
                                        .font(.ariseMono(size: 10))
                                        .foregroundColor(.systemPrimary)
                                        .tracking(2)

                                    Text("\(viewModel.searchResults.count)")
                                        .font(.ariseMono(size: 10))
                                        .foregroundColor(.textSecondary)
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 2)
                                        .background(Color.voidLight)
                                        .cornerRadius(10)

                                    Spacer()
                                }
                                .padding(.horizontal, 16)
                                .padding(.bottom, 4)

                                ForEach(viewModel.searchResults) { user in
                                    SearchResultCard(
                                        user: user,
                                        status: viewModel.requestStatus(for: user.id),
                                        onAdd: {
                                            Task {
                                                await viewModel.sendFriendRequest(to: user.id)
                                            }
                                        }
                                    )
                                    .padding(.horizontal, 16)
                                }
                            } else if searchText.isEmpty {
                                // Empty state / instructions
                                VStack(spacing: 12) {
                                    Image(systemName: "magnifyingglass")
                                        .font(.system(size: 32))
                                        .foregroundColor(.textMuted)
                                    Text("Search by username")
                                        .font(.ariseHeader(size: 14, weight: .semibold))
                                        .foregroundColor(.textSecondary)
                                    Text("Enter a hunter's username\nto find them")
                                        .font(.ariseMono(size: 11))
                                        .foregroundColor(.textMuted)
                                        .multilineTextAlignment(.center)
                                }
                                .padding(.top, 60)
                            }
                        }
                        .padding(.bottom, 40)
                    }
                }
            }
            .navigationBarHidden(true)
            .onAppear {
                isSearchFocused = true
            }
            .alert("Success", isPresented: .constant(viewModel.successMessage != nil)) {
                Button("OK") {
                    viewModel.clearMessages()
                }
            } message: {
                Text(viewModel.successMessage ?? "")
            }
            .alert("Error", isPresented: .constant(viewModel.error != nil)) {
                Button("OK") {
                    viewModel.clearMessages()
                }
            } message: {
                Text(viewModel.error ?? "")
            }
        }
    }
}

#Preview {
    AddFriendSheet(viewModel: FriendsViewModel())
}
