import Foundation
@testable import FitnessApp

/// Mock API client for testing purposes.
/// Allows tests to control API responses without making actual network calls.
class MockAPIClient {

    // MARK: - Mock Response Storage

    /// Goals endpoints
    var mockGoalsListResponse: GoalsListResponse?
    var mockGoalResponse: GoalResponse?
    var mockGoalBatchResponse: GoalBatchCreateResponse?
    var mockGoalsError: Error?

    /// Mission endpoints
    var mockCurrentMissionResponse: CurrentMissionResponse?
    var mockMissionAcceptResponse: MissionAcceptResponse?
    var mockMissionError: Error?

    // MARK: - Call Tracking

    /// Track which methods were called and with what arguments
    var createGoalsCalled = false
    var createGoalsBatchCalled = false
    var lastBatchGoals: [GoalCreate]?

    var listGoalsCalled = false
    var lastIncludeInactive: Bool?

    var fetchCurrentMissionCalled = false
    var acceptMissionCalled = false
    var lastAcceptedMissionId: String?

    // MARK: - Configuration

    /// Simulated network delay (seconds)
    var simulatedDelay: TimeInterval = 0

    /// Whether to simulate errors
    var shouldSimulateError = false

    // MARK: - Goals API

    func createGoal(_ goal: GoalCreate) async throws -> GoalResponse {
        createGoalsCalled = true

        if simulatedDelay > 0 {
            try await Task.sleep(nanoseconds: UInt64(simulatedDelay * 1_000_000_000))
        }

        if shouldSimulateError, let error = mockGoalsError {
            throw error
        }

        guard let response = mockGoalResponse else {
            throw MockAPIError.noMockResponse
        }

        return response
    }

    func createGoalsBatch(_ goals: [GoalCreate]) async throws -> GoalBatchCreateResponse {
        createGoalsBatchCalled = true
        lastBatchGoals = goals

        if simulatedDelay > 0 {
            try await Task.sleep(nanoseconds: UInt64(simulatedDelay * 1_000_000_000))
        }

        if shouldSimulateError, let error = mockGoalsError {
            throw error
        }

        guard let response = mockGoalBatchResponse else {
            throw MockAPIError.noMockResponse
        }

        return response
    }

    func listGoals(includeInactive: Bool = false) async throws -> GoalsListResponse {
        listGoalsCalled = true
        lastIncludeInactive = includeInactive

        if simulatedDelay > 0 {
            try await Task.sleep(nanoseconds: UInt64(simulatedDelay * 1_000_000_000))
        }

        if shouldSimulateError, let error = mockGoalsError {
            throw error
        }

        guard let response = mockGoalsListResponse else {
            throw MockAPIError.noMockResponse
        }

        return response
    }

    // MARK: - Mission API

    func fetchCurrentMission() async throws -> CurrentMissionResponse {
        fetchCurrentMissionCalled = true

        if simulatedDelay > 0 {
            try await Task.sleep(nanoseconds: UInt64(simulatedDelay * 1_000_000_000))
        }

        if shouldSimulateError, let error = mockMissionError {
            throw error
        }

        guard let response = mockCurrentMissionResponse else {
            throw MockAPIError.noMockResponse
        }

        return response
    }

    func acceptMission(_ missionId: String) async throws -> MissionAcceptResponse {
        acceptMissionCalled = true
        lastAcceptedMissionId = missionId

        if simulatedDelay > 0 {
            try await Task.sleep(nanoseconds: UInt64(simulatedDelay * 1_000_000_000))
        }

        if shouldSimulateError, let error = mockMissionError {
            throw error
        }

        guard let response = mockMissionAcceptResponse else {
            throw MockAPIError.noMockResponse
        }

        return response
    }

    // MARK: - Reset

    /// Reset all mock state for clean test runs
    func reset() {
        // Reset responses
        mockGoalsListResponse = nil
        mockGoalResponse = nil
        mockGoalBatchResponse = nil
        mockGoalsError = nil
        mockCurrentMissionResponse = nil
        mockMissionAcceptResponse = nil
        mockMissionError = nil

        // Reset call tracking
        createGoalsCalled = false
        createGoalsBatchCalled = false
        lastBatchGoals = nil
        listGoalsCalled = false
        lastIncludeInactive = nil
        fetchCurrentMissionCalled = false
        acceptMissionCalled = false
        lastAcceptedMissionId = nil

        // Reset configuration
        simulatedDelay = 0
        shouldSimulateError = false
    }
}

// MARK: - Mock Errors

enum MockAPIError: Error, LocalizedError {
    case noMockResponse
    case networkError
    case serverError(code: Int, message: String)
    case decodingError

    var errorDescription: String? {
        switch self {
        case .noMockResponse:
            return "No mock response configured"
        case .networkError:
            return "Network error"
        case .serverError(let code, let message):
            return "Server error \(code): \(message)"
        case .decodingError:
            return "Failed to decode response"
        }
    }
}
