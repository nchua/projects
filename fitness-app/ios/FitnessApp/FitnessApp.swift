import SwiftUI
import SwiftData

class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        Task { @MainActor in
            NotificationManager.shared.registerDeviceToken(deviceToken)
        }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        #if DEBUG
        print("DEBUG: Failed to register for remote notifications: \(error)")
        #endif
    }
}

@main
struct FitnessApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    let modelContainer: ModelContainer
    @StateObject private var authManager = AuthManager.shared
    @StateObject private var notificationManager = NotificationManager.shared
    @Environment(\.scenePhase) private var scenePhase

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
                .environmentObject(notificationManager)
                .preferredColorScheme(.dark)
                // Single global foreground observer: silently import new Apple-Watch workouts
                // on every `.active`. Debounce + in-flight guard live in SyncCoordinator.
                // (LogView's local scenePhase observer is a separate concern — left as-is.)
                .onChange(of: scenePhase) { _, phase in
                    if phase == .active {
                        Task { await SyncCoordinator.shared.syncOnForeground() }
                    }
                }
        }
        .modelContainer(modelContainer)
    }
}
