import SwiftUI
import UIKit

struct LogView: View {
    // Initial screenshots passed from QuestsView (or other callers)
    var initialScreenshots: [Data]?

    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel = LogViewModel()
    @StateObject private var screenshotViewModel = ScreenshotProcessingViewModel()
    @State private var showDatePicker = false
    @State private var isSessionActive = false
    @State private var showCancelConfirmation = false
    @State private var showScreenshotPicker = false
    @State private var showScreenshotPreview = false
    @State private var hasLoadedInitialScreenshots = false

    // Celebration states
    @State private var showRankUpCelebration = false
    @State private var rankUpData: (previousRank: HunterRank, newRank: HunterRank, newLevel: Int)?
    @State private var pendingXPResponse: WorkoutCreateResponse?

    // PR celebration states
    @State private var showPRCelebration = false
    @State private var prQueue: [PRAchievedResponse] = []
    @State private var currentPRIndex = 0

    // Debug mode for testing celebrations
    #if DEBUG
    @State private var showDebugCelebration = false
    #endif

    init(initialScreenshots: [Data]? = nil) {
        self.initialScreenshots = initialScreenshots
    }

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: true, glowIntensity: 0.05)

                if !isSessionActive {
                    // Idle State - No active quest
                    IdleQuestView(
                        onStartQuest: {
                            withAnimation(.smoothSpring) {
                                isSessionActive = true
                            }
                        },
                        onScanQuestLog: {
                            showScreenshotPicker = true
                        },
                        showCloseButton: true,
                        onClose: { dismiss() }
                    )
                    .swipeBackGesture()
                    #if DEBUG
                    .onLongPressGesture(minimumDuration: 2.0) {
                        // Debug: Trigger rank-up celebration for testing
                        showDebugCelebration = true
                    }
                    #endif
                } else {
                    // Active Quest Session
                    ActiveQuestView(
                        viewModel: viewModel,
                        showDatePicker: $showDatePicker,
                        onCancel: { showCancelConfirmation = true },
                        onQuestComplete: {
                            withAnimation(.smoothSpring) {
                                isSessionActive = false
                                viewModel.resetWorkout()
                            }
                        }
                    )
                }
            }
            .navigationBarHidden(true)
            .onTapGesture {
                UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
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
            .sheet(isPresented: $viewModel.showExercisePicker) {
                ExercisePickerView(viewModel: viewModel)
            }
            // PR Celebration (shows first if PRs achieved)
            .fullScreenCover(isPresented: $showPRCelebration) {
                if currentPRIndex < prQueue.count {
                    let pr = prQueue[currentPRIndex]
                    PRCelebrationView(
                        exerciseName: pr.exerciseName,
                        prType: pr.prType == "e1rm" ? .e1rm : .repPR,
                        value: pr.value,
                        onDismiss: {
                            handlePRDismiss()
                        },
                        currentIndex: currentPRIndex + 1,
                        totalCount: prQueue.count
                    )
                    .id(currentPRIndex)  // Force new view instance when index changes to reset @State
                } else {
                    // Safety fallback: return to idle instead of showing Color.clear
                    Color.clear
                        .onAppear {
                            // Emergency cleanup - shouldn't normally reach here
                            prQueue = []
                            currentPRIndex = 0
                            showPRCelebration = false
                            withAnimation(.smoothSpring) {
                                isSessionActive = false
                            }
                        }
                }
            }
            // Rank-Up Celebration (shows after PRs if rank changed)
            .fullScreenCover(isPresented: $showRankUpCelebration) {
                if let data = rankUpData {
                    RankUpCelebrationView(
                        previousRank: data.previousRank,
                        newRank: data.newRank,
                        newLevel: data.newLevel,
                        onContinue: {
                            showRankUpCelebration = false
                            // Now show the XP reward
                            // NOTE: Don't clear pendingXPResponse here - the .onChange handler will clear it
                            // when it detects this is an already-processed response
                            if let response = pendingXPResponse {
                                viewModel.xpRewardResponse = response
                            }
                        }
                    )
                } else {
                    // Safety fallback: immediately dismiss if rankUpData is nil (prevents black screen)
                    Color.clear
                        .onAppear {
                            showRankUpCelebration = false
                            // Proceed to XP view if available
                            // NOTE: Don't clear pendingXPResponse here - the .onChange handler will clear it
                            if let response = pendingXPResponse {
                                viewModel.xpRewardResponse = response
                            }
                        }
                }
            }
            // XP Reward View (shows after rank-up celebration, or directly if no rank change)
            .fullScreenCover(item: $viewModel.xpRewardResponse) { response in
                XPRewardView(
                    xpEarned: response.xpEarned,
                    xpBreakdown: response.xpBreakdown,
                    leveledUp: response.leveledUp,
                    newLevel: response.newLevel,
                    rankChanged: response.rankChanged,
                    newRank: response.newRank,
                    achievementsUnlocked: response.achievementsUnlocked,
                    onDismiss: {
                        viewModel.dismissXPReward()
                        withAnimation(.smoothSpring) {
                            isSessionActive = false
                        }
                    }
                )
            }
            // Debug celebration for testing (long-press idle view for 2 seconds)
            #if DEBUG
            .fullScreenCover(isPresented: $showDebugCelebration) {
                RankUpCelebrationView(
                    previousRank: .c,
                    newRank: .b,
                    newLevel: 46,
                    onContinue: {
                        showDebugCelebration = false
                    }
                )
            }
            #endif
            // Intercept workout response to check for PRs and rank change
            .onChange(of: viewModel.xpRewardResponse?.id) { oldValue, newValue in
                guard let response = viewModel.xpRewardResponse else { return }

                // IMPORTANT: Skip if this response was already processed (coming back from PR/rank-up flow)
                // This prevents infinite loops where setting xpRewardResponse triggers onChange again
                if let pending = pendingXPResponse, pending.id == response.id {
                    // Already processed this response - let the XP view show directly
                    pendingXPResponse = nil
                    return
                }

                // Check for PRs first (they show before rank-up)
                if !response.prsAchieved.isEmpty {
                    prQueue = response.prsAchieved
                    currentPRIndex = 0
                    pendingXPResponse = response
                    viewModel.xpRewardResponse = nil  // Clear to prevent showing XP view yet
                    showPRCelebration = true
                    return
                }

                // No PRs, check for rank change
                guard response.rankChanged,
                      let newRankStr = response.newRank else { return }

                // Rank changed! Show celebration first
                let newRank = HunterRank(rawValue: newRankStr) ?? .e
                let previousRank = getPreviousRank(from: newRank)
                let newLevel = response.newLevel ?? response.level

                rankUpData = (previousRank, newRank, newLevel)
                pendingXPResponse = response
                viewModel.xpRewardResponse = nil  // Clear to prevent showing XP view yet
                showRankUpCelebration = true
            }
            .alert("System Error", isPresented: .constant(viewModel.error != nil)) {
                Button("DISMISS", role: .cancel) {
                    viewModel.error = nil
                }
            } message: {
                Text(viewModel.error ?? "")
            }
            .alert("Abandon Quest?", isPresented: $showCancelConfirmation) {
                Button("Continue Training", role: .cancel) {}
                Button("Abandon", role: .destructive) {
                    withAnimation(.smoothSpring) {
                        isSessionActive = false
                        viewModel.resetWorkout()
                    }
                }
            } message: {
                Text("Warning: All progress will be lost. The System does not forgive weakness.")
            }
            .sheet(isPresented: $showScreenshotPicker) {
                ScreenshotPickerView(isPresented: $showScreenshotPicker) { imagesData in
                    screenshotViewModel.selectedImagesData = imagesData
                    showScreenshotPreview = true
                }
            }
            .sheet(isPresented: $showScreenshotPreview) {
                ScreenshotPreviewView(
                    viewModel: screenshotViewModel,
                    isPresented: $showScreenshotPreview
                ) { exercises in
                    // Populate the log view model with extracted exercises
                    viewModel.selectedExercises = exercises
                    // Start the session with pre-populated exercises
                    withAnimation(.smoothSpring) {
                        isSessionActive = true
                    }
                }
            }
        }
        .task {
            await viewModel.loadExercises()
        }
        .onAppear {
            // Auto-trigger screenshot preview if initial screenshots were passed
            if !hasLoadedInitialScreenshots, let screenshots = initialScreenshots, !screenshots.isEmpty {
                hasLoadedInitialScreenshots = true
                screenshotViewModel.selectedImagesData = screenshots
                showScreenshotPreview = true
            }
        }
    }

    /// Handle PR celebration dismissal - advance to next PR or proceed to rank-up/XP
    private func handlePRDismiss() {
        // Move to next PR or proceed to rank-up/XP view
        if currentPRIndex + 1 < prQueue.count {
            // More PRs to show - increment index and let fullScreenCover re-render
            // Keep showPRCelebration = true; the view will update with next PR
            currentPRIndex += 1
        } else {
            // All PRs shown, check for rank change
            if let response = pendingXPResponse,
               response.rankChanged,
               let newRankStr = response.newRank {
                // PREPARE next celebration BEFORE dismissing PR
                let newRank = HunterRank(rawValue: newRankStr) ?? .e
                let previousRank = getPreviousRank(from: newRank)
                let newLevel = response.newLevel ?? response.level
                rankUpData = (previousRank, newRank, newLevel)

                // Reset PR queue
                prQueue = []
                currentPRIndex = 0

                // THEN transition: dismiss PR and show rank-up simultaneously
                showPRCelebration = false
                showRankUpCelebration = true
            } else if let response = pendingXPResponse {
                // PREPARE XP view BEFORE dismissing PR
                // Reset PR queue
                prQueue = []
                currentPRIndex = 0

                // THEN transition: dismiss PR and show XP simultaneously
                // NOTE: Don't clear pendingXPResponse here - the .onChange handler will clear it
                showPRCelebration = false
                viewModel.xpRewardResponse = response
            } else {
                // No pending response - clean up and return to idle
                prQueue = []
                currentPRIndex = 0
                showPRCelebration = false
                withAnimation(.smoothSpring) {
                    isSessionActive = false
                }
                viewModel.resetWorkout()
            }
        }
    }

    /// Determine the previous rank based on the new rank
    private func getPreviousRank(from newRank: HunterRank) -> HunterRank {
        switch newRank {
        case .e: return .e  // Can't go lower than E
        case .d: return .e
        case .c: return .d
        case .b: return .c
        case .a: return .b
        case .s: return .a
        }
    }
}

