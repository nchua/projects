import Foundation

class APIClient {
    static let shared = APIClient()

    #if DEBUG
    // Use Railway production URL (works from anywhere)
    // Switch to local IP for offline dev: "http://192.168.0.72:8000"
    private let baseURL = "https://backend-production-e316.up.railway.app"
    #else
    private let baseURL = "https://backend-production-e316.up.railway.app"
    #endif

    private var accessToken: String? {
        get { UserDefaults.standard.string(forKey: "accessToken") }
        set { UserDefaults.standard.set(newValue, forKey: "accessToken") }
    }

    private var refreshToken: String? {
        get { UserDefaults.standard.string(forKey: "refreshToken") }
        set { UserDefaults.standard.set(newValue, forKey: "refreshToken") }
    }

    /// Callback for when session expires and user needs to re-authenticate
    var onSessionExpired: (() -> Void)?

    private init() {}

    // MARK: - Auth

    func register(email: String, password: String) async throws -> AuthResponse {
        let body = ["email": email, "password": password]
        return try await post("/auth/register", body: body)
    }

    func login(email: String, password: String) async throws -> AuthResponse {
        let body = ["email": email, "password": password]
        let response: AuthResponse = try await post("/auth/login", body: body)
        self.accessToken = response.accessToken
        self.refreshToken = response.refreshToken
        return response
    }

    func refreshAccessToken() async throws -> AuthResponse {
        guard let refreshToken = refreshToken else {
            throw APIError.unauthorized
        }
        let body = ["refresh_token": refreshToken]
        let response: AuthResponse = try await post("/auth/refresh", body: body)
        self.accessToken = response.accessToken
        self.refreshToken = response.refreshToken
        return response
    }

    func logout() {
        accessToken = nil
        refreshToken = nil
    }

    // MARK: - Password Reset

    func requestPasswordReset(email: String) async throws -> PasswordResetResponse {
        let body = PasswordResetRequest(email: email)
        return try await postUnauthenticated("/auth/password-reset/request", body: body)
    }

    func verifyPasswordReset(email: String, code: String, newPassword: String) async throws -> PasswordResetResponse {
        let body = PasswordResetVerify(email: email, code: code, newPassword: newPassword)
        return try await postUnauthenticated("/auth/password-reset/verify", body: body)
    }

    // MARK: - Profile

    func getProfile() async throws -> ProfileResponse {
        return try await get("/profile")
    }

    func updateProfile(_ profile: ProfileUpdate) async throws -> ProfileResponse {
        return try await put("/profile", body: profile)
    }

    // MARK: - Username

    func checkUsernameAvailability(_ username: String) async throws -> UsernameCheckResponse {
        let encodedUsername = username.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? username
        return try await get("/users/username/check?username=\(encodedUsername)")
    }

    func setUsername(_ username: String) async throws {
        struct SetUsernameResponse: Decodable {
            let message: String
            let username: String
        }
        let body = UsernameUpdate(username: username)
        let _: SetUsernameResponse = try await put("/users/username", body: body)
    }

    func searchUsers(query: String, limit: Int = 20) async throws -> [UserPublicResponse] {
        let encodedQuery = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
        return try await get("/users/search?q=\(encodedQuery)&limit=\(limit)")
    }

    // MARK: - Exercises

    func getExercises(category: String? = nil, search: String? = nil) async throws -> [ExerciseResponse] {
        var path = "/exercises"
        var params: [String] = []
        if let category = category { params.append("category=\(category)") }
        if let search = search { params.append("search=\(search)") }
        if !params.isEmpty { path += "?" + params.joined(separator: "&") }
        return try await get(path)
    }

    // MARK: - Workouts

    func getWorkouts(limit: Int = 20, offset: Int = 0) async throws -> [WorkoutSummaryResponse] {
        return try await get("/workouts?limit=\(limit)&offset=\(offset)")
    }

    func getWorkout(id: String) async throws -> WorkoutResponse {
        return try await get("/workouts/\(id)")
    }

    func createWorkout(_ workout: WorkoutCreate) async throws -> WorkoutResponse {
        return try await post("/workouts", body: workout)
    }

    func deleteWorkout(id: String) async throws {
        try await delete("/workouts/\(id)")
    }

    // MARK: - Bodyweight

    func logBodyweight(_ entry: BodyweightCreate) async throws -> BodyweightResponse {
        return try await post("/bodyweight", body: entry)
    }

    func getBodyweightHistory(limit: Int = 100) async throws -> BodyweightHistoryResponse {
        return try await get("/bodyweight?limit=\(limit)")
    }

