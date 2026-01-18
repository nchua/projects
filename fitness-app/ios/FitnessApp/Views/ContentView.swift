import SwiftUI
import UIKit

struct ContentView: View {
    @EnvironmentObject var authManager: AuthManager
    @State private var selectedTab = 0

    init() {
        // Configure ARISE tab bar appearance
        configureTabBarAppearance()
    }

    var body: some View {
        Group {
            if authManager.isAuthenticated {
                MainTabView(selectedTab: $selectedTab)
            } else {
                AuthView()
            }
        }
    }

    private func configureTabBarAppearance() {
        let appearance = UITabBarAppearance()
        appearance.configureWithOpaqueBackground()
        appearance.backgroundColor = UIColor(Color.voidDark)

        // Selected state
        appearance.stackedLayoutAppearance.selected.iconColor = UIColor(Color.systemPrimary)
        appearance.stackedLayoutAppearance.selected.titleTextAttributes = [
            .foregroundColor: UIColor(Color.systemPrimary),
            .font: UIFont.systemFont(ofSize: 10, weight: .semibold)
        ]

        // Normal state
        appearance.stackedLayoutAppearance.normal.iconColor = UIColor(Color.textMuted)
        appearance.stackedLayoutAppearance.normal.titleTextAttributes = [
            .foregroundColor: UIColor(Color.textMuted),
            .font: UIFont.systemFont(ofSize: 10, weight: .medium)
        ]

        // Apply to all tab bar instances
        UITabBar.appearance().standardAppearance = appearance
        UITabBar.appearance().scrollEdgeAppearance = appearance
    }
}

struct MainTabView: View {
    @Binding var selectedTab: Int

    var body: some View {
        TabView(selection: $selectedTab) {
            HomeView()
                .tabItem {
                    Label("Status", systemImage: "shield.fill")
                }
                .tag(0)

            QuestsView()
                .tabItem {
                    Label("Quests", systemImage: "scroll.fill")
                }
                .tag(1)

            DungeonsView()
                .tabItem {
                    Label("Dungeons", systemImage: "door.left.hand.open")
                }
                .tag(2)

            FriendsView()
                .tabItem {
                    Label("Friends", systemImage: "person.2.fill")
                }
                .tag(3)

            StatsView()
                .tabItem {
                    Label("Stats", systemImage: "chart.bar.fill")
                }
                .tag(4)
        }
        .tint(Color.systemPrimary)
    }
}

struct AuthView: View {
    @EnvironmentObject var authManager: AuthManager
    @State private var isLogin = true
    @State private var email = ""
    @State private var password = ""
    @State private var confirmPassword = ""
    @State private var showPassword = false
    @State private var showConfirmPassword = false
    @State private var showTitle = false
    @State private var showSubtitle = false