// MARK: - Idle Quest View

struct IdleQuestView: View {
    let onStartQuest: () -> Void
    var onScanQuestLog: (() -> Void)? = nil
    var showCloseButton: Bool = false
    var onClose: (() -> Void)? = nil
    @State private var showContent = false
    @State private var pulseAnimation = false

    var body: some View {
        ZStack(alignment: .topLeading) {
            // Close button when navigated from another view
            if showCloseButton {
                Button {
                    onClose?()
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "chevron.left")
                            .font(.system(size: 14, weight: .semibold))
                        Text("Back")
                            .font(.ariseMono(size: 14, weight: .medium))
                    }
                    .foregroundColor(.systemPrimary)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                }
                .zIndex(1)
            }

            VStack(spacing: 32) {
            Spacer()

            // System notification
            Text("[ SYSTEM ]")
                .font(.ariseMono(size: 11, weight: .medium))
                .foregroundColor(.systemPrimary)
                .tracking(2)
                .opacity(showContent ? 1 : 0)

            // Quest icon with pulse
            ZStack {
                // Outer glow rings
                Circle()
                    .stroke(Color.systemPrimary.opacity(0.1), lineWidth: 1)
                    .frame(width: 140, height: 140)
                    .scaleEffect(pulseAnimation ? 1.1 : 1.0)

                Circle()
                    .fill(Color.systemPrimary.opacity(0.05))
                    .frame(width: 120, height: 120)

                Circle()
                    .fill(Color.systemPrimary.opacity(0.1))
                    .frame(width: 90, height: 90)

                // Icon
                Image(systemName: "bolt.shield.fill")
                    .font(.system(size: 40))
                    .foregroundColor(.systemPrimary)
                    .shadow(color: .systemPrimaryGlow, radius: 10, x: 0, y: 0)
            }
            .opacity(showContent ? 1 : 0)
            .scaleEffect(showContent ? 1 : 0.8)

            VStack(spacing: 12) {
                Text("DAILY QUEST AVAILABLE")
                    .font(.ariseHeader(size: 24, weight: .bold))
                    .foregroundColor(.textPrimary)
                    .tracking(1)

                Text("Begin your training to grow stronger.\nThe System awaits your dedication.")
                    .font(.ariseBody(size: 15))
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
                    .lineSpacing(4)
            }
            .opacity(showContent ? 1 : 0)

            Spacer()

            // Start Quest Button - ARISE style
            Button {
                let impactFeedback = UIImpactFeedbackGenerator(style: .medium)
                impactFeedback.impactOccurred()
                onStartQuest()
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "play.fill")
                        .font(.system(size: 14))
                    Text("BEGIN QUEST")
                        .font(.ariseHeader(size: 16, weight: .semibold))
                        .tracking(2)
                }
            }
            .frame(maxWidth: .infinity)
            .frame(height: 56)
            .background(Color.systemPrimary)
            .foregroundColor(.voidBlack)
            .overlay(
                Rectangle()
                    .stroke(Color.systemPrimary, lineWidth: 2)
            )
            .shadow(color: .systemPrimaryGlow, radius: 20, x: 0, y: 0)
            .padding(.horizontal, 24)
            .opacity(showContent ? 1 : 0)

            // Scan Quest Log Button
            if let onScan = onScanQuestLog {
                Button {
                    let impactFeedback = UIImpactFeedbackGenerator(style: .light)
                    impactFeedback.impactOccurred()
                    onScan()
                } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "camera.viewfinder")
                            .font(.system(size: 14))
                        Text("SCAN QUEST LOG")
                            .font(.ariseHeader(size: 14, weight: .semibold))
                            .tracking(2)
                    }
                }
                .frame(maxWidth: .infinity)
                .frame(height: 48)
                .background(Color.voidMedium)
                .foregroundColor(.textPrimary)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.ariseBorder, lineWidth: 1)
                )
                .padding(.horizontal, 24)
                .opacity(showContent ? 1 : 0)
            }

            Spacer()
                .frame(height: 100)
            } // end VStack
        } // end ZStack
        .onAppear {
            withAnimation(.easeOut(duration: 0.6).delay(0.2)) {
                showContent = true
            }
            withAnimation(.easeInOut(duration: 2).repeatForever(autoreverses: true)) {
                pulseAnimation = true
            }
        }
    }
}

