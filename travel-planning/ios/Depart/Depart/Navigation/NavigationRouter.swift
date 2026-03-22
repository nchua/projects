import SwiftUI

/// Deep link destinations for push notification routing.
enum DeepLinkDestination: Hashable {
    case tripDetail(UUID)
    case addTrip
    case settings
}

/// Centralized navigation state for all tabs.
@Observable
final class NavigationRouter {
    var selectedTab: Tab = .home
    var homePath = NavigationPath()
    var calendarPath = NavigationPath()

    enum Tab: Int, CaseIterable {
        case home = 0
        case calendar
        case alerts
        case settings
    }

    func navigate(to destination: DeepLinkDestination) {
        switch destination {
        case .tripDetail:
            selectedTab = .home
            homePath.append(destination)
        case .addTrip:
            selectedTab = .home
            // Sheet presentation handled by HomeView via notification
            NotificationCenter.default.post(name: .showAddTrip, object: nil)
        case .settings:
            selectedTab = .settings
        }
    }

    func resetToRoot() {
        homePath = NavigationPath()
        calendarPath = NavigationPath()
    }
}

extension Notification.Name {
    static let showAddTrip = Notification.Name("com.depart.showAddTrip")
}
