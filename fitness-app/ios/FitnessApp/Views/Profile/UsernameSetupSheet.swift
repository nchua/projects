import SwiftUI

struct UsernameSetupSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var username: String = ""
    @State private var isChecking = false
    @State private var isSaving = false
    @State private var isAvailable: Bool? = nil
    @State private var error: String?
    @State private var checkTask: Task<Void, Never>?

    let onComplete: () -> Void

    var isValidFormat: Bool {
        let pattern = "^[a-z0-9][a-z0-9_]{1,18}[a-z0-9]$|^[a-z0-9]{3}$"
        return username.range(of: pattern, options: .regularExpression) != nil
    }

    var validationMessage: String? {
        let trimmed = username.trimmingCharacters(in: .whitespaces).lowercased()

        if trimmed.isEmpty {
            return nil
        }

        if trimmed.count < 3 {
            return "At least 3 characters"
        }

        if trimmed.count > 20 {
            return "Maximum 20 characters"
        }

        if trimmed.hasPrefix("_") || trimmed.hasSuffix("_") {
            return "Cannot start or end with underscore"
        }

        if !trimmed.allSatisfy({ $0.isLetter || $0.isNumber || $0 == "_" }) {
            return "Only letters, numbers, and underscores"
        }

        if trimmed.contains(where: { $0.isUppercase }) {
            return nil // Will be auto-lowercased
        }

        return nil
    }

    var canSave: Bool {
        isValidFormat && isAvailable == true && !isSaving && !isChecking
    }

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                VStack(spacing: 24) {
                    // Header
                    VStack(spacing: 8) {
                        Text("CHOOSE YOUR HUNTER NAME")
                            .font(.ariseMono(size: 11, weight: .semibold))
                            .foregroundColor(.textMuted)
                            .tracking(2)

                        Text("Your username is how other hunters will find you")
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.textSecondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding(.top, 16)

                    // Username input
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(spacing: 8) {
                            Text("@")
                                .font(.ariseDisplay(size: 28, weight: .bold))
                                .foregroundColor(.systemPrimary)

                            TextField("username", text: $username)
                                .font(.ariseDisplay(size: 28, weight: .bold))
                                .foregroundColor(.textPrimary)
                                .autocapitalization(.none)
                                .autocorrectionDisabled()
                                .textInputAutocapitalization(.never)
                                .onChange(of: username) { _, newValue in
                                    // Auto-lowercase
                                    let lowercased = newValue.lowercased()
                                    if lowercased != newValue {
                                        username = lowercased
                                    }
                                    checkAvailabilityDebounced()
                                }
                        }
                        .padding(.horizontal, 20)
                        .padding(.vertical, 16)
                        .background(Color.voidMedium)
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(strokeColor, lineWidth: 2)
                        )

                        // Status indicator
                        HStack(spacing: 8) {
                            if isChecking {
                                SwiftUI.ProgressView()
                                    .scaleEffect(0.8)
                                    .tint(.textMuted)
                                Text("Checking availability...")
                                    .font(.ariseMono(size: 11))
                                    .foregroundColor(.textMuted)
                            } else if let message = validationMessage {
                                Image(systemName: "exclamationmark.circle")
                                    .foregroundColor(.warningYellow)
                                Text(message)
                                    .font(.ariseMono(size: 11))
                                    .foregroundColor(.warningYellow)
                            } else if isValidFormat {
                                if isAvailable == true {
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundColor(.successGreen)
                                    Text("Username available")
                                        .font(.ariseMono(size: 11))
                                        .foregroundColor(.successGreen)
                                } else if isAvailable == false {
                                    Image(systemName: "xmark.circle.fill")
                                        .foregroundColor(.warningRed)
                                    Text("Username taken")
                                        .font(.ariseMono(size: 11))
                                        .foregroundColor(.warningRed)
                                }
                            }

                            Spacer()

                            Text("\(username.count)/20")
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textMuted)
                        }
                        .frame(height: 20)
                    }
                    .padding(.horizontal)

                    // Rules
                    VStack(alignment: .leading, spacing: 8) {
                        RuleRow(text: "3-20 characters", isValid: username.count >= 3 && username.count <= 20)
                        RuleRow(text: "Letters, numbers, and underscores only", isValid: username.allSatisfy { $0.isLetter || $0.isNumber || $0 == "_" } && !username.isEmpty)
                        RuleRow(text: "No underscore at start or end", isValid: !username.hasPrefix("_") && !username.hasSuffix("_"))
                    }
                    .padding(.horizontal, 24)

                    Spacer()

                    // Error message
                    if let error = error {
                        Text(error)
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.warningRed)
                            .padding(.horizontal)
                    }

                    // Save button
                    Button {
                        saveUsername()
                    } label: {
                        HStack(spacing: 8) {
                            if isSaving {
                                SwiftUI.ProgressView()
                                    .tint(.voidBlack)
                                Text("CLAIMING...")
                                    .font(.ariseHeader(size: 14, weight: .semibold))
                                    .tracking(2)
                            } else {
                                Image(systemName: "checkmark.shield.fill")
                                    .font(.system(size: 14))
                                Text("CLAIM USERNAME")
                                    .font(.ariseHeader(size: 14, weight: .semibold))
                                    .tracking(2)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 54)
                    .background(canSave ? Color.systemPrimary : Color.voidMedium)
                    .foregroundColor(canSave ? .voidBlack : .textMuted)
                    .overlay(
                        Rectangle()
                            .stroke(canSave ? Color.systemPrimary : Color.ariseBorder, lineWidth: 2)
                    )
                    .shadow(color: canSave ? .systemPrimaryGlow : .clear, radius: 15, x: 0, y: 0)
                    .padding(.horizontal)
                    .disabled(!canSave)
                    .animation(.easeInOut(duration: 0.2), value: canSave)

                    Spacer(minLength: 40)
                }
            }
            .navigationTitle("Hunter Name")
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
            }
        }
    }

    var strokeColor: Color {
        if isChecking {
            return .textMuted
        } else if validationMessage != nil {
            return .warningYellow
        } else if isAvailable == true {
            return .successGreen
        } else if isAvailable == false {
            return .warningRed
        } else {
            return .ariseBorder
        }
    }

    func checkAvailabilityDebounced() {
        // Cancel previous check
        checkTask?.cancel()
        isAvailable = nil

        let trimmed = username.trimmingCharacters(in: .whitespaces).lowercased()

        guard isValidFormat else {
            return
        }

        isChecking = true

        checkTask = Task {
            // Debounce 300ms
            try? await Task.sleep(nanoseconds: 300_000_000)

            guard !Task.isCancelled else { return }

            do {
                let result = try await APIClient.shared.checkUsernameAvailability(trimmed)
                guard !Task.isCancelled else { return }

                await MainActor.run {
                    isAvailable = result.available
                    isChecking = false
                }
            } catch {
                guard !Task.isCancelled else { return }
                await MainActor.run {
                    isChecking = false
                }
            }
        }
    }

    func saveUsername() {
        let trimmed = username.trimmingCharacters(in: .whitespaces).lowercased()

        guard isValidFormat && isAvailable == true else { return }

        isSaving = true
        error = nil

        Task {
            do {
                try await APIClient.shared.setUsername(trimmed)
                await MainActor.run {
                    isSaving = false
                    onComplete()
                    dismiss()
                }
            } catch let apiError as APIError {
                await MainActor.run {
                    isSaving = false
                    if case .serverError(409) = apiError {
                        error = "Username was just taken. Try another."
                        isAvailable = false
                    } else {
                        error = apiError.localizedDescription
                    }
                }
            } catch {
                await MainActor.run {
                    isSaving = false
                    self.error = error.localizedDescription
                }
            }
        }
    }
}

// MARK: - Rule Row

struct RuleRow: View {
    let text: String
    let isValid: Bool

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: isValid ? "checkmark.circle.fill" : "circle")
                .font(.system(size: 12))
                .foregroundColor(isValid ? .successGreen : .textMuted)

            Text(text)
                .font(.ariseMono(size: 11))
                .foregroundColor(isValid ? .textSecondary : .textMuted)
        }
    }
}

#Preview {
    UsernameSetupSheet {
        print("Username set!")
    }
}