// MARK: - Active Quest View

struct ActiveQuestView: View {
    @ObservedObject var viewModel: LogViewModel
    @Binding var showDatePicker: Bool
    let onCancel: () -> Void
    let onQuestComplete: () -> Void
    @State private var showSupersetPicker = false

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                // Header
                ActiveQuestHeader(onCancel: onCancel)
                    .fadeIn(delay: 0)

                // Quest Timer Card
                QuestTimerCard()
                    .padding(.horizontal)
                    .fadeIn(delay: 0.1)

                // Date Selector
                VStack(spacing: 12) {
                    Button {
                        withAnimation(.smoothSpring) {
                            showDatePicker.toggle()
                        }
                    } label: {
                        HStack {
                            HStack(spacing: 12) {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 4)
                                        .fill(Color.systemPrimary.opacity(0.1))
                                        .frame(width: 36, height: 36)

                                    Image(systemName: "calendar")
                                        .font(.system(size: 16))
                                        .foregroundColor(.systemPrimary)
                                }

                                VStack(alignment: .leading, spacing: 2) {
                                    Text("QUEST DATE")
                                        .font(.ariseMono(size: 10, weight: .medium))
                                        .foregroundColor(.textMuted)
                                        .tracking(1)

                                    Text(viewModel.workoutDate.formattedMedium)
                                        .font(.ariseMono(size: 14, weight: .medium))
                                        .foregroundColor(.textPrimary)
                                }
                            }

                            Spacer()

                            Image(systemName: showDatePicker ? "chevron.up" : "chevron.down")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(.textMuted)
                        }
                        .padding(16)
                        .background(Color.voidMedium)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.ariseBorder, lineWidth: 1)
                        )
                    }

                    if showDatePicker {
                        DatePicker(
                            "Quest Date",
                            selection: $viewModel.workoutDate,
                            displayedComponents: .date
                        )
                        .datePickerStyle(.graphical)
                        .tint(.systemPrimary)
                        .padding()
                        .background(Color.voidMedium)
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.ariseBorder, lineWidth: 1)
                        )
                    }
                }
                .padding(.horizontal)
                .fadeIn(delay: 0.15)

                // Exercises Section
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        AriseSectionHeader(title: "Objectives")

                        Spacer()

                        Menu {
                            Button {
                                viewModel.showExercisePicker = true
                            } label: {
                                Label("Add Exercise", systemImage: "dumbbell")
                            }

                            Button {
                                showSupersetPicker = true
                            } label: {
                                Label("Add Superset", systemImage: "link")
                            }
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "plus")
                                    .font(.system(size: 12, weight: .bold))
                                Text("ADD")
                                    .font(.ariseMono(size: 12, weight: .semibold))
                                    .tracking(1)
                            }
                            .foregroundColor(.systemPrimary)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(Color.systemPrimary.opacity(0.1))
                            .cornerRadius(4)
                        }
                    }
                    .padding(.horizontal)

                    if viewModel.selectedExercises.isEmpty {
                        EmptyObjectiveCard()
                            .padding(.horizontal)
                    } else {
                        ForEach(viewModel.exercisesGroupedForDisplay) { item in
                            switch item {
                            case .single(_, let index):
                                ObjectiveCard(
                                    exercise: $viewModel.selectedExercises[index],
                                    onAddSet: { viewModel.addSet(to: index) },
                                    onCopySet: { viewModel.copyLastSet(for: index) },
                                    onRemoveSet: { setIndex in
                                        viewModel.removeSet(from: index, at: setIndex)
                                    },
                                    onRemove: { viewModel.removeExercise(at: index) }
                                )
                                .padding(.horizontal)
                                .fadeIn(delay: 0.2 + Double(index) * 0.05)

                            case .superset(let groupId, let exercises, let indices):
                                SupersetCard(
                                    groupId: groupId,
                                    exercises: exercises,
                                    indices: indices,
                                    allExercises: $viewModel.selectedExercises,
                                    onAddRound: { id in
                                        viewModel.addRoundToSuperset(groupId: id)
                                    },
                                    onRemoveSuperset: { id in
                                        viewModel.removeSuperset(groupId: id)
                                    }
                                )
                                .padding(.horizontal)
                                .fadeIn(delay: 0.2)
                            }
                        }
                    }
                }

                // Session RPE
                VStack(alignment: .leading, spacing: 12) {
                    AriseSectionHeader(title: "Difficulty Rating")
                        .padding(.horizontal)

                    AriseRPESelector(selectedRPE: $viewModel.sessionRPE)
                        .padding(.horizontal)
                }
                .fadeIn(delay: 0.25)

                // Notes
                VStack(alignment: .leading, spacing: 12) {
                    AriseSectionHeader(title: "Hunter Notes")
                        .padding(.horizontal)

                    TextField("Record your observations...", text: $viewModel.workoutNotes, axis: .vertical)
                        .lineLimit(3...6)
                        .font(.ariseMono(size: 14))
                        .foregroundColor(.textPrimary)
                        .padding(16)
                        .background(Color.voidMedium)
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.ariseBorder, lineWidth: 1)
                        )
                        .padding(.horizontal)
                }
                .fadeIn(delay: 0.3)

                // Complete Quest Button
                Button {
                    Task {
                        await viewModel.saveWorkout()
                    }
                } label: {
                    HStack(spacing: 8) {
                        if viewModel.isSaving {
                            SwiftUI.ProgressView()
                                .tint(.voidBlack)
                            Text("SUBMITTING...")
                                .font(.ariseHeader(size: 14, weight: .semibold))
                                .tracking(2)
                        } else {
                            Image(systemName: "checkmark.shield.fill")
                                .font(.system(size: 16))
                            Text("COMPLETE QUEST")
                                .font(.ariseHeader(size: 14, weight: .semibold))
                                .tracking(2)
                        }
                    }
                }
                .frame(maxWidth: .infinity)
                .frame(height: 54)
                .background(
                    viewModel.canSave ? Color.systemPrimary : Color.voidLight
                )
                .foregroundColor(viewModel.canSave ? .voidBlack : .textMuted)
                .overlay(
                    Rectangle()
                        .stroke(viewModel.canSave ? Color.systemPrimary : Color.ariseBorder, lineWidth: 2)
                )
                .shadow(color: viewModel.canSave ? Color.systemPrimaryGlow : .clear, radius: 15, x: 0, y: 0)
                .padding(.horizontal)
                .disabled(!viewModel.canSave || viewModel.isSaving)
                .fadeIn(delay: 0.35)

                Spacer(minLength: 100)
            }
            .padding(.vertical)
            .contentShape(Rectangle())
            .onTapGesture {
                UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
            }
        }
        .scrollDismissesKeyboard(.interactively)
        .sheet(isPresented: $showSupersetPicker) {
            SupersetPickerView(viewModel: viewModel) { exercises in
                viewModel.createSuperset(with: exercises)
            }
        }
    }
}

