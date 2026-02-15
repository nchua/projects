import SwiftUI
import UIKit

struct ProfileView: View {
    @StateObject private var viewModel = ProfileViewModel()
    @EnvironmentObject var authManager: AuthManager
    @Environment(\.dismiss) private var dismiss
    @State private var showLogoutConfirmation = false
    @State private var showDeleteAccountConfirmation = false
    @State private var showDeletePasswordEntry = false
    @State private var deletePassword = ""
    @State private var deleteError: String?
    @State private var isDeleting = false
    @State private var showAllAchievements = false
    @State private var showImagePicker = false
    @State private var showUsernameSetup = false
    @State private var profileImage: UIImage?
    @State private var selectedAchievement: AchievementResponse?

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                // Close button overlay
                VStack {
                    HStack {
                        Spacer()
                        Button {
                            dismiss()
                        } label: {
                            Image(systemName: "xmark")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundColor(.textSecondary)
                                .frame(width: 32, height: 32)
                                .background(Color.voidMedium)
                                .cornerRadius(4)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 4)
                                        .stroke(Color.ariseBorder, lineWidth: 1)
                                )
                        }
                        .padding(.trailing, 16)
                        .padding(.top, 16)
                    }
                    Spacer()
                }
                .zIndex(100)

                if viewModel.isLoading {
                    VStack(spacing: 16) {
                        SwiftUI.ProgressView()
                            .tint(.systemPrimary)
                        Text("LOADING...")
                            .font(.ariseMono(size: 12, weight: .medium))
                            .foregroundColor(.textMuted)
                            .tracking(2)
                    }
                } else {
                    ScrollView {
                        VStack(spacing: 24) {
                            // Hunter Profile Header
                            HunterProfileHeader(
                                email: viewModel.profile?.email ?? "",
                                username: viewModel.profile?.username,
                                level: viewModel.hunterLevel,
                                rank: viewModel.hunterRank,
                                profileImage: profileImage,
                                onEditPhoto: { showImagePicker = true }
                            )

                            // Hunter Stats
                            HunterStatsPanel(
                                totalWorkouts: viewModel.totalWorkouts,
                                currentStreak: viewModel.currentStreak,
                                totalPRs: viewModel.totalPRs
                            )

                            // Achievements
                            HunterAchievementsSection(
                                achievements: viewModel.featuredAchievements,
                                onViewAll: { showAllAchievements = true },
                                onTapAchievement: { achievement in
                                    selectedAchievement = achievement
                                }
                            )

                            // Vessel Section (Bodyweight)
                            VesselSection(viewModel: viewModel)

                            // Hunter Identity (Username)
                            HunterIdentitySection(
                                username: viewModel.profile?.username,
                                onSetUsername: { showUsernameSetup = true }
                            )

                            // Hunter Attributes
                            HunterAttributesSection(viewModel: viewModel)

                            // System Settings
                            SystemSettingsSection(viewModel: viewModel)

                            // Save Button - ARISE style
                            Button {
                                let impactFeedback = UIImpactFeedbackGenerator(style: .medium)
                                impactFeedback.impactOccurred()

                                Task {
                                    await viewModel.saveProfile()
                                    if viewModel.error == nil {
                                        let successFeedback = UINotificationFeedbackGenerator()
                                        successFeedback.notificationOccurred(.success)
                                    }
                                }
                            } label: {
                                HStack(spacing: 8) {
                                    if viewModel.isSaving {
                                        SwiftUI.ProgressView()
                                            .tint(.voidBlack)
                                        Text("SAVING...")
                                            .font(.ariseHeader(size: 14, weight: .semibold))
                                            .tracking(2)
                                    } else {
                                        Image(systemName: "checkmark.shield.fill")
                                            .font(.system(size: 14))
                                        Text("SAVE CHANGES")
                                            .font(.ariseHeader(size: 14, weight: .semibold))
                                            .tracking(2)
                                    }
                                }
                            }
                            .frame(maxWidth: .infinity)
                            .frame(height: 54)
                            .background(viewModel.isSaving ? Color.systemPrimary.opacity(0.7) : Color.systemPrimary)
                            .foregroundColor(.voidBlack)
                            .overlay(
                                Rectangle()
                                    .stroke(Color.systemPrimary, lineWidth: 2)
                            )
                            .shadow(color: .systemPrimaryGlow, radius: 15, x: 0, y: 0)
                            .padding(.horizontal)
                            .disabled(viewModel.isSaving)
                            .animation(.easeInOut(duration: 0.2), value: viewModel.isSaving)

                            // Logout Button
                            Button {
                                showLogoutConfirmation = true
                            } label: {
                                HStack(spacing: 6) {
                                    Image(systemName: "rectangle.portrait.and.arrow.right")
                                        .font(.system(size: 12))
                                    Text("DISCONNECT")
                                        .font(.ariseMono(size: 12, weight: .semibold))
                                        .tracking(1)
                                }
                                .foregroundColor(.warningRed)
                            }
                            .padding(.top, 8)

                            // Delete Account Button
                            Button {
                                showDeleteAccountConfirmation = true
                            } label: {
                                HStack(spacing: 6) {
                                    Image(systemName: "trash.fill")
                                        .font(.system(size: 12))
                                    Text("DELETE ACCOUNT")
                                        .font(.ariseMono(size: 12, weight: .semibold))
                                        .tracking(1)
                                }
                                .foregroundColor(.warningRed.opacity(0.7))
                            }
                            .padding(.top, 4)

                            Spacer(minLength: 100)
                        }
                        .padding(.vertical)
                    }
                }
            }
            .navigationBarHidden(true)
            .onTapGesture {
                UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
            }
            .refreshable {
                await viewModel.loadProfile()
            }
            .alert("System Error", isPresented: .constant(viewModel.error != nil)) {
                Button("DISMISS", role: .cancel) {
                    viewModel.error = nil
                }
            } message: {
                Text(viewModel.error ?? "")
            }
            .alert("Data Saved", isPresented: .constant(viewModel.successMessage != nil)) {
                Button("ACCEPT", role: .cancel) {
                    viewModel.successMessage = nil
                }
            } message: {
                Text(viewModel.successMessage ?? "")
            }
            .alert("Disconnect from System?", isPresented: $showLogoutConfirmation) {
                Button("Cancel", role: .cancel) {}
                Button("Disconnect", role: .destructive) {
                    authManager.logout()
                }
            } message: {
                Text("Warning: You will need to re-authenticate to access the System.")
            }
            .alert("Delete Account?", isPresented: $showDeleteAccountConfirmation) {
                Button("Cancel", role: .cancel) {}
                Button("Delete Account", role: .destructive) {
                    showDeletePasswordEntry = true
                }
            } message: {
                Text("Your account will be permanently deleted after 30 days. This action cannot be undone.")
            }
            .alert("Confirm Password", isPresented: $showDeletePasswordEntry) {
                SecureField("Password", text: $deletePassword)
                Button("Cancel", role: .cancel) {
                    deletePassword = ""
                }
                Button("Delete", role: .destructive) {
                    guard !deletePassword.isEmpty, !isDeleting else { return }
                    let pw = deletePassword
                    deletePassword = ""
                    Task {
                        isDeleting = true
                        deleteError = nil
                        do {
                            try await APIClient.shared.deleteAccount(password: pw)
                            authManager.logout()
                        } catch {
                            deleteError = error.localizedDescription
                        }
                        isDeleting = false
                    }
                }
            } message: {
                Text("Enter your password to confirm account deletion.")
            }
            .alert("Deletion Failed", isPresented: .constant(deleteError != nil)) {
                Button("OK", role: .cancel) {
                    deleteError = nil
                }
            } message: {
                Text(deleteError ?? "")
            }
            .sheet(isPresented: $viewModel.showBodyweightEntry) {
                VesselEntrySheet(viewModel: viewModel)
            }
            .sheet(isPresented: $showAllAchievements) {
                AchievementsListView(achievements: viewModel.allAchievements)
            }
            .sheet(isPresented: $showImagePicker) {
                ImagePicker(image: $profileImage)
            }
            .sheet(isPresented: $showUsernameSetup) {
                UsernameSetupSheet {
                    // Refresh profile after username is set
                    Task {
                        await viewModel.loadProfile()
                    }
                }
            }
            .sheet(item: $selectedAchievement) { achievement in
                AchievementDetailSheet(achievement: achievement)
            }
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") {
                        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                    }
                    .font(.ariseMono(size: 14, weight: .semibold))
                    .foregroundColor(.systemPrimary)
                }
            }
        }
        .task {
            await viewModel.loadProfile()
        }
    }
}