    func deleteBodyweight(id: String) async throws {
        try await delete("/bodyweight/\(id)")
    }

    // MARK: - Analytics

    func getExerciseTrend(exerciseId: String, timeRange: String = "12w", includeSets: Bool = false) async throws -> TrendResponse {
        var path = "/analytics/exercise/\(exerciseId)/trend?time_range=\(timeRange)"
        if includeSets {
            path += "&include_sets=true"
        }
        return try await get(path)
    }

    func getPercentiles() async throws -> PercentilesResponse {
        return try await get("/analytics/percentiles")
    }

    func getPRs(exerciseId: String? = nil, prType: String? = nil) async throws -> PRListResponse {
        var path = "/analytics/prs"
        var params: [String] = []
        if let exerciseId = exerciseId { params.append("exercise_id=\(exerciseId)") }
        if let prType = prType { params.append("pr_type=\(prType)") }
        if !params.isEmpty { path += "?" + params.joined(separator: "&") }
        return try await get(path)
    }

    func getInsights() async throws -> InsightsResponse {
        return try await get("/analytics/insights")
    }

    func getWeeklyReview() async throws -> WeeklyReviewResponse {
        return try await get("/analytics/weekly-review")
    }

    func getCooldownStatus() async throws -> CooldownResponse {
        return try await get("/analytics/cooldowns")
    }

    // MARK: - Sync

    func sync(_ data: SyncRequest) async throws -> SyncResponse {
        return try await post("/sync", body: data)
    }

    func getSyncStatus() async throws -> SyncStatusResponse {
        return try await get("/sync/status")
    }

    // MARK: - Progress & Achievements

    func getUserProgress() async throws -> UserProgressResponse {
        return try await get("/progress")
    }

    func getAchievements() async throws -> AchievementsListResponse {
        return try await get("/progress/achievements")
    }

    func getRecentAchievements(limit: Int = 5) async throws -> RecentAchievementsResponse {
        return try await get("/progress/achievements/recent?limit=\(limit)")
    }

    func checkAchievements() async throws -> [AchievementUnlockedResponse] {
        struct CheckResponse: Decodable {
            let achievementsUnlocked: [AchievementUnlockedResponse]
            let count: Int

            enum CodingKeys: String, CodingKey {
                case achievementsUnlocked = "achievements_unlocked"
                case count
            }
        }
        let response: CheckResponse = try await post("/progress/check-achievements", body: EmptyBody())
        return response.achievementsUnlocked
    }

    func seedAchievements() async throws {
        struct SeedResponse: Decodable {
            let message: String
        }
        let _: SeedResponse = try await post("/progress/seed-achievements", body: EmptyBody())
    }

    // MARK: - Workouts (with XP)

    func createWorkoutWithXP(_ workout: WorkoutCreate) async throws -> WorkoutCreateResponse {
        return try await post("/workouts", body: workout)
    }

    // MARK: - Quests

    func getDailyQuests() async throws -> DailyQuestsResponse {
        return try await get("/quests")
    }

    func claimQuestReward(questId: String) async throws -> QuestClaimResponse {
        return try await post("/quests/\(questId)/claim", body: EmptyBody())
    }

    func refreshQuests() async throws -> DailyQuestsResponse {
        return try await post("/quests/refresh", body: EmptyBody())
    }

    func seedQuests() async throws {
        struct SeedResponse: Decodable {
            let message: String
            let questsCreated: Int

            enum CodingKeys: String, CodingKey {
                case message
                case questsCreated = "quests_created"
            }
        }
        let _: SeedResponse = try await post("/quests/seed", body: EmptyBody())
    }

    // MARK: - Dungeons

    func getDungeons() async throws -> DungeonsResponse {
        return try await get("/dungeons")
    }

    func getDungeon(id: String) async throws -> DungeonResponse {
        return try await get("/dungeons/\(id)")
    }

    func acceptDungeon(id: String) async throws -> DungeonAcceptResponse {
        return try await post("/dungeons/\(id)/accept", body: EmptyBody())
    }

    func abandonDungeon(id: String) async throws -> DungeonAbandonResponse {
        return try await post("/dungeons/\(id)/abandon", body: EmptyBody())
    }

    func claimDungeonReward(id: String) async throws -> DungeonClaimResponse {
        return try await post("/dungeons/\(id)/claim", body: EmptyBody())
    }

    func getDungeonHistory(skip: Int = 0, limit: Int = 20) async throws -> DungeonHistoryResponse {
        return try await get("/dungeons/history?skip=\(skip)&limit=\(limit)")
    }