// MARK: - Active Quest Header

struct ActiveQuestHeader: View {
    let onCancel: () -> Void

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Circle()
                        .fill(Color.successGreen)
                        .frame(width: 8, height: 8)
                        .shadow(color: .successGreen, radius: 4, x: 0, y: 0)

                    Text("QUEST ACTIVE")
                        .font(.ariseMono(size: 11, weight: .semibold))
                        .foregroundColor(.successGreen)
                        .tracking(2)
                }

                Text("Training Session")
                    .font(.ariseHeader(size: 24, weight: .bold))
                    .foregroundColor(.textPrimary)
            }

            Spacer()

            // Cancel button
            Button(action: onCancel) {
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.voidLight)
                        .frame(width: 40, height: 40)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.ariseBorder, lineWidth: 1)
                        )

                    Image(systemName: "xmark")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.textSecondary)
                }
            }
        }
        .padding(.horizontal)
    }
}

// MARK: - Quest Timer Card

struct QuestTimerCard: View {
    // Track actual start time - timer continues even when app is backgrounded
    @State private var workoutStartTime: Date = Date()
    @State private var pausedDuration: TimeInterval = 0  // Total time spent paused
    @State private var pauseStartTime: Date?  // When current pause began (nil if running)
    @State private var isRunning = true
    @State private var displayTimer: Timer?  // Only for UI updates, not time tracking
    @State private var currentTime = Date()  // Triggers UI refresh

