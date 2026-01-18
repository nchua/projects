import Foundation
import SwiftUI

@MainActor
class ProfileViewModel: ObservableObject {
    @Published var profile: ProfileResponse?
    @Published var bodyweightHistory: BodyweightHistoryResponse?
    @Published var userProgress: UserProgressResponse?
    @Published var achievements: [AchievementResponse] = []
    @Published var isLoading = false
    @Published var isSaving = false
    @Published var error: String?
    @Published var showBodyweightEntry = false
    @Published var successMessage: String?

    // Editable fields
    @Published var age: String = ""
    @Published var sex: String = ""
    @Published var bodyweight: String = ""
    @Published var heightFeet: String = ""
    @Published var heightInches: String = ""
    @Published var trainingExperience: String = ""
    @Published var preferredUnit: String = "lb"
    @Published var e1rmFormula: String = "epley"

    // Bodyweight entry
    @Published var newBodyweight: String = ""

    let sexOptions = ["", "M", "F"]
    let experienceOptions = ["", "beginner", "novice", "intermediate", "advanced", "elite"]
    let unitOptions = ["lb", "kg"]
    let formulaOptions = ["epley", "brzycki", "wathan", "lombardi"]

    // Computed properties for Hunter info
    var hunterLevel: Int { userProgress?.level ?? 1 }
    var hunterRank: HunterRank { HunterRank(rawValue: userProgress?.rank ?? "E") ?? .e }
    var totalWorkouts: Int { userProgress?.totalWorkouts ?? 0 }
    var currentStreak: Int { userProgress?.currentStreak ?? 0 }
    var totalPRs: Int { userProgress?.totalPrs ?? 0 }

    // Unlocked achievements for display
    var unlockedAchievements: [AchievementResponse] {
        achievements.filter { $0.unlocked }
    }

    // Featured achievements (up to 4 most recent unlocked)
    var featuredAchievements: [AchievementResponse] {
        Array(achievements.filter { $0.unlocked }.prefix(4))
    }

    // All achievements for the full list view
    var allAchievements: [AchievementResponse] {
        // Sort with unlocked first, then by name
        achievements.sorted { a, b in
            if a.unlocked != b.unlocked {
                return a.unlocked
            }
            return a.name < b.name
        }
    }

    func loadProfile() async {
        isLoading = true
        error = nil

        do {
            async let profileTask = APIClient.shared.getProfile()
            async let bodyweightTask = APIClient.shared.getBodyweightHistory(limit: 10)
            async let progressTask = APIClient.shared.getUserProgress()
            async let achievementsTask = APIClient.shared.getAchievements()

            let (profileResult, bodyweightResult, progressResult, achievementsResult) = try await (
                profileTask,
                bodyweightTask,
                progressTask,
                achievementsTask
            )

            profile = profileResult
            bodyweightHistory = bodyweightResult
            userProgress = progressResult
            achievements = achievementsResult.achievements

            // Populate editable fields
            age = profileResult.age.map { String($0) } ?? ""
            sex = profileResult.sex ?? ""
            bodyweight = profileResult.bodyweightLb.map { String(format: "%.1f", $0) } ?? ""
            if let inches = profileResult.heightInches {
                heightFeet = String(Int(inches) / 12)
                heightInches = String(Int(inches) % 12)
            }
            trainingExperience = profileResult.trainingExperience ?? ""
            preferredUnit = profileResult.preferredUnit ?? "lb"
            e1rmFormula = profileResult.e1rmFormula ?? "epley"

        } catch let apiError as APIError {
            // Don't set error for unauthorized - user will be redirected to login
            if case .unauthorized = apiError {
                return
            }
            self.error = apiError.localizedDescription
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func saveProfile() async {
        isSaving = true
        error = nil

        // Compute total height in inches from feet + inches
        var totalHeightInches: Double? = nil
        if let feet = Int(heightFeet), let inches = Int(heightInches) {
            totalHeightInches = Double(feet * 12 + inches)
        } else if let feet = Int(heightFeet) {
            totalHeightInches = Double(feet * 12)
        }

        let update = ProfileUpdate(
            age: Int(age),
            sex: sex.isEmpty ? nil : sex,
            bodyweightLb: Double(bodyweight),
            heightInches: totalHeightInches,
            trainingExperience: trainingExperience.isEmpty ? nil : trainingExperience,
            preferredUnit: preferredUnit,
            e1rmFormula: e1rmFormula
        )

        do {
            profile = try await APIClient.shared.updateProfile(update)
            successMessage = "Profile updated successfully"
        } catch let apiError as APIError {
            // Don't set error for unauthorized - user will be redirected to login
            if case .unauthorized = apiError {
                return
            }
            self.error = apiError.localizedDescription
        } catch {
            self.error = error.localizedDescription
        }

        isSaving = false
    }

    func logBodyweight() async {
        guard let weight = Double(newBodyweight), weight > 0 else {
            error = "Please enter a valid weight"
            return
        }

        isSaving = true
        error = nil

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withFullDate]

        let entry = BodyweightCreate(
            date: formatter.string(from: Date()),
            weight: weight,
            weightUnit: preferredUnit,
            source: "manual"
        )

        do {
            _ = try await APIClient.shared.logBodyweight(entry)
            bodyweightHistory = try await APIClient.shared.getBodyweightHistory(limit: 10)
            newBodyweight = ""
            showBodyweightEntry = false
            successMessage = "Bodyweight logged successfully"
        } catch let apiError as APIError {
            if case .unauthorized = apiError { return }
            self.error = apiError.localizedDescription
        } catch {
            self.error = error.localizedDescription
        }

        isSaving = false
    }

    func deleteBodyweight(id: String) async {
        do {
            try await APIClient.shared.deleteBodyweight(id: id)
            // Refresh history after deletion
            bodyweightHistory = try await APIClient.shared.getBodyweightHistory(limit: 10)
        } catch let apiError as APIError {
            if case .unauthorized = apiError { return }
            self.error = apiError.localizedDescription
        } catch {
            self.error = error.localizedDescription
        }
    }
}