    func forceSpawnDungeon() async throws -> DungeonSpawnedResponse? {
        struct SpawnResponse: Decodable {
            let spawned: Bool
            let dungeon: DungeonSpawnedResponse?
            let message: String?
        }
        let response: SpawnResponse = try await post("/dungeons/spawn/force", body: EmptyBody())
        return response.dungeon
    }

    func forceSpawnRareDungeon() async throws -> DungeonSpawnedResponse? {
        struct SpawnResponse: Decodable {
            let spawned: Bool
            let dungeon: DungeonSpawnedResponse?
            let message: String?
        }
        let response: SpawnResponse = try await post("/dungeons/spawn/force-rare", body: EmptyBody())
        return response.dungeon
    }

    func seedDungeons() async throws {
        struct SeedResponse: Decodable {
            let message: String
            let dungeonsCreated: Int

            enum CodingKeys: String, CodingKey {
                case message
                case dungeonsCreated = "dungeons_created"
            }
        }
        let _: SeedResponse = try await post("/dungeons/seed", body: EmptyBody())
    }

    // MARK: - Goals & Missions

    func getGoals() async throws -> GoalsListResponse {
        return try await get("/goals")
    }

    func createGoal(_ goal: GoalCreate) async throws -> GoalResponse {
        return try await post("/goals", body: goal)
    }

    func createGoalsBatch(_ goals: [GoalCreate]) async throws -> GoalBatchCreateResponse {
        let batch = GoalBatchCreate(goals: goals)
        return try await post("/goals/batch", body: batch)
    }

    func updateGoal(id: String, _ goal: GoalUpdate) async throws -> GoalResponse {
        return try await put("/goals/\(id)", body: goal)
    }

    func deleteGoal(id: String) async throws {
        try await delete("/goals/\(id)")
    }

    func getGoalProgress(goalId: String) async throws -> GoalProgressResponse {
        return try await get("/goals/\(goalId)/progress")
    }

    func getCurrentMission() async throws -> CurrentMissionResponse {
        return try await get("/missions/current")
    }

    func getMission(id: String) async throws -> WeeklyMissionResponse {
        return try await get("/missions/\(id)")
    }

    func acceptMission(id: String) async throws -> MissionAcceptResponse {
        return try await post("/missions/\(id)/accept", body: EmptyBody())
    }

    func declineMission(id: String) async throws -> MissionDeclineResponse {
        return try await post("/missions/\(id)/decline", body: EmptyBody())
    }

    // MARK: - Friends

    func getFriends() async throws -> [FriendResponse] {
        return try await get("/friends")
    }

    func getFriendRequests() async throws -> FriendRequestsResponse {
        return try await get("/friends/requests")
    }

    func sendFriendRequest(userId: String) async throws -> FriendRequestResponse {
        struct RequestBody: Encodable {
            let receiverId: String
            enum CodingKeys: String, CodingKey {
                case receiverId = "receiver_id"
            }
        }
        return try await post("/friends/request", body: RequestBody(receiverId: userId))
    }

    func acceptFriendRequest(id: String) async throws -> FriendResponse {
        return try await post("/friends/accept/\(id)", body: EmptyBody())
    }

    func rejectFriendRequest(id: String) async throws {
        struct RejectResponse: Decodable {
            let message: String
        }
        let _: RejectResponse = try await post("/friends/reject/\(id)", body: EmptyBody())
    }

    func cancelFriendRequest(id: String) async throws {
        try await delete("/friends/cancel/\(id)")
    }

    func removeFriend(userId: String) async throws {
        try await delete("/friends/\(userId)")
    }

    func getFriendProfile(userId: String) async throws -> FriendProfileResponse {
        return try await get("/friends/\(userId)/profile")
    }

    // MARK: - Activity (HealthKit Sync)

    func syncActivity(_ activity: ActivityCreate) async throws -> ActivityResponse {
        return try await post("/activity", body: activity)
    }

    func syncActivityBulk(_ activities: [ActivityCreate]) async throws -> [ActivityResponse] {
        return try await post("/activity/bulk", body: activities)
    }

    func getActivityHistory(limit: Int = 30, startDate: String? = nil, endDate: String? = nil) async throws -> ActivityHistoryResponse {
        var path = "/activity?limit=\(limit)"
        if let startDate = startDate { path += "&start_date=\(startDate)" }
        if let endDate = endDate { path += "&end_date=\(endDate)" }
        return try await get(path)
    }

    func getTodayActivity(source: String = "apple_fitness") async throws -> ActivityResponse? {
        do {
            return try await get("/activity/today?source=\(source)")
        } catch APIError.notFound {
            return nil
        }
    }