    var elapsedTime: TimeInterval {
        let totalElapsed = currentTime.timeIntervalSince(workoutStartTime)
        let currentPauseDuration = pauseStartTime.map { currentTime.timeIntervalSince($0) } ?? 0
        return max(0, totalElapsed - pausedDuration - currentPauseDuration)
    }

    var timeString: String {
        let total = Int(elapsedTime)
        let hours = total / 3600
        let minutes = (total % 3600) / 60
        let seconds = total % 60
        if hours > 0 {
            return String(format: "%02d:%02d:%02d", hours, minutes, seconds)
        }
        return String(format: "%02d:%02d", minutes, seconds)
    }

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 6) {
                Text(timeString)
                    .font(.ariseDisplay(size: 36, weight: .bold))
                    .foregroundColor(.textPrimary)
                    .shadow(color: .systemPrimaryGlow.opacity(0.3), radius: 10, x: 0, y: 0)

                HStack(spacing: 8) {
                    Circle()
                        .fill(isRunning ? Color.systemPrimary : Color.gold)
                        .frame(width: 6, height: 6)

                    Text(isRunning ? "TIME ELAPSED" : "PAUSED")
                        .font(.ariseMono(size: 10, weight: .medium))
                        .foregroundColor(isRunning ? .textMuted : .gold)
                        .tracking(1)
                }
            }

            Spacer()

            // Pause/Play button
            Button {
                let impactFeedback = UIImpactFeedbackGenerator(style: .light)
                impactFeedback.impactOccurred()
                toggleTimer()
            } label: {
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(isRunning ? Color.voidLight : Color.systemPrimary.opacity(0.15))
                        .frame(width: 48, height: 48)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(isRunning ? Color.ariseBorder : Color.systemPrimary.opacity(0.3), lineWidth: 1)
                        )

                    Image(systemName: isRunning ? "pause.fill" : "play.fill")
                        .font(.system(size: 16))
                        .foregroundColor(isRunning ? .textPrimary : .systemPrimary)
                }
            }
        }
        .padding(20)
        .background(
            LinearGradient(
                colors: [Color.voidMedium, Color.voidDark],
                startPoint: .top,
                endPoint: .bottom
            )
        )
        .overlay(
            // Top glow line
            Rectangle()
                .fill(Color.systemPrimary.opacity(0.3))
                .frame(height: 1),
            alignment: .top
        )
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .cornerRadius(4)
        .onAppear {
            startDisplayTimer()
        }
        .onDisappear {
            displayTimer?.invalidate()
        }
    }

    private func startDisplayTimer() {
        // Timer just updates the display - actual time is calculated from startTime
        displayTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            currentTime = Date()
        }
    }

    private func toggleTimer() {
        if isRunning {
            // Pausing - record when pause started
            pauseStartTime = Date()
            isRunning = false
        } else {
            // Resuming - add pause duration to total paused time
            if let pauseStart = pauseStartTime {
                pausedDuration += Date().timeIntervalSince(pauseStart)
            }
            pauseStartTime = nil
            isRunning = true
        }
        // Update display immediately
        currentTime = Date()
    }
}