    var body: some View {
        NavigationStack {
            ZStack {
                // ARISE void background
                VoidBackground(showGrid: true, glowIntensity: 0.05)

                VStack(spacing: 32) {
                    Spacer()

                    // ARISE Title with animation
                    VStack(spacing: 16) {
                        // System notification tag
                        Text("[ SYSTEM ]")
                            .font(.ariseMono(size: 12, weight: .medium))
                            .foregroundColor(.systemPrimary)
                            .tracking(2)
                            .opacity(showTitle ? 1 : 0)

                        // ARISE title with glow
                        Text("ARISE")
                            .font(.ariseDisplay(size: 48, weight: .bold))
                            .foregroundColor(.textPrimary)
                            .tracking(8)
                            .shadow(color: .systemPrimaryGlow, radius: 20, x: 0, y: 0)
                            .shadow(color: .systemPrimaryGlow, radius: 40, x: 0, y: 0)
                            .scaleEffect(showTitle ? 1 : 0.8)
                            .opacity(showTitle ? 1 : 0)

                        // Subtitle
                        Text("Become the Hunter")
                            .font(.ariseHeader(size: 16, weight: .medium))
                            .foregroundColor(.textSecondary)
                            .tracking(3)
                            .textCase(.uppercase)
                            .opacity(showSubtitle ? 1 : 0)
                    }
                    .padding(.bottom, 20)
                    .onAppear {
                        withAnimation(.easeOut(duration: 0.8).delay(0.3)) {
                            showTitle = true
                        }
                        withAnimation(.easeOut(duration: 0.5).delay(0.8)) {
                            showSubtitle = true
                        }
                    }

                    // Form
                    VStack(spacing: 16) {
                        // Email field
                        VStack(alignment: .leading, spacing: 8) {
                            Text("HUNTER ID")
                                .font(.ariseMono(size: 11, weight: .semibold))
                                .foregroundColor(.textMuted)
                                .tracking(1)

                            TextField("you@example.com", text: $email)
                                .textFieldStyle(AriseTextFieldStyle())
                                .textInputAutocapitalization(.never)
                                .keyboardType(.emailAddress)
                        }

                        // Password field
                        VStack(alignment: .leading, spacing: 8) {
                            Text("ACCESS CODE")
                                .font(.ariseMono(size: 11, weight: .semibold))
                                .foregroundColor(.textMuted)
                                .tracking(1)

                            HStack(spacing: 0) {
                                Group {
                                    if showPassword {
                                        TextField("Enter access code", text: $password)
                                    } else {
                                        SecureField("Enter access code", text: $password)
                                    }
                                }
                                .textInputAutocapitalization(.never)
                                .font(.ariseMono(size: 15))

                                Button {
                                    showPassword.toggle()
                                } label: {
                                    Image(systemName: showPassword ? "eye.slash.fill" : "eye.fill")
                                        .foregroundColor(.textMuted)
                                        .frame(width: 44, height: 44)
                                }
                            }
                            .padding(.leading, 16)
                            .background(Color.voidLight)
                            .cornerRadius(4)
                            .overlay(
                                RoundedRectangle(cornerRadius: 4)
                                    .stroke(Color.ariseBorder, lineWidth: 1)
                            )
                        }

                        if !isLogin {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("CONFIRM CODE")
                                    .font(.ariseMono(size: 11, weight: .semibold))
                                    .foregroundColor(.textMuted)
                                    .tracking(1)

                                HStack(spacing: 0) {
                                    Group {
                                        if showConfirmPassword {
                                            TextField("Confirm access code", text: $confirmPassword)
                                        } else {
                                            SecureField("Confirm access code", text: $confirmPassword)
                                        }
                                    }
                                    .textInputAutocapitalization(.never)
                                    .font(.ariseMono(size: 15))

                                    Button {
                                        showConfirmPassword.toggle()
                                    } label: {
                                        Image(systemName: showConfirmPassword ? "eye.slash.fill" : "eye.fill")
                                            .foregroundColor(.textMuted)
                                            .frame(width: 44, height: 44)
                                    }
                                }
                                .padding(.leading, 16)
                                .background(Color.voidLight)
                                .cornerRadius(4)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 4)
                                        .stroke(Color.ariseBorder, lineWidth: 1)
                                )
                            }
                        }
                    }
                    .padding(.horizontal, 24)

                    // Error message
                    if let error = authManager.error {
                        HStack(spacing: 8) {
                            Image(systemName: "exclamationmark.triangle.fill")
                            Text(error)
                        }
                        .font(.ariseMono(size: 13, weight: .medium))
                        .foregroundColor(.warningRed)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                        .background(Color.warningRed.opacity(0.1))
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.warningRed.opacity(0.3), lineWidth: 1)
                        )
                        .padding(.horizontal, 24)
                    }

                    // Action button - ARISE style
                    Button {
                        // Dismiss keyboard first
                        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)

                        // Haptic feedback on press
                        let impactFeedback = UIImpactFeedbackGenerator(style: .medium)
                        impactFeedback.impactOccurred()

                        Task {
                            if isLogin {
                                await authManager.login(email: email, password: password)
                            } else {
                                if password == confirmPassword {
                                    await authManager.register(email: email, password: password)
                                } else {
                                    authManager.error = "Codes don't match"
                                }
                            }
                        }
                    } label: {
                        HStack(spacing: 8) {
                            if authManager.isLoading {
                                SwiftUI.ProgressView()
                                    .tint(.voidBlack)
                                Text("AWAKENING...")
                                    .font(.ariseHeader(size: 16, weight: .semibold))
                                    .tracking(2)
                            } else {
                                Text(isLogin ? "ACCEPT" : "AWAKEN")
                                    .font(.ariseHeader(size: 16, weight: .semibold))
                                    .tracking(2)
                            }
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 54)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(AriseButtonStyle())
                    .shadow(color: Color.systemPrimaryGlow, radius: 20, x: 0, y: 0)
                    .padding(.horizontal, 24)
                    .disabled(authManager.isLoading)
                    .animation(.easeInOut(duration: 0.2), value: authManager.isLoading)

                    // Toggle login/register - ARISE style
                    Button {
                        withAnimation(.smoothSpring) {
                            isLogin.toggle()
                            authManager.error = nil
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Text(isLogin ? "New Hunter?" : "Already Awakened?")
                                .foregroundColor(.textSecondary)
                            Text(isLogin ? "Register" : "Sign In")
                                .foregroundColor(.systemPrimary)
                                .fontWeight(.semibold)
                        }
                        .font(.ariseMono(size: 14))
                    }

                    Spacer()
                    Spacer()
                }
            }
            .background {
                // Tap background to dismiss keyboard (won't interfere with buttons)
                Color.clear
                    .contentShape(Rectangle())
                    .onTapGesture {
                        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                    }
            }
        }
    }
}

// ARISE button style with press feedback
struct AriseButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(
                Group {
                    if configuration.isPressed {
                        Color.systemPrimary.opacity(0.8)
                    } else if !isEnabled {
                        Color.systemPrimary.opacity(0.5)
                    } else {
                        Color.systemPrimary
                    }
                }
            )
            .foregroundColor(.voidBlack)
            .overlay(
                Rectangle()
                    .stroke(Color.systemPrimary, lineWidth: 2)
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .animation(.easeInOut(duration: 0.1), value: configuration.isPressed)
    }
}

// ARISE-styled text field
struct AriseTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .padding(16)
            .background(Color.voidLight)
            .cornerRadius(4)
            .foregroundColor(.textPrimary)
            .font(.ariseMono(size: 15))
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
    }
}

// Legacy text field style (backward compatibility)
struct AppTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .padding(16)
            .background(Color.voidLight)
            .cornerRadius(4)
            .foregroundColor(.textPrimary)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
    }
}

#Preview {
    ContentView()
        .environmentObject(AuthManager.shared)
}