// MARK: - Hunter Profile Header

struct HunterProfileHeader: View {
    let email: String
    var username: String? = nil
    let level: Int
    let rank: HunterRank
    var profileImage: UIImage? = nil
    var onEditPhoto: (() -> Void)? = nil
    @State private var showContent = false

    var hunterName: String {
        // Prefer username, fallback to email prefix
        if let username = username, !username.isEmpty {
            return username
        }
        return email.components(separatedBy: "@").first?.capitalized ?? "Hunter"
    }

    var displayUsername: String? {
        // Only show @username if username is set
        if let username = username, !username.isEmpty {
            return "@\(username)"
        }
        return nil
    }

    var initials: String {
        // Prefer username initials if available
        if let username = username, !username.isEmpty, username.count >= 2 {
            return String(username.prefix(2)).uppercased()
        }
        let components = email.components(separatedBy: "@").first?.components(separatedBy: ".") ?? []
        if components.count >= 2 {
            return String(components[0].prefix(1) + components[1].prefix(1)).uppercased()
        } else if let first = components.first, first.count >= 2 {
            return String(first.prefix(2)).uppercased()
        }
        return "NC"
    }

    var body: some View {
        VStack(spacing: 20) {
            // System tag
            Text("[ HUNTER PROFILE ]")
                .font(.ariseMono(size: 11, weight: .medium))
                .foregroundColor(.systemPrimary)
                .tracking(2)
                .opacity(showContent ? 1 : 0)

            // Hunter Avatar with Rank
            HStack(spacing: 20) {
                ZStack(alignment: .bottomTrailing) {
                    if let image = profileImage {
                        Image(uiImage: image)
                            .resizable()
                            .scaledToFill()
                            .frame(width: 80, height: 80)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(rank.color, lineWidth: 3)
                            )
                    } else {
                        HunterAvatarView(initial: initials, rank: rank, size: 80)
                    }

                    Button {
                        onEditPhoto?()
                    } label: {
                        ZStack {
                            Circle()
                                .fill(Color.voidDark)
                                .frame(width: 28, height: 28)

                            Image(systemName: "pencil.circle.fill")
                                .font(.system(size: 24))
                                .foregroundColor(.systemPrimary)
                        }
                    }
                    .offset(x: 4, y: 4)
                }
                .opacity(showContent ? 1 : 0)
                .scaleEffect(showContent ? 1 : 0.9)

                VStack(alignment: .leading, spacing: 8) {
                    Text(hunterName)
                        .font(.ariseHeader(size: 28, weight: .bold))
                        .foregroundColor(.textPrimary)

                    Text("\"\(rank.title)\"")
                        .font(.ariseMono(size: 13))
                        .foregroundColor(.textMuted)
                        .italic()

                    // Rank + Level badge
                    HStack(spacing: 8) {
                        RankBadgeView(rank: rank, size: .small)

                        HStack(spacing: 4) {
                            Text("LV")
                                .font(.ariseMono(size: 10, weight: .medium))
                                .foregroundColor(.textMuted)
                            Text("\(level)")
                                .font(.ariseDisplay(size: 16, weight: .bold))
                                .foregroundColor(.systemPrimary)
                        }
                    }
                }
                .opacity(showContent ? 1 : 0)

                Spacer()
            }
            .padding(.horizontal, 24)

            // Show @username if set, otherwise email
            if let displayUsername = displayUsername {
                Text(displayUsername)
                    .font(.ariseMono(size: 14, weight: .medium))
                    .foregroundColor(.systemPrimary)
                    .opacity(showContent ? 1 : 0)
            } else {
                Text(email)
                    .font(.ariseMono(size: 12))
                    .foregroundColor(.textSecondary)
                    .opacity(showContent ? 1 : 0)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .background(
            LinearGradient(
                colors: [Color.voidMedium, Color.voidDark],
                startPoint: .top,
                endPoint: .bottom
            )
        )
        .overlay(
            Rectangle()
                .fill(Color.systemPrimary.opacity(0.2))
                .frame(height: 1),
            alignment: .bottom
        )
        .onAppear {
            withAnimation(.easeOut(duration: 0.5).delay(0.2)) {
                showContent = true
            }
        }
    }
}

// MARK: - Hunter Stats Panel

struct HunterStatsPanel: View {
    let totalWorkouts: Int
    let currentStreak: Int
    let totalPRs: Int