// MARK: - Empty Objective Card

struct EmptyObjectiveCard: View {
    var body: some View {
        VStack(spacing: 16) {
            ZStack {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.voidLight)
                    .frame(width: 64, height: 64)

                Image(systemName: "scroll")
                    .font(.system(size: 28))
                    .foregroundColor(.textMuted)
            }

            Text("No Objectives Set")
                .font(.ariseHeader(size: 16, weight: .semibold))
                .foregroundColor(.textPrimary)

            Text("Add exercises to begin your training quest")
                .font(.ariseMono(size: 13))
                .foregroundColor(.textSecondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 32)
        .systemPanelStyle()
    }
}

// MARK: - Objective Card (Exercise)

struct ObjectiveCard: View {
    @Binding var exercise: LoggedExercise
    let onAddSet: () -> Void
    let onCopySet: () -> Void
    let onRemoveSet: (Int) -> Void
    let onRemove: () -> Void

    @State private var showWeightInfo = false

    var exerciseColor: Color {
        Color.exerciseColor(for: exercise.exerciseName)
    }

    var fantasyName: String {
        ExerciseFantasyNames.fantasyName(for: exercise.exerciseName)
    }

    var completedSets: Int {
        exercise.sets.filter { ($0.isBodyweight || $0.weight > 0) && $0.reps > 0 }.count
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header with left color border
            HStack(spacing: 0) {
                // Left color indicator
                Rectangle()
                    .fill(exerciseColor)
                    .frame(width: 4)

                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(exercise.exerciseName)
                            .font(.ariseHeader(size: 16, weight: .semibold))
                            .foregroundColor(.textPrimary)

                        Text("\"\(fantasyName)\"")
                            .font(.ariseMono(size: 11))
                            .foregroundColor(.textMuted)
                            .italic()
                    }

                    Spacer()

                    // Progress indicator
                    HStack(spacing: 4) {
                        Text("\(completedSets)/\(exercise.sets.count)")
                            .font(.ariseMono(size: 12, weight: .medium))
                            .foregroundColor(completedSets == exercise.sets.count ? .successGreen : .textSecondary)

                        Text("SETS")
                            .font(.ariseMono(size: 10, weight: .medium))
                            .foregroundColor(.textMuted)
                            .tracking(0.5)
                    }

                    Menu {
                        Button(action: onAddSet) {
                            Label("Add Set", systemImage: "plus")
                        }
                        Button(action: onCopySet) {
                            Label("Copy Last Set", systemImage: "doc.on.doc")
                        }
                        Divider()
                        Button(role: .destructive, action: onRemove) {
                            Label("Remove Objective", systemImage: "trash")
                        }
                    } label: {
                        ZStack {
                            RoundedRectangle(cornerRadius: 4)
                                .fill(Color.voidLight)
                                .frame(width: 32, height: 32)

                            Image(systemName: "ellipsis")
                                .font(.system(size: 12))
                                .foregroundColor(.textSecondary)
                        }
                    }
                }
                .padding(16)
            }
            .background(Color.voidMedium)

            // Divider
            Rectangle()
                .fill(Color.ariseBorder)
                .frame(height: 1)

            // Sets Grid Header
            HStack {
                Text("SET")
                    .frame(width: 36, alignment: .leading)
                Text("BW")
                    .frame(width: 28)
                HStack(spacing: 4) {
                    Text("WEIGHT")
                    Button {
                        showWeightInfo = true
                    } label: {
                        Image(systemName: "info.circle")
                            .font(.system(size: 10))
                            .foregroundColor(.textMuted)
                    }
                    .popover(isPresented: $showWeightInfo, arrowEdge: .bottom) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("WEIGHT CONVENTION")
                                .font(.ariseMono(size: 11, weight: .semibold))
                                .foregroundColor(.textPrimary)

                            Text("Enter the total weight lifted.")
                                .font(.ariseMono(size: 12))
                                .foregroundColor(.textSecondary)

                            Text("For dumbbells, combine both sides:\n40lb each = 80lb total")
                                .font(.ariseMono(size: 11))
                                .foregroundColor(.textMuted)
                                .italic()
                        }
                        .padding(12)
                        .frame(width: 220)
                        .background(Color.voidMedium)
                        .presentationCompactAdaptation(.popover)
                    }
                }
                .frame(maxWidth: .infinity)
                Text("REPS")
                    .frame(width: 56)
                Text("RPE")
                    .frame(width: 44)
                Spacer()
                    .frame(width: 28)
            }
            .font(.ariseMono(size: 10, weight: .semibold))
            .foregroundColor(.textMuted)
            .tracking(1)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(Color.voidDark)

            // Sets
            ForEach(Array(exercise.sets.enumerated()), id: \.element.id) { index, _ in
                AriseSetRow(
                    set: $exercise.sets[index],
                    exerciseColor: exerciseColor,
                    isCompleted: (exercise.sets[index].isBodyweight || exercise.sets[index].weight > 0) && exercise.sets[index].reps > 0,
                    onRemove: { onRemoveSet(index) }
                )

                if index < exercise.sets.count - 1 {
                    Rectangle()
                        .fill(Color.ariseBorder)
                        .frame(height: 1)
                        .padding(.horizontal, 16)
                }
            }

            // Add Set Button
            Button(action: onAddSet) {
                HStack(spacing: 8) {
                    Image(systemName: "plus")
                        .font(.system(size: 12, weight: .bold))
                    Text("ADD SET")
                        .font(.ariseMono(size: 11, weight: .semibold))
                        .tracking(1)
                }
                .foregroundColor(.systemPrimary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
            }
            .background(Color.voidDark)
        }
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }
}

