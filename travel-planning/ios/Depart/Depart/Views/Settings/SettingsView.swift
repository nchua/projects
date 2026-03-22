import SwiftUI

/// Full settings screen with all user preference sections.
struct SettingsView: View {
    @Environment(APIClient.self) private var apiClient
    @State private var viewModel = SettingsViewModel()

    var body: some View {
        List {
            // Saved Locations
            Section {
                ForEach(viewModel.savedLocations) { location in
                    NavigationLink {
                        SavedLocationEditView(
                            location: location,
                            onSave: { await viewModel.loadLocations() }
                        )
                    } label: {
                        HStack(spacing: 10) {
                            Text(location.icon ?? "📍")
                                .font(.title3)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(location.name)
                                    .font(.departBody)
                                Text(location.address)
                                    .font(.departCaption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                        }
                    }
                }
                .onDelete { indexSet in
                    Task {
                        for index in indexSet {
                            await viewModel.deleteLocation(viewModel.savedLocations[index])
                        }
                    }
                }

                NavigationLink {
                    SavedLocationEditView(
                        location: nil,
                        onSave: { await viewModel.loadLocations() }
                    )
                } label: {
                    Label("Add Location", systemImage: "plus.circle.fill")
                        .foregroundStyle(Color.departPrimary)
                }
            } header: {
                Text("Saved Locations")
            }

            // Default Buffer
            Section {
                StepperControlView(
                    "Default Buffer",
                    value: $viewModel.defaultBufferMinutes,
                    in: 0...60,
                    step: 5,
                    unit: "min"
                )
                .onChange(of: viewModel.defaultBufferMinutes) { _, _ in
                    viewModel.debounceSavePreferences()
                }
            } header: {
                Text("Buffer Time")
            } footer: {
                Text("Extra time added to all trips for parking, walking, etc.")
            }

            // Transport Preferences
            Section {
                Picker("Default Mode", selection: $viewModel.defaultTravelMode) {
                    ForEach(TravelMode.allCases, id: \.self) { mode in
                        Label(mode.rawValue.capitalized, systemImage: mode.icon)
                            .tag(mode)
                    }
                }
                .onChange(of: viewModel.defaultTravelMode) { _, _ in
                    viewModel.debounceSavePreferences()
                }
            } header: {
                Text("Transport")
            }

            // Notification Preferences
            Section {
                ToggleRowView(
                    icon: "bell.fill",
                    label: "Push Notifications",
                    description: "Departure reminders and traffic alerts",
                    isOn: $viewModel.pushEnabled
                )
                .onChange(of: viewModel.pushEnabled) { _, _ in
                    viewModel.debounceSavePreferences()
                }

                ToggleRowView(
                    icon: "iphone.radiowaves.left.and.right",
                    label: "Haptic Feedback",
                    isOn: $viewModel.hapticEnabled
                )
            } header: {
                Text("Notifications")
            }

            // Quiet Hours
            Section {
                ToggleRowView(
                    icon: "moon.fill",
                    label: "Quiet Hours",
                    description: "Silence non-critical alerts during these hours",
                    isOn: $viewModel.quietHoursEnabled
                )

                if viewModel.quietHoursEnabled {
                    DatePicker("Start", selection: $viewModel.quietHoursStart, displayedComponents: .hourAndMinute)
                    DatePicker("End", selection: $viewModel.quietHoursEnd, displayedComponents: .hourAndMinute)
                }
            } header: {
                Text("Quiet Hours")
            }

            // About
            Section {
                Link(destination: URL(string: "https://apps.apple.com/app/depart")!) {
                    FormRowView(icon: "star.fill", label: "Rate Depart", showChevron: true)
                }

                FormRowView(icon: "lock.shield.fill", label: "Privacy Policy", showChevron: true)

                FormRowView(icon: "envelope.fill", label: "Send Feedback", showChevron: true)
            } header: {
                Text("About")
            } footer: {
                Text("Depart v1.0.0")
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.top, 8)
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("Settings")
        .task {
            viewModel.configure(apiClient: apiClient)
            await viewModel.loadPreferences()
            await viewModel.loadLocations()
        }
    }
}