    var body: some View {
        HStack(spacing: 0) {
            HunterStatItem(value: "\(totalWorkouts)", label: "Quests", color: .systemPrimary)

            Rectangle()
                .fill(Color.ariseBorder)
                .frame(width: 1)
                .padding(.vertical, 12)

            HunterStatItem(value: "\(currentStreak)", label: "Streak", color: .gold)

            Rectangle()
                .fill(Color.ariseBorder)
                .frame(width: 1)
                .padding(.vertical, 12)

            HunterStatItem(value: "\(totalPRs)", label: "Records", color: .successGreen)
        }
        .padding(.vertical, 20)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .padding(.horizontal)
        .offset(y: -12)
    }
}

struct HunterStatItem: View {
    let value: String
    let label: String
    let color: Color

    var body: some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.ariseDisplay(size: 24, weight: .bold))
                .foregroundColor(color)
                .shadow(color: color.opacity(0.4), radius: 6, x: 0, y: 0)

            Text(label.uppercased())
                .font(.ariseMono(size: 9, weight: .semibold))
                .foregroundColor(.textMuted)
                .tracking(1)
        }
        .frame(maxWidth: .infinity)
    }
}

// MARK: - Hunter Achievements

struct HunterAchievementsSection: View {
    let achievements: [AchievementResponse]
    var onViewAll: (() -> Void)? = nil
    var onTapAchievement: ((AchievementResponse) -> Void)? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                AriseSectionHeader(title: "Achievements")

