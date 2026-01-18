import SwiftUI

@MainActor
class FriendsViewModel: ObservableObject {
    // MARK: - Published Properties

    @Published var friends: [FriendResponse] = []
    @Published var incomingRequests: [FriendRequestResponse] = []
    @Published var sentRequests: [FriendRequestResponse] = []
    @Published var searchResults: [UserPublicResponse] = []
    @Published var selectedFriendProfile: FriendProfileResponse?

    @Published var isLoading = false
    @Published var isSearching = false
    @Published var isSendingRequest = false
    @Published var error: String?
    @Published var successMessage: String?

    // Track pending request states for search results
    @Published var pendingRequestUserIds: Set<String> = []
    @Published var friendUserIds: Set<String> = []

    // MARK: - Computed Properties

    var totalPendingRequests: Int {
        incomingRequests.count
    }

    var hasPendingRequests: Bool {
        !incomingRequests.isEmpty
    }

    // MARK: - Load Data

    func loadFriends() async {
        isLoading = true
        error = nil

        do {
            friends = try await APIClient.shared.getFriends()
            friendUserIds = Set(friends.map { $0.friendId })
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func loadRequests() async {
        do {
            let response = try await APIClient.shared.getFriendRequests()
            incomingRequests = response.incoming
            sentRequests = response.sent
            pendingRequestUserIds = Set(sentRequests.map { $0.receiverId })
        } catch {
            self.error = error.localizedDescription
        }
    }

    func loadAll() async {
        isLoading = true
        error = nil

        async let friendsTask: () = loadFriends()
        async let requestsTask: () = loadRequests()

        _ = await (friendsTask, requestsTask)
        isLoading = false
    }

    // MARK: - Search Users

    func searchUsers(query: String) async {
        guard !query.isEmpty else {
            searchResults = []
            return
        }

        isSearching = true

        do {
            searchResults = try await APIClient.shared.searchUsers(query: query, limit: 20)
        } catch {
            self.error = error.localizedDescription
        }

        isSearching = false
    }

    // MARK: - Friend Request Actions

    func sendFriendRequest(to userId: String) async {
        isSendingRequest = true
        error = nil

        do {
            let response = try await APIClient.shared.sendFriendRequest(userId: userId)

            // If auto-accepted (they already sent us a request), reload friends
            if response.status == "accepted" {
                await loadFriends()
                successMessage = "You're now friends!"
            } else {
                pendingRequestUserIds.insert(userId)
                await loadRequests()
                successMessage = "Friend request sent!"
            }
        } catch {
            self.error = error.localizedDescription
        }

        isSendingRequest = false
    }

    func acceptRequest(id: String) async {
        do {
            _ = try await APIClient.shared.acceptFriendRequest(id: id)
            await loadAll()
            successMessage = "Friend request accepted!"
        } catch {
            self.error = error.localizedDescription
        }
    }

    func rejectRequest(id: String) async {
        do {
            try await APIClient.shared.rejectFriendRequest(id: id)
            incomingRequests.removeAll { $0.id == id }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func cancelRequest(id: String) async {
        do {
            try await APIClient.shared.cancelFriendRequest(id: id)
            if let request = sentRequests.first(where: { $0.id == id }) {
                pendingRequestUserIds.remove(request.receiverId)
            }
            sentRequests.removeAll { $0.id == id }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func removeFriend(userId: String) async {
        do {
            try await APIClient.shared.removeFriend(userId: userId)
            friends.removeAll { $0.friendId == userId }
            friendUserIds.remove(userId)
            successMessage = "Friend removed"
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - Friend Profile

    func loadFriendProfile(userId: String) async {
        do {
            selectedFriendProfile = try await APIClient.shared.getFriendProfile(userId: userId)
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - Helpers

    func requestStatus(for userId: String) -> RequestStatus {
        if friendUserIds.contains(userId) {
            return .friends
        } else if pendingRequestUserIds.contains(userId) {
            return .pending
        } else if incomingRequests.contains(where: { $0.senderId == userId }) {
            return .incoming
        }
        return .none
    }

    func clearMessages() {
        error = nil
        successMessage = nil
    }

    enum RequestStatus {
        case none
        case pending
        case incoming
        case friends
    }
}