    func getLastSync(source: String = "apple_fitness") async throws -> LastSyncResponse {
        return try await get("/activity/last-sync?source=\(source)")
    }

    // MARK: - Screenshot Processing

    func processScreenshot(imageData: Data, filename: String, sessionDate: Date? = nil) async throws -> ScreenshotProcessResponse {
        guard let url = URL(string: baseURL + "/screenshot/process") else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 60 // Longer timeout for AI processing

        if let token = accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        // Create multipart form data
        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()

        // Add file field
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)

        // Determine content type from filename
        let contentType = filename.lowercased().hasSuffix(".png") ? "image/png" : "image/jpeg"
        body.append("Content-Type: \(contentType)\r\n\r\n".data(using: .utf8)!)
        body.append(imageData)
        body.append("\r\n".data(using: .utf8)!)

        // Add session_date field if provided
        if let date = sessionDate {
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyy-MM-dd"
            formatter.timeZone = .current
            let dateString = formatter.string(from: date)

            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"session_date\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(dateString)\r\n".data(using: .utf8)!)
        }

        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        request.httpBody = body

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch let error as URLError {
            switch error.code {
            case .notConnectedToInternet:
                throw APIError.networkError("No internet connection")
            case .timedOut:
                throw APIError.networkError("Processing timed out. Please try again.")
            case .cannotConnectToHost, .cannotFindHost:
                throw APIError.networkError("Cannot connect to server")
            default:
                throw APIError.networkError("Network error: \(error.localizedDescription)")
            }
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200...299:
            return try JSONDecoder().decode(ScreenshotProcessResponse.self, from: data)
        case 401:
            throw APIError.unauthorized
        case 422:
            // Extract actual error detail from response
            if let errorResponse = try? JSONDecoder().decode(ErrorResponse.self, from: data) {
                throw APIError.badRequest(errorResponse.detail ?? "Screenshot analysis failed")
            }
            throw APIError.badRequest("Screenshot analysis failed. Please try a different image.")
        default:
            throw APIError.serverError(httpResponse.statusCode)
        }
    }

    func processScreenshotsBatch(images: [(data: Data, filename: String)], saveWorkout: Bool = true, sessionDate: Date? = nil) async throws -> ScreenshotBatchResponse {
        guard let url = URL(string: baseURL + "/screenshot/process/batch") else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 120 // Longer timeout for multiple images

        if let token = accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        // Create multipart form data
        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()

        // Add each file
        for (_, image) in images.enumerated() {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"files\"; filename=\"\(image.filename)\"\r\n".data(using: .utf8)!)

            let contentType = image.filename.lowercased().hasSuffix(".png") ? "image/png" : "image/jpeg"
            body.append("Content-Type: \(contentType)\r\n\r\n".data(using: .utf8)!)
            body.append(image.data)
            body.append("\r\n".data(using: .utf8)!)
        }

        // Add save_workout field
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"save_workout\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(saveWorkout)\r\n".data(using: .utf8)!)

        // Add session_date field if provided
        if let date = sessionDate {
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyy-MM-dd"
            formatter.timeZone = .current
            let dateString = formatter.string(from: date)

            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"session_date\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(dateString)\r\n".data(using: .utf8)!)
        }

        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        request.httpBody = body

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch let error as URLError {
            switch error.code {
            case .notConnectedToInternet:
                throw APIError.networkError("No internet connection")
            case .timedOut:
                throw APIError.networkError("Processing timed out. Please try again.")
            case .cannotConnectToHost, .cannotFindHost:
                throw APIError.networkError("Cannot connect to server")
            default:
                throw APIError.networkError("Network error: \(error.localizedDescription)")
            }
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200...299:
            return try JSONDecoder().decode(ScreenshotBatchResponse.self, from: data)
        case 401:
            throw APIError.unauthorized
        case 422:
            // Extract actual error detail from response
            if let errorResponse = try? JSONDecoder().decode(ErrorResponse.self, from: data) {
                throw APIError.badRequest(errorResponse.detail ?? "Screenshot analysis failed")
            }
            throw APIError.badRequest("Screenshot analysis failed. Please try a different image.")
        default:
            throw APIError.serverError(httpResponse.statusCode)
        }
    }

    // MARK: - Private Helpers

    private func get<T: Decodable>(_ path: String) async throws -> T {
        return try await request(method: "GET", path: path, body: nil as EmptyBody?)
    }

    private func post<T: Decodable, B: Encodable>(_ path: String, body: B) async throws -> T {
        return try await request(method: "POST", path: path, body: body)
    }

    private func postUnauthenticated<T: Decodable, B: Encodable>(_ path: String, body: B) async throws -> T {
        return try await requestUnauthenticated(method: "POST", path: path, body: body)
    }

    private func put<T: Decodable, B: Encodable>(_ path: String, body: B) async throws -> T {
        return try await request(method: "PUT", path: path, body: body)
    }

    private func delete(_ path: String) async throws {
        let _: EmptyResponse = try await request(method: "DELETE", path: path, body: nil as EmptyBody?)
    }

    private func request<T: Decodable, B: Encodable>(method: String, path: String, body: B?, isRetry: Bool = false) async throws -> T {
        guard let url = URL(string: baseURL + path) else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 10 // 10 second timeout for faster feedback

        if let token = accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        if let body = body {
            request.httpBody = try JSONEncoder().encode(body)
        }

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch let error as URLError {
            switch error.code {
            case .notConnectedToInternet:
                throw APIError.networkError("No internet connection")
            case .timedOut:
                throw APIError.networkError("Request timed out. Check your connection.")
            case .cannotConnectToHost, .cannotFindHost:
                throw APIError.networkError("Cannot connect to server")
            default:
                throw APIError.networkError("Network error: \(error.localizedDescription)")
            }
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200...299:
            if T.self == EmptyResponse.self {
                return EmptyResponse() as! T
            }
            let decoder = JSONDecoder()
            // Using explicit CodingKeys in structs instead of automatic conversion
            // decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(T.self, from: data)
        case 401:
            // Try to refresh token if this isn't already a retry
            if !isRetry, refreshToken != nil {
                do {
                    _ = try await refreshAccessToken()
                    // Retry original request with new token
                    return try await self.request(method: method, path: path, body: body, isRetry: true)
                } catch {
                    // Refresh failed, user needs to log in again
                    // Notify app to redirect to login
                    Task { @MainActor in
                        self.onSessionExpired?()
                    }
                    throw APIError.unauthorized
                }
            }
            // No refresh token or already retried - session is expired
            Task { @MainActor in
                self.onSessionExpired?()
            }
            throw APIError.unauthorized
        case 400:
            // Extract error message from backend response
            if let errorResponse = try? JSONDecoder().decode(ErrorResponse.self, from: data) {
                throw APIError.badRequest(errorResponse.detail ?? "Bad request")
            }
            throw APIError.validationError
        case 404:
            throw APIError.notFound
        case 422:
            throw APIError.validationError
        default:
            throw APIError.serverError(httpResponse.statusCode)
        }
    }

    /// Make a request without authentication (for password reset, etc.)
    private func requestUnauthenticated<T: Decodable, B: Encodable>(method: String, path: String, body: B?) async throws -> T {
        guard let url = URL(string: baseURL + path) else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 10

        if let body = body {
            request.httpBody = try JSONEncoder().encode(body)
        }

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch let error as URLError {
            switch error.code {
            case .notConnectedToInternet:
                throw APIError.networkError("No internet connection")
            case .timedOut:
                throw APIError.networkError("Request timed out. Check your connection.")
            case .cannotConnectToHost, .cannotFindHost:
                throw APIError.networkError("Cannot connect to server")
            default:
                throw APIError.networkError("Network error: \(error.localizedDescription)")
            }
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200...299:
            return try JSONDecoder().decode(T.self, from: data)
        case 400:
            // Try to decode error message from response
            if let errorResponse = try? JSONDecoder().decode(ErrorResponse.self, from: data) {
                throw APIError.networkError(errorResponse.detail ?? "Bad request")
            }
            throw APIError.validationError
        case 422:
            throw APIError.validationError
        default:
            throw APIError.serverError(httpResponse.statusCode)
        }
    }
}

// Helper struct for decoding error responses
private struct ErrorResponse: Decodable {
    let detail: String?
}

// MARK: - API Types

struct EmptyBody: Encodable {}
struct EmptyResponse: Decodable {}

enum APIError: Error, LocalizedError {
    case invalidURL
    case invalidResponse
    case unauthorized
    case notFound
    case validationError
    case badRequest(String)
    case serverError(Int)
    case networkError(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        case .invalidResponse: return "Invalid response from server"
        case .unauthorized: return "Session expired. Please sign in again."
        case .notFound: return "Resource not found"
        case .validationError: return "Invalid data provided. Please check your input."
        case .badRequest(let message): return message
        case .serverError(let code): return "Server error: \(code)"
        case .networkError(let message): return message
        }
    }
}