                Spacer()

                Button {
                    onViewAll?()
                } label: {
                    Text("VIEW ALL")
                        .font(.ariseMono(size: 11, weight: .semibold))
                        .foregroundColor(.systemPrimary)
                        .tracking(1)
                }
            }
            .padding(.horizontal)

            if achievements.isEmpty {
                // Empty state
                HStack {
                    Spacer()
                    VStack(spacing: 8) {
                        Image(systemName: "trophy")
                            .font(.system(size: 32))
                            .foregroundColor(.textMuted)
                        Text("Complete quests to earn achievements")
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.textSecondary)
                    }
                    .padding(.vertical, 24)
                    Spacer()
                }
                .padding(.horizontal)
            } else {
                LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 4), spacing: 12) {
                    ForEach(Array(achievements.enumerated()), id: \.element.id) { index, achievement in
                        Button {
                            onTapAchievement?(achievement)
                        } label: {
                            HunterAchievementBadge(achievement: achievement)
                        }
                        .buttonStyle(.plain)
                        .fadeIn(delay: Double(index) * 0.05)
                    }
                }
                .padding(.horizontal)
            }
        }
    }
}

struct HunterAchievementBadge: View {
    let achievement: AchievementResponse

    var rarityColor: Color {
        switch achievement.rarity {
        case "legendary": return .gold
        case "epic": return .purple
        case "rare": return .systemPrimary
        default: return .textSecondary
        }
    }

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: achievement.icon)
                .font(.system(size: 24))
                .foregroundColor(achievement.unlocked ? rarityColor : .textMuted)
                .opacity(achievement.unlocked ? 1 : 0.3)

            Text(achievement.name.prefix(8).uppercased())
                .font(.ariseMono(size: 8, weight: .semibold))
                .foregroundColor(achievement.unlocked ? .textSecondary : .textMuted)
                .tracking(0.5)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
        .aspectRatio(1, contentMode: .fit)
        .padding(8)
        .background(
            achievement.unlocked
                ? rarityColor.opacity(0.1)
                : Color.voidLight
        )
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(achievement.unlocked ? rarityColor.opacity(0.3) : Color.ariseBorder, lineWidth: 1)
        )
        .opacity(achievement.unlocked ? 1 : 0.5)
    }
}

// MARK: - Vessel Section (Bodyweight)

struct VesselSection: View {
    @ObservedObject var viewModel: ProfileViewModel
    @State private var showHistory = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                AriseSectionHeader(title: "Vessel Status")

                Spacer()

