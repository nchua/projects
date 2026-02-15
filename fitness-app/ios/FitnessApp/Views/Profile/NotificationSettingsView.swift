import SwiftUI

struct NotificationSettingsView: View {
    @StateObject private var viewModel = NotificationSettingsViewModel()

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                // Master toggle
                masterToggleCard

                // System notification banner
                if !viewModel.systemNotificationsEnabled {
                    systemDisabledBanner
                }

                // Social section
                notificationSection(
                    title: "Social",
                    accent: .systemPrimary,
                    types: NotificationSettingsViewModel.socialTypes
                )

                // Progression section
                notificationSection(
                    title: "Progression",
                    accent: .xpGold,
                    types: NotificationSettingsViewModel.progressionTypes
                )

                // Missions & Dungeons section
                notificationSection(
                    title: "Missions & Dungeons",
                    accent: .successGreen,
                    types: NotificationSettingsViewModel.missionTypes
                )
            }
            .padding(.bottom, 32)
        }
        .background(Color.voidBlack)
        .navigationTitle("Notifications")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await viewModel.loadPreferences()
        }
    }

    // MARK: - Master Toggle

    private var masterToggleCard: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color.systemPrimary.opacity(0.1))
                    .frame(width: 40, height: 40)

                Image(systemName: "bell.fill")
                    .font(.system(size: 18))
                    .foregroundColor(.systemPrimary)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text("All Notifications")
                    .font(.ariseHeader(size: 16, weight: .semibold))
                    .foregroundColor(.textPrimary)

                Text(viewModel.allEnabled ? "ALL ENABLED" : "SOME DISABLED")
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(0.5)
            }

            Spacer()

            Toggle("", isOn: Binding(
                get: { viewModel.allEnabled },
                set: { _ in viewModel.toggleAll() }
            ))
            .tint(.systemPrimary)
        }
        .padding(16)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .padding(.horizontal)
    }

    // MARK: - System Disabled Banner

    private var systemDisabledBanner: some View {
        HStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 20))
                .foregroundColor(.xpGold)

            VStack(alignment: .leading, spacing: 2) {
                Text("System Notifications Disabled")
                    .font(.ariseHeader(size: 13, weight: .semibold))
                    .foregroundColor(.xpGold)

                Text("Enable notifications in iOS Settings to receive alerts.")
                    .font(.ariseBody(size: 11))
                    .foregroundColor(.textSecondary)
            }

            Spacer()

            Button {
                if let url = URL(string: UIApplication.openSettingsURLString) {
                    UIApplication.shared.open(url)
                }
            } label: {
                Text("OPEN")
                    .font(.ariseMono(size: 10, weight: .bold))
                    .foregroundColor(.xpGold)
                    .tracking(1)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Color.xpGold.opacity(0.15))
                    .overlay(
                        RoundedRectangle(cornerRadius: 2)
                            .stroke(Color.xpGold.opacity(0.3), lineWidth: 1)
                    )
            }
        }
        .padding(14)
        .background(Color.xpGold.opacity(0.06))
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.xpGold.opacity(0.2), lineWidth: 1)
        )
        .padding(.horizontal)
    }

    // MARK: - Section Builder

    private func notificationSection(
        title: String,
        accent: Color,
        types: [(String, String, String)]
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            AriseSectionHeader(title: title)
                .padding(.horizontal)

            VStack(spacing: 0) {
                ForEach(Array(types.enumerated()), id: \.element.0) { index, item in
                    let (type, label, icon) = item

                    HStack(spacing: 12) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 4)
                                .fill(accent.opacity(0.1))
                                .frame(width: 36, height: 36)

                            Image(systemName: icon)
                                .font(.system(size: 14))
                                .foregroundColor(accent)
                        }

                        Text(label)
                            .font(.ariseHeader(size: 14, weight: .medium))
                            .foregroundColor(.textPrimary)

                        Spacer()

                        Toggle("", isOn: Binding(
                            get: { viewModel.preferences[type] ?? true },
                            set: { _ in viewModel.togglePreference(type: type) }
                        ))
                        .tint(.systemPrimary)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)

                    if index < types.count - 1 {
                        AriseDivider()
                    }
                }
            }
            .background(Color.voidMedium)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
            .padding(.horizontal)
        }
    }
}
