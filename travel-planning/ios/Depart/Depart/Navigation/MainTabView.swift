import SwiftUI

struct MainTabView: View {
    @Bindable var router: NavigationRouter

    var body: some View {
        TabView(selection: $router.selectedTab) {
            // Home Tab
            NavigationStack(path: $router.homePath) {
                HomeView()
                    .navigationDestination(for: DeepLinkDestination.self) { destination in
                        switch destination {
                        case .tripDetail(let tripId):
                            TripDetailView(tripId: tripId)
                        default:
                            EmptyView()
                        }
                    }
            }
            .tabItem {
                Label("Home", systemImage: "house.fill")
            }
            .tag(NavigationRouter.Tab.home)

            // Calendar Tab
            NavigationStack(path: $router.calendarPath) {
                CalendarView()
            }
            .tabItem {
                Label("Calendar", systemImage: "calendar")
            }
            .tag(NavigationRouter.Tab.calendar)

            // Alerts Tab
            NavigationStack {
                AlertsView()
                    .navigationDestination(for: DeepLinkDestination.self) { destination in
                        switch destination {
                        case .tripDetail(let tripId):
                            TripDetailView(tripId: tripId)
                        default:
                            EmptyView()
                        }
                    }
            }
            .tabItem {
                Label("Alerts", systemImage: "bell.fill")
            }
            .tag(NavigationRouter.Tab.alerts)

            // Settings Tab
            NavigationStack {
                SettingsView()
            }
            .tabItem {
                Label("Settings", systemImage: "gearshape.fill")
            }
            .tag(NavigationRouter.Tab.settings)
        }
    }
}