                Button {
                    viewModel.showBodyweightEntry = true
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "plus")
                            .font(.system(size: 10, weight: .bold))
                        Text("LOG")
                            .font(.ariseMono(size: 11, weight: .semibold))
                            .tracking(1)
                    }
                    .foregroundColor(.systemPrimary)
                }
            }
            .padding(.horizontal)

            if let history = viewModel.bodyweightHistory,
               let latest = history.entries.first {
                Button {
                    showHistory = true
                } label: {
                    HStack(spacing: 0) {
                        // Left indicator
                        Rectangle()
                            .fill(Color.gold)
                            .frame(width: 4)

                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("VESSEL MASS")
                                    .font(.ariseMono(size: 10, weight: .medium))
                                    .foregroundColor(.textMuted)
                                    .tracking(1)

                                HStack(alignment: .lastTextBaseline, spacing: 6) {
                                    Text(latest.weightDisplay.formattedWeight)
                                        .font(.ariseDisplay(size: 28, weight: .bold))
                                        .foregroundColor(.textPrimary)

                                    Text(latest.weightUnit)
                                        .font(.ariseMono(size: 12))
                                        .foregroundColor(.textMuted)
                                }
                            }

                            Spacer()

                            if let avg = history.rollingAverage7day {
                                VStack(alignment: .trailing, spacing: 4) {
                                    Text("7-DAY AVG")
                                        .font(.ariseMono(size: 9, weight: .medium))
                                        .foregroundColor(.textMuted)
                                        .tracking(0.5)

                                    HStack(alignment: .lastTextBaseline, spacing: 4) {
                                        Text(avg.formattedWeight)
                                            .font(.ariseDisplay(size: 18, weight: .bold))
                                            .foregroundColor(.gold)

                                        Text("lb")
                                            .font(.ariseMono(size: 10))
                                            .foregroundColor(.textMuted)
                                    }
                                }
                            }

                            Image(systemName: "chevron.right")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(.textMuted)
                                .padding(.leading, 12)
                        }
                        .padding(16)
                    }
                    .background(Color.voidMedium)
                    .cornerRadius(4)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.ariseBorder, lineWidth: 1)
                    )
                }
                .padding(.horizontal)
            } else {
                HStack(spacing: 12) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Color.voidLight)
                            .frame(width: 48, height: 48)

                        Image(systemName: "scalemass")
                            .font(.system(size: 20))
                            .foregroundColor(.textMuted)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        Text("No vessel data")
                            .font(.ariseHeader(size: 14, weight: .medium))
                            .foregroundColor(.textPrimary)

                        Text("Log your weight to track vessel status")
                            .font(.ariseMono(size: 11))
                            .foregroundColor(.textSecondary)
                    }

                    Spacer()
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
        }
        .sheet(isPresented: $showHistory) {
            VesselHistorySheet(viewModel: viewModel)
        }
    }
}

// MARK: - Vessel History Sheet

struct VesselHistorySheet: View {
    @ObservedObject var viewModel: ProfileViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var entryToDelete: BodyweightResponse?
    @State private var showDeleteConfirmation = false

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                if let history = viewModel.bodyweightHistory {
                    List {
                        // Stats Section
                        Section {
                            VStack(spacing: 12) {
                                HStack(spacing: 12) {
                                    VesselStatBox(
                                        title: "7-Day Avg",
                                        value: history.rollingAverage7day?.formattedWeight ?? "-",
                                        unit: "lb",
                                        color: .systemPrimary
                                    )
                                    VesselStatBox(
                                        title: "14-Day Avg",
                                        value: history.rollingAverage14day?.formattedWeight ?? "-",
                                        unit: "lb",
                                        color: .systemPrimary
                                    )
                                }
                                HStack(spacing: 12) {
                                    VesselStatBox(
                                        title: "Min",
                                        value: history.minWeight?.formattedWeight ?? "-",
                                        unit: "lb",
                                        color: .successGreen
                                    )
                                    VesselStatBox(
                                        title: "Max",
                                        value: history.maxWeight?.formattedWeight ?? "-",
                                        unit: "lb",
                                        color: .warningRed
                                    )
                                }
                            }
                            .listRowBackground(Color.clear)
                            .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                        }

                        // Entries Section
                        Section {
                            ForEach(history.entries) { entry in
                                HStack {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(entry.date.formattedDateString)
                                            .font(.ariseHeader(size: 14, weight: .medium))
                                            .foregroundColor(.textPrimary)

                                        Text(entry.source.uppercased())
                                            .font(.ariseMono(size: 10))
                                            .foregroundColor(.textMuted)
                                            .tracking(0.5)
                                    }

                                    Spacer()

                                    HStack(alignment: .lastTextBaseline, spacing: 4) {
                                        Text(entry.weightDisplay.formattedWeight)
                                            .font(.ariseDisplay(size: 18, weight: .bold))
                                            .foregroundColor(.textPrimary)

                                        Text(entry.weightUnit)
                                            .font(.ariseMono(size: 10))
                                            .foregroundColor(.textMuted)
                                    }
                                }
                                .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                    Button(role: .destructive) {
                                        entryToDelete = entry
                                        showDeleteConfirmation = true
                                    } label: {
                                        Label("Delete", systemImage: "trash")
                                    }
                                }
                            }
                            .listRowBackground(Color.voidMedium)
                            .listRowSeparatorTint(Color.ariseBorder)
                        } header: {
                            Text("HISTORY")
                                .font(.ariseMono(size: 11, weight: .semibold))
                                .foregroundColor(.textMuted)
                                .tracking(1)
                        }
                    }
                    .listStyle(.insetGrouped)
                    .scrollContentBackground(.hidden)
                } else {
                    Text("No vessel history")
                        .font(.ariseMono(size: 14))
                        .foregroundColor(.textSecondary)
                }
            }
            .navigationTitle("Vessel History")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.voidDark, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                    .font(.ariseMono(size: 14, weight: .medium))
                    .foregroundColor(.systemPrimary)
                }
            }
            .alert("Delete Entry?", isPresented: $showDeleteConfirmation) {
                Button("Cancel", role: .cancel) {
                    entryToDelete = nil
                }
                Button("Delete", role: .destructive) {
                    if let entry = entryToDelete {
                        Task {
                            await viewModel.deleteBodyweight(id: entry.id)
                        }
                    }
                    entryToDelete = nil
                }
            } message: {
                if let entry = entryToDelete {
                    Text("Delete the \(entry.weightDisplay.formattedWeight) lb entry from \(entry.date.formattedDateString)?")
                }
            }
        }
    }
}

