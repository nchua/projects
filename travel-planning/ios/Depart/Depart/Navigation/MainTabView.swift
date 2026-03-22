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
                CalendarTabPlaceholder()
            }
            .tabItem {
                Label("Calendar", systemImage: "calendar")
            }
            .tag(NavigationRouter.Tab.calendar)

            // Settings Tab
            NavigationStack {
                SettingsTabPlaceholder()
            }
            .tabItem {
                Label("Settings", systemImage: "gearshape.fill")
            }
            .tag(NavigationRouter.Tab.settings)
        }
    }
}

// MARK: - Placeholder Views (replaced in Phase B+)

private struct HomeTabPlaceholder: View {
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "car.fill")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("Depart")
                .font(.largeTitle.bold())
            Text("No upcoming trips")
                .foregroundStyle(.secondary)
        }
        .navigationTitle("Home")
    }
}

private struct CalendarTabPlaceholder: View {
    var body: some View {
        Text("Calendar")
            .navigationTitle("Calendar")
    }
}

private struct SettingsTabPlaceholder: View {
    var body: some View {
        Text("Settings")
            .navigationTitle("Settings")
    }
}

private struct TripDetailPlaceholder: View {
    let tripId: UUID

    var body: some View {
        Text("Trip Detail: \(tripId.uuidString.prefix(8))")
            .navigationTitle("Trip Detail")
    }
}
