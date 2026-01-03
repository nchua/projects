import SwiftUI
import SwiftData

@main
struct FitnessApp: App {
    let modelContainer: ModelContainer
    @StateObject private var authManager = AuthManager.shared

    init() {
        do {
            let schema = Schema([
                User.self,
                Exercise.self,
                WorkoutSession.self,
                WorkoutExercise.self,
                ExerciseSet.self,
                BodyweightEntry.self,
                PersonalRecord.self
            ])
            let modelConfiguration = ModelConfiguration(schema: schema, isStoredInMemoryOnly: false)
            modelContainer = try ModelContainer(for: schema, configurations: [modelConfiguration])
        } catch {
            fatalError("Could not initialize ModelContainer: \(error)")
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(authManager)
                .preferredColorScheme(.dark)
        }
        .modelContainer(modelContainer)
    }
}