// MARK: - Set Row

struct AriseSetRow: View {
    @Binding var set: LoggedSet
    var exerciseColor: Color
    var isCompleted: Bool
    let onRemove: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            // Set number with completion indicator
            ZStack {
                if isCompleted {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.successGreen)
                        .frame(width: 24, height: 24)
                    Image(systemName: "checkmark")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundColor(.voidBlack)
                } else {
                    Text("\(set.setNumber)")
                        .font(.ariseMono(size: 14, weight: .medium))
                        .foregroundColor(.textSecondary)
                }
            }
            .frame(width: 36)

            // Bodyweight toggle button
            Button {
                withAnimation(.easeInOut(duration: 0.15)) {
                    set.isBodyweight.toggle()
                    if set.isBodyweight {
                        set.weightText = ""  // Clear weight when enabling BW
                    }
                }
            } label: {
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(set.isBodyweight ? Color.systemPrimary.opacity(0.2) : Color.voidLight)
                        .frame(width: 28, height: 28)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(set.isBodyweight ? Color.systemPrimary : Color.ariseBorder, lineWidth: 1)
                        )

                    Text("BW")
                        .font(.ariseMono(size: 9, weight: .semibold))
                        .foregroundColor(set.isBodyweight ? .systemPrimary : .textMuted)
                }
            }

            // Weight input OR bodyweight label
            if !set.isBodyweight {
                HStack(spacing: 4) {
                    TextField("", text: $set.weightText)
                        .keyboardType(.decimalPad)
                        .multilineTextAlignment(.center)
                        .font(.ariseMono(size: 15, weight: .medium))
                        .foregroundColor(.textPrimary)
                        .padding(.vertical, 10)
                        .padding(.horizontal, 8)
                        .background(Color.voidLight)
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.ariseBorder, lineWidth: 1)
                        )

                    Text("lb")
                        .font(.ariseMono(size: 10))
                        .foregroundColor(.textMuted)
                }
                .frame(maxWidth: .infinity)
            } else {
                Text("BODYWEIGHT")
                    .font(.ariseMono(size: 11, weight: .medium))
                    .foregroundColor(.systemPrimary)
                    .frame(maxWidth: .infinity)
            }

            // Reps input
            TextField("", text: $set.repsText)
                .keyboardType(.numberPad)
                .multilineTextAlignment(.center)
                .font(.ariseMono(size: 15, weight: .medium))
                .foregroundColor(.textPrimary)
                .padding(.vertical, 10)
                .padding(.horizontal, 8)
                .background(Color.voidLight)
                .cornerRadius(4)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.ariseBorder, lineWidth: 1)
                )
                .frame(width: 56)

            // RPE selector
            AriseRPEMiniSelector(selectedRPE: $set.rpe)
                .frame(width: 44)

            // Remove button
            Button(action: onRemove) {
                Image(systemName: "xmark")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.textMuted)
            }
            .frame(width: 28)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(isCompleted ? Color.successGreen.opacity(0.05) : Color.clear)
    }
}

// MARK: - RPE Selector

struct AriseRPESelector: View {
    @Binding var selectedRPE: Int?

    var body: some View {
        HStack(spacing: 8) {
            ForEach([6, 7, 8, 9, 10], id: \.self) { rpe in
                Button {
                    withAnimation(.quickSpring) {
                        if selectedRPE == rpe {
                            selectedRPE = nil
                        } else {
                            selectedRPE = rpe
                        }
                    }
                } label: {
                    Text("\(rpe)")
                        .font(.ariseMono(size: 14, weight: .semibold))
                        .frame(width: 48, height: 48)
                        .background(selectedRPE == rpe ? Color.systemPrimary : Color.voidMedium)
                        .foregroundColor(selectedRPE == rpe ? .voidBlack : .textSecondary)
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(selectedRPE == rpe ? Color.systemPrimary : Color.ariseBorder, lineWidth: 1)
                        )
                        .shadow(color: selectedRPE == rpe ? Color.systemPrimaryGlow : .clear, radius: 8, x: 0, y: 0)
                }
            }
        }
    }
}

