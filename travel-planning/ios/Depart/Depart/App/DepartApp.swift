import SwiftData
import SwiftUI

@main
struct DepartApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    @State private var appState = AppState()
    @State private var authManager = AuthManager()
    @State private var apiClient = APIClient.shared
    @State private var router = NavigationRouter()

    private let persistence = PersistenceController.shared

    var body: some Scene {
        WindowGroup {
            Group {
                if appState.isOnboarded {
                    MainTabView(router: router)
                } else {
                    // TODO: OnboardingContainerView
                    // For now, auto-mark onboarded so we can test the main flow
                    MainTabView(router: router)
                        .onAppear {
                            appState.isOnboarded = true
                        }
                }
            }
            .environment(appState)
            .environment(authManager)
            .environment(apiClient)
            .environment(router)
            .modelContainer(persistence.container)
            .task {
                // Wire up dependencies (breaks circular init)
                apiClient.configure(authManager: authManager)
                authManager.configure(apiClient: apiClient)

                // Start services
                appState.startNetworkMonitoring()
                await authManager.restoreSession()

                // Schedule background ETA monitoring
                TripMonitor.shared.scheduleAppRefresh()
            }
            .onReceive(NotificationCenter.default.publisher(for: .handleDeepLink)) { notification in
                if let destination = notification.object as? DeepLinkDestination {
                    // Small delay to ensure NavigationStack is mounted
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                        router.navigate(to: destination)
                    }
                }
            }
            .onOpenURL { url in
                // Handle depart:// URL scheme deep links
                if let destination = DeepLinkHandler.destination(from: url) {
                    router.navigate(to: destination)
                }
            }
        }
    }
}