struct VesselStatBox: View {
    let title: String
    let value: String
    let unit: String
    var color: Color = .textPrimary

    var body: some View {
        VStack(spacing: 4) {
            Text(title.uppercased())
                .font(.ariseMono(size: 9, weight: .semibold))
                .foregroundColor(.textMuted)
                .tracking(0.5)

            HStack(alignment: .lastTextBaseline, spacing: 4) {
                Text(value)
                    .font(.ariseDisplay(size: 20, weight: .bold))
                    .foregroundColor(color)
                Text(unit)
                    .font(.ariseMono(size: 10))
                    .foregroundColor(.textMuted)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }
}

// MARK: - Hunter Identity (Username)

struct HunterIdentitySection: View {
    let username: String?
    var onSetUsername: (() -> Void)? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            AriseSectionHeader(title: "Hunter Identity")
                .padding(.horizontal)

            VStack(spacing: 0) {
                AriseSettingsRow(
                    icon: "at",
                    iconColor: .systemPrimary,
                    title: "Username",
                    trailing: {
                        if let username = username, !username.isEmpty {
                            Button {
                                onSetUsername?()
                            } label: {
                                HStack(spacing: 6) {
                                    Text("@\(username)")
                                        .font(.ariseMono(size: 14, weight: .medium))
                                        .foregroundColor(.systemPrimary)

                                    Image(systemName: "pencil")
                                        .font(.system(size: 10, weight: .semibold))
                                        .foregroundColor(.textMuted)
                                }
                            }
                        } else {
                            Button {
                                onSetUsername?()
                            } label: {
                                HStack(spacing: 4) {
                                    Image(systemName: "plus.circle.fill")
                                        .font(.system(size: 12))
                                    Text("SET USERNAME")
                                        .font(.ariseMono(size: 11, weight: .semibold))
                                        .tracking(0.5)
                                }
                                .foregroundColor(.systemPrimary)
                            }
                        }
                    }
                )
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

// MARK: - Hunter Attributes (Personal Info)

struct HunterAttributesSection: View {
    @ObservedObject var viewModel: ProfileViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            AriseSectionHeader(title: "Hunter Attributes")
                .padding(.horizontal)

            VStack(spacing: 0) {
                AriseSettingsRow(
                    icon: "person.fill",
                    iconColor: .systemPrimary,
                    title: "Age",
                    trailing: {
                        TextField("--", text: $viewModel.age)
                            .keyboardType(.numberPad)
                            .multilineTextAlignment(.trailing)
                            .font(.ariseMono(size: 14, weight: .medium))
                            .foregroundColor(.textPrimary)
                            .frame(width: 60)
                    }
                )

                AriseDivider()

                AriseSettingsRow(
                    icon: "figure.stand",
                    iconColor: .gold,
                    title: "Sex",
                    trailing: {
                        Picker("Sex", selection: $viewModel.sex) {
                            Text("--").tag("")
                            Text("M").tag("M")
                            Text("F").tag("F")
                        }
                        .pickerStyle(.menu)
                        .tint(.textPrimary)
                    }
                )

                AriseDivider()

                AriseSettingsRow(
                    icon: "ruler",
                    iconColor: .successGreen,
                    title: "Height",
                    trailing: {
                        HStack(spacing: 6) {
                            TextField("0", text: $viewModel.heightFeet)
                                .keyboardType(.numberPad)
                                .multilineTextAlignment(.center)
                                .font(.ariseMono(size: 14, weight: .medium))
                                .foregroundColor(.textPrimary)
                                .frame(width: 44, height: 36)
                                .background(Color.voidLight.opacity(0.5))
                                .cornerRadius(6)
                                .contentShape(Rectangle())

                            Text("ft")
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textMuted)

                            TextField("0", text: $viewModel.heightInches)
                                .keyboardType(.numberPad)
                                .multilineTextAlignment(.center)
                                .font(.ariseMono(size: 14, weight: .medium))
                                .foregroundColor(.textPrimary)
                                .frame(width: 44, height: 36)
                                .background(Color.voidLight.opacity(0.5))
                                .cornerRadius(6)
                                .contentShape(Rectangle())

                            Text("in")
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textMuted)
                        }
                    }
                )

                AriseDivider()

                AriseSettingsRow(
                    icon: "star.fill",
                    iconColor: .rankA,
                    title: "Experience",
                    trailing: {
                        Picker("Experience", selection: $viewModel.trainingExperience) {
                            ForEach(viewModel.experienceOptions, id: \.self) { option in
                                Text(option.isEmpty ? "--" : option.uppercased())
                                    .tag(option)
                            }
                        }
                        .font(.ariseMono(size: 12, weight: .medium))
                        .pickerStyle(.menu)
                        .tint(.textPrimary)
                        .fixedSize(horizontal: true, vertical: false)
                    }
                )
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

// MARK: - System Settings

struct SystemSettingsSection: View {
    @ObservedObject var viewModel: ProfileViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            AriseSectionHeader(title: "System Settings")
                .padding(.horizontal)

            VStack(spacing: 0) {
                NavigationLink {
                    NotificationSettingsView()
                } label: {
                    AriseSettingsRow(
                        icon: "bell.fill",
                        iconColor: .gold,
                        title: "Notifications",
                        trailing: {
                            Image(systemName: "chevron.right")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(.textMuted)
                        }
                    )
                }

                AriseDivider()

                AriseSettingsRow(
                    icon: "scalemass.fill",
                    iconColor: .textSecondary,
                    title: "Weight Unit",
                    trailing: {
                        Picker("Unit", selection: $viewModel.preferredUnit) {
                            ForEach(viewModel.unitOptions, id: \.self) { option in
                                Text(option.uppercased())
                                    .tag(option)
                            }
                        }
                        .pickerStyle(.menu)
                        .tint(.textPrimary)
                    }
                )

                AriseDivider()

                AriseSettingsRow(
                    icon: "function",
                    iconColor: .systemPrimary,
                    title: "e1RM Formula",
                    trailing: {
                        Picker("Formula", selection: $viewModel.e1rmFormula) {
                            ForEach(viewModel.formulaOptions, id: \.self) { option in
                                Text(option.uppercased())
                                    .tag(option)
                            }
                        }
                        .pickerStyle(.menu)
                        .tint(.textPrimary)
                    }
                )

                AriseDivider()

                AriseSettingsRow(
                    icon: "heart.fill",
                    iconColor: .warningRed,
                    title: "Health Sync",
                    trailing: {
                        HStack(spacing: 6) {
                            Circle()
                                .fill(Color.successGreen)
                                .frame(width: 6, height: 6)
                            Text("CONNECTED")
                                .font(.ariseMono(size: 11, weight: .semibold))
                                .foregroundColor(.successGreen)
                                .tracking(0.5)
                        }
                    }
                )

                AriseDivider()

                Button {
                    if let url = URL(string: "https://backend-production-e316.up.railway.app/privacy") {
                        UIApplication.shared.open(url)
                    }
                } label: {
                    AriseSettingsRow(
                        icon: "doc.text.fill",
                        iconColor: .textSecondary,
                        title: "Privacy Policy",
                        trailing: {
                            Image(systemName: "arrow.up.right.square")
                                .font(.system(size: 12))
                                .foregroundColor(.textMuted)
                        }
                    )
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

// MARK: - Settings Row

struct AriseSettingsRow<Trailing: View>: View {
    let icon: String
    let iconColor: Color
    let title: String
    @ViewBuilder let trailing: () -> Trailing

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 4)
                    .fill(iconColor.opacity(0.1))
                    .frame(width: 36, height: 36)

                Image(systemName: icon)
                    .font(.system(size: 14))
                    .foregroundColor(iconColor)
            }

            Text(title)
                .font(.ariseHeader(size: 14, weight: .medium))
                .foregroundColor(.textPrimary)

            Spacer()

            trailing()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }
}

// MARK: - Vessel Entry Sheet (Bodyweight)

struct VesselEntrySheet: View {
    @ObservedObject var viewModel: ProfileViewModel
    @Environment(\.dismiss) private var dismiss
    @FocusState private var isWeightFieldFocused: Bool

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                VStack(spacing: 32) {
                    VStack(alignment: .leading, spacing: 16) {
                        Text("ENTER VESSEL MASS")
                            .font(.ariseMono(size: 11, weight: .semibold))
                            .foregroundColor(.textMuted)
                            .tracking(1)

                        HStack(alignment: .lastTextBaseline) {
                            TextField("0.0", text: $viewModel.newBodyweight)
                                .keyboardType(.decimalPad)
                                .font(.ariseDisplay(size: 56, weight: .bold))
                                .foregroundColor(.textPrimary)
                                .multilineTextAlignment(.center)
                                .focused($isWeightFieldFocused)

                            Text(viewModel.preferredUnit)
                                .font(.ariseMono(size: 20))
                                .foregroundColor(.textMuted)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 32)
                        .background(Color.voidMedium)
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.ariseBorder, lineWidth: 1)
                        )
                        .overlay(
                            Rectangle()
                                .fill(Color.systemPrimary.opacity(0.3))
                                .frame(height: 1),
                            alignment: .top
                        )
                    }
                    .padding(.horizontal)

                    Button {
                        isWeightFieldFocused = false

                        let impactFeedback = UIImpactFeedbackGenerator(style: .medium)
                        impactFeedback.impactOccurred()

                        Task {
                            await viewModel.logBodyweight()
                            if viewModel.error == nil {
                                let successFeedback = UINotificationFeedbackGenerator()
                                successFeedback.notificationOccurred(.success)
                            }
                        }
                    } label: {
                        HStack(spacing: 8) {
                            if viewModel.isSaving {
                                SwiftUI.ProgressView()
                                    .tint(.voidBlack)
                                Text("SAVING...")
                                    .font(.ariseHeader(size: 14, weight: .semibold))
                                    .tracking(2)
                            } else {
                                Image(systemName: "checkmark")
                                    .font(.system(size: 14, weight: .bold))
                                Text("LOG VESSEL DATA")
                                    .font(.ariseHeader(size: 14, weight: .semibold))
                                    .tracking(2)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 54)
                    .background(viewModel.isSaving ? Color.systemPrimary.opacity(0.7) : Color.systemPrimary)
                    .foregroundColor(.voidBlack)
                    .overlay(
                        Rectangle()
                            .stroke(Color.systemPrimary, lineWidth: 2)
                    )
                    .shadow(color: .systemPrimaryGlow, radius: 15, x: 0, y: 0)
                    .padding(.horizontal)
                    .disabled(viewModel.isSaving)
                    .animation(.easeInOut(duration: 0.2), value: viewModel.isSaving)

                    Spacer()
                }
                .padding(.vertical, 24)
            }
            .navigationTitle("Log Vessel Mass")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.voidDark, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        dismiss()
                    }
                    .font(.ariseMono(size: 14, weight: .medium))
                    .foregroundColor(.systemPrimary)
                }
                ToolbarItem(placement: .keyboard) {
                    HStack {
                        Spacer()
                        Button("Done") {
                            isWeightFieldFocused = false
                        }
                        .font(.ariseMono(size: 14, weight: .semibold))
                        .foregroundColor(.systemPrimary)
                    }
                }
            }
        }
    }
}

// MARK: - Legacy Aliases

typealias ProfileHeader = HunterProfileHeader
typealias ProfileStatsCard = HunterStatsPanel
typealias ProfileStatItem = HunterStatItem
typealias AchievementsSection = HunterAchievementsSection
typealias AchievementBadge = HunterAchievementBadge
typealias BodyweightSection = VesselSection
typealias BodyweightHistorySheet = VesselHistorySheet
typealias StatBox = VesselStatBox
typealias PersonalInfoSection = HunterAttributesSection
typealias SettingsSection = SystemSettingsSection
typealias SettingsRow = AriseSettingsRow
typealias BodyweightEntrySheet = VesselEntrySheet

#Preview {
    ProfileView()
        .environmentObject(AuthManager.shared)
}
