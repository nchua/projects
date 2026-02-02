import SwiftUI

struct ForgotPasswordView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var step: Step = .enterEmail
    @State private var email = ""
    @State private var code = ""
    @State private var newPassword = ""
    @State private var confirmPassword = ""
    @State private var showPassword = false
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var successMessage: String?

    enum Step {
        case enterEmail
        case enterCode
        case success
    }

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: true, glowIntensity: 0.03)

                ScrollView {
                    VStack(spacing: 32) {
                        // Header
                        headerView

                        // Content based on step
                        switch step {
                        case .enterEmail:
                            emailStepView
                        case .enterCode:
                            codeStepView
                        case .success:
                            successView
                        }
                    }
                    .padding(.horizontal, 24)
                    .padding(.top, 40)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    if step != .success {
                        Button {
                            dismiss()
                        } label: {
                            Image(systemName: "xmark")
                                .foregroundColor(.textSecondary)
                        }
                    }
                }
            }
        }
    }

    // MARK: - Header

    private var headerView: some View {
        VStack(spacing: 12) {
            Image(systemName: step == .success ? "checkmark.shield.fill" : "key.fill")
                .font(.system(size: 48))
                .foregroundColor(step == .success ? .systemPrimary : .textSecondary)
                .shadow(color: step == .success ? .systemPrimaryGlow : .clear, radius: 20)

            Text(headerTitle)
                .font(.ariseHeader(size: 24, weight: .semibold))
                .foregroundColor(.textPrimary)

            Text(headerSubtitle)
                .font(.ariseMono(size: 14))
                .foregroundColor(.textMuted)
                .multilineTextAlignment(.center)
        }
    }

    private var headerTitle: String {
        switch step {
        case .enterEmail: return "Reset Password"
        case .enterCode: return "Enter Code"
        case .success: return "Password Updated"
        }
    }

    private var headerSubtitle: String {
        switch step {
        case .enterEmail: return "Enter your email to receive a reset code"
        case .enterCode: return "Check your email for the 6-digit code"
        case .success: return "You can now sign in with your new password"
        }
    }

    // MARK: - Step 1: Enter Email

    private var emailStepView: some View {
        VStack(spacing: 24) {
            // Email field
            VStack(alignment: .leading, spacing: 8) {
                Text("EMAIL")
                    .font(.ariseMono(size: 11, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(1)

                TextField("you@example.com", text: $email)
                    .textFieldStyle(AriseTextFieldStyle())
                    .textInputAutocapitalization(.never)
                    .keyboardType(.emailAddress)
                    .autocorrectionDisabled()
            }

            // Error/Success message
            messageView

            // Submit button
            Button {
                Task { await requestCode() }
            } label: {
                HStack(spacing: 8) {
                    if isLoading {
                        SwiftUI.ProgressView()
                            .tint(.voidBlack)
                    }
                    Text(isLoading ? "SENDING..." : "SEND CODE")
                        .font(.ariseHeader(size: 16, weight: .semibold))
                        .tracking(2)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 54)
                .contentShape(Rectangle())
            }
            .buttonStyle(AriseButtonStyle())
            .disabled(isLoading || email.isEmpty)
        }
    }

    // MARK: - Step 2: Enter Code & New Password

    private var codeStepView: some View {
        VStack(spacing: 24) {
            // Code field
            VStack(alignment: .leading, spacing: 8) {
                Text("RESET CODE")
                    .font(.ariseMono(size: 11, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(1)

                TextField("000000", text: $code)
                    .textFieldStyle(AriseTextFieldStyle())
                    .keyboardType(.numberPad)
                    .font(.ariseMono(size: 24))
                    .multilineTextAlignment(.center)
                    .onChange(of: code) { _, newValue in
                        // Limit to 6 digits
                        code = String(newValue.prefix(6).filter { $0.isNumber })
                    }
            }

            // New password field
            VStack(alignment: .leading, spacing: 8) {
                Text("NEW PASSWORD")
                    .font(.ariseMono(size: 11, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(1)

                HStack(spacing: 0) {
                    Group {
                        if showPassword {
                            TextField("Enter new password", text: $newPassword)
                        } else {
                            SecureField("Enter new password", text: $newPassword)
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

                Text("Min 8 chars, 1 uppercase, 1 lowercase, 1 number")
                    .font(.ariseMono(size: 11))
                    .foregroundColor(.textMuted)
            }

            // Confirm password field
            VStack(alignment: .leading, spacing: 8) {
                Text("CONFIRM PASSWORD")
                    .font(.ariseMono(size: 11, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(1)

                SecureField("Confirm new password", text: $confirmPassword)
                    .textInputAutocapitalization(.never)
                    .font(.ariseMono(size: 15))
                    .padding(16)
                    .background(Color.voidLight)
                    .cornerRadius(4)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.ariseBorder, lineWidth: 1)
                    )
            }

            // Error message
            messageView

            // Submit button
            Button {
                Task { await verifyCode() }
            } label: {
                HStack(spacing: 8) {
                    if isLoading {
                        SwiftUI.ProgressView()
                            .tint(.voidBlack)
                    }
                    Text(isLoading ? "UPDATING..." : "RESET PASSWORD")
                        .font(.ariseHeader(size: 16, weight: .semibold))
                        .tracking(2)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 54)
                .contentShape(Rectangle())
            }
            .buttonStyle(AriseButtonStyle())
            .disabled(isLoading || code.count != 6 || newPassword.isEmpty || confirmPassword.isEmpty)

            // Resend code link
            Button {
                Task { await requestCode() }
            } label: {
                Text("Didn't receive a code? Resend")
                    .font(.ariseMono(size: 13))
                    .foregroundColor(.systemPrimary)
            }
            .disabled(isLoading)
        }
    }

    // MARK: - Step 3: Success

    private var successView: some View {
        VStack(spacing: 24) {
            Button {
                dismiss()
            } label: {
                Text("RETURN TO SIGN IN")
                    .font(.ariseHeader(size: 16, weight: .semibold))
                    .tracking(2)
                    .frame(maxWidth: .infinity)
                    .frame(height: 54)
                    .contentShape(Rectangle())
            }
            .buttonStyle(AriseButtonStyle())
        }
    }

    // MARK: - Message View

    @ViewBuilder
    private var messageView: some View {
        if let error = errorMessage {
            HStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle.fill")
                Text(error)
            }
            .font(.ariseMono(size: 13, weight: .medium))
            .foregroundColor(.warningRed)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity)
            .background(Color.warningRed.opacity(0.1))
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.warningRed.opacity(0.3), lineWidth: 1)
            )
        }

        if let success = successMessage {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill")
                Text(success)
            }
            .font(.ariseMono(size: 13, weight: .medium))
            .foregroundColor(.systemPrimary)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity)
            .background(Color.systemPrimary.opacity(0.1))
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.systemPrimary.opacity(0.3), lineWidth: 1)
            )
        }
    }

    // MARK: - Actions

    private func requestCode() async {
        guard !email.isEmpty else { return }

        isLoading = true
        errorMessage = nil
        successMessage = nil

        do {
            _ = try await APIClient.shared.requestPasswordReset(email: email)
            // Always move to code entry step (API always returns success for security)
            withAnimation(.smoothSpring) {
                step = .enterCode
                successMessage = "If an account exists, a code has been sent."
            }
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    private func verifyCode() async {
        // Validate passwords match
        guard newPassword == confirmPassword else {
            errorMessage = "Passwords don't match"
            return
        }

        // Validate password strength
        guard newPassword.count >= 8 else {
            errorMessage = "Password must be at least 8 characters"
            return
        }

        isLoading = true
        errorMessage = nil
        successMessage = nil

        do {
            _ = try await APIClient.shared.verifyPasswordReset(
                email: email,
                code: code,
                newPassword: newPassword
            )
            withAnimation(.smoothSpring) {
                step = .success
            }
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }
}

#Preview {
    ForgotPasswordView()
}
