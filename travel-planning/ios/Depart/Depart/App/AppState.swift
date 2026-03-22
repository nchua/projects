import Foundation
import Network
import SwiftUI

/// App-wide state: onboarding, network status, pending deep links.
@Observable
final class AppState {
    var isOnboarded: Bool {
        get { UserDefaults.standard.bool(forKey: "com.depart.isOnboarded") }
        set { UserDefaults.standard.set(newValue, forKey: "com.depart.isOnboarded") }
    }

    var isOffline = false
    var pendingDeepLink: DeepLinkDestination?

    private let monitor = NWPathMonitor()
    private let monitorQueue = DispatchQueue(label: "com.depart.network-monitor")

    func startNetworkMonitoring() {
        monitor.pathUpdateHandler = { [weak self] path in
            DispatchQueue.main.async {
                self?.isOffline = path.status != .satisfied
            }
        }
        monitor.start(queue: monitorQueue)
    }

    deinit {
        monitor.cancel()
    }
}