// MARK: - Mini RPE Selector

struct AriseRPEMiniSelector: View {
    @Binding var selectedRPE: Int?

    var body: some View {
        Menu {
            ForEach([6, 7, 8, 9, 10], id: \.self) { rpe in
                Button {
                    selectedRPE = rpe
                } label: {
                    Text("RPE \(rpe)")
                }
            }
            Divider()
            Button {
                selectedRPE = nil
            } label: {
                Text("None")
            }
        } label: {
            Text(selectedRPE.map { "\($0)" } ?? "-")
                .font(.ariseMono(size: 13, weight: .medium))
                .foregroundColor(selectedRPE != nil ? .systemPrimary : .textMuted)
                .frame(width: 36, height: 36)
                .background(Color.voidLight)
                .cornerRadius(4)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.ariseBorder, lineWidth: 1)
                )
        }
    }
}

// MARK: - Exercise Picker View

struct ExercisePickerView: View {
    @ObservedObject var viewModel: LogViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                VStack(spacing: 0) {
                    // Search Bar - ARISE style
                    HStack(spacing: 12) {
                        Image(systemName: "magnifyingglass")
                            .foregroundColor(.textMuted)

                        TextField("Search objectives...", text: $viewModel.searchText)
                            .font(.ariseMono(size: 14))
                            .foregroundColor(.textPrimary)

                        if !viewModel.searchText.isEmpty {
                            Button {
                                viewModel.searchText = ""
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .foregroundColor(.textMuted)
                            }
                        }
                    }
                    .padding(14)
                    .background(Color.voidMedium)
                    .cornerRadius(4)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.ariseBorder, lineWidth: 1)
                    )
                    .padding()

                    // Category Filter
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            AriseCategoryChip(
                                title: "ALL",
                                isSelected: viewModel.selectedCategory == nil
                            ) {
                                viewModel.selectedCategory = nil
                            }

                            ForEach(viewModel.categories, id: \.self) { category in
                                AriseCategoryChip(
                                    title: category.uppercased(),
                                    isSelected: viewModel.selectedCategory == category
                                ) {
                                    viewModel.selectedCategory = category
                                }
                            }
                        }
                        .padding(.horizontal)
                    }
                    .padding(.bottom, 16)

                    // Exercise List
                    if viewModel.isLoading {
                        Spacer()
                        SwiftUI.ProgressView()
                            .tint(.systemPrimary)
                        Spacer()
                    } else {
                        List {
                            ForEach(viewModel.filteredExercises) { exercise in
                                Button {
                                    viewModel.addExercise(exercise)
                                } label: {
                                    AriseExerciseListRow(exercise: exercise)
                                }
                                .listRowBackground(Color.voidMedium)
                                .listRowSeparatorTint(Color.ariseBorder)
                            }
                        }
                        .listStyle(.plain)
                        .scrollContentBackground(.hidden)
                    }
                }
            }
            .navigationTitle("Select Objective")
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
}

// MARK: - Category Chip

struct AriseCategoryChip: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.ariseMono(size: 11, weight: .semibold))
                .tracking(1)
                .foregroundColor(isSelected ? .voidBlack : .textSecondary)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(isSelected ? Color.systemPrimary : Color.voidMedium)
                .cornerRadius(4)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(isSelected ? Color.systemPrimary : Color.ariseBorder, lineWidth: 1)
                )
        }
    }
}

// MARK: - Exercise List Row

struct AriseExerciseListRow: View {
    let exercise: ExerciseResponse

    var exerciseColor: Color {
        Color.exerciseColor(for: exercise.name)
    }

    var fantasyName: String {
        ExerciseFantasyNames.fantasyName(for: exercise.name)
    }

    var body: some View {
        HStack(spacing: 0) {
            // Color indicator
            Rectangle()
                .fill(exerciseColor)
                .frame(width: 4, height: 50)

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(exercise.name)
                        .font(.ariseHeader(size: 15, weight: .medium))
                        .foregroundColor(.textPrimary)

                    HStack(spacing: 8) {
                        Text((exercise.category ?? "OTHER").uppercased())
                            .font(.ariseMono(size: 10, weight: .semibold))
                            .foregroundColor(exerciseColor)
                            .tracking(0.5)

                        if let muscle = exercise.primaryMuscle {
                            Circle()
                                .fill(Color.textMuted)
                                .frame(width: 3, height: 3)

                            Text(muscle.capitalized)
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textSecondary)
                        }
                    }
                }

                Spacer()

                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.systemPrimary.opacity(0.1))
                        .frame(width: 32, height: 32)

                    Image(systemName: "plus")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.systemPrimary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }
    }
}

// MARK: - Legacy Support

// Keep old names as aliases for backward compatibility
typealias IdleWorkoutView = IdleQuestView
typealias ActiveWorkoutView = ActiveQuestView
typealias WorkoutTimerCard = QuestTimerCard
typealias SetRow = AriseSetRow
typealias RPESelector = AriseRPESelector
typealias RPEMiniSelector = AriseRPEMiniSelector
typealias CategoryChip = AriseCategoryChip
typealias ExerciseListRow = AriseExerciseListRow

#Preview {
    LogView()
}
