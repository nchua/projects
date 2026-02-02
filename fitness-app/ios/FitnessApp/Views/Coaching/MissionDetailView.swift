import SwiftUI

struct MissionDetailView: View {
    let missionId: String
    @StateObject private var viewModel = MissionDetailViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                Color.bgVoid.ignoresSafeArea()

                if viewModel.isLoading {
                    ProgressView()
                        .tint(.systemPrimary)
                } else if let mission = viewModel.mission {
                    ScrollView {
                        VStack(spacing: 24) {
                            // Header Card
                            MissionHeaderCard(mission: mission)

                            // Coaching Message
                            if let message = mission.coachingMessage {
                                CoachingMessageCard(message: message)
                            }

                            // Workouts List
                            VStack(alignment: .leading, spacing: 14) {
                                Text("This Week's Workouts")
                                    .font(.system(size: 18, weight: .semibold))
                                    .foregroundColor(.white)
                                    .padding(.horizontal, 20)

                                ForEach(mission.workouts, id: \.id) { workout in
                                    WorkoutPrescriptionCard(workout: workout)
                                }
                            }

                            // Bottom spacing
                            Spacer().frame(height: 100)
                        }
                        .padding(.vertical)
                    }
                } else if let error = viewModel.error {
                    VStack(spacing: 16) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 48))
                            .foregroundColor(.warningRed)
                        Text(error)
                            .foregroundColor(.textSecondary)
                    }
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(.white)
                            .frame(width: 32, height: 32)
                            .background(Color.white.opacity(0.1))
                            .clipShape(Circle())
                    }
                }

                ToolbarItem(placement: .principal) {
                    Text("Weekly Mission")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundColor(.white)
                }
            }
        }
        .task {
            await viewModel.loadMission(id: missionId)
        }
    }
}

// MARK: - Mission Header Card

struct MissionHeaderCard: View {
    let mission: WeeklyMissionResponse

    var progressPercent: Double {
        guard mission.workoutsTotal > 0 else { return 0 }
        return Double(mission.workoutsCompleted) / Double(mission.workoutsTotal)
    }

    var body: some View {
        VStack(spacing: 20) {
            // Goal Info
            HStack(spacing: 16) {
                // Goal Icon
                ZStack {
                    RoundedRectangle(cornerRadius: 16)
                        .fill(Color.systemPrimary.opacity(0.15))
                        .frame(width: 60, height: 60)

                    Text("🎯")
                        .font(.system(size: 28))
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(mission.goalExerciseName)
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(.white)

                    HStack(spacing: 4) {
                        Text("\(Int(mission.goalTargetWeight))")
                            .font(.system(size: 24, weight: .bold))
                            .foregroundColor(.systemPrimary)

                        Text(mission.goalWeightUnit)
                            .font(.system(size: 14))
                            .foregroundColor(.textSecondary)

                        Text("goal")
                            .font(.system(size: 14))
                            .foregroundColor(.textSecondary)
                    }
                }

                Spacer()
            }

            // Progress Bar
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("\(mission.workoutsCompleted) of \(mission.workoutsTotal) workouts completed")
                        .font(.system(size: 13))
                        .foregroundColor(.textSecondary)

                    Spacer()

                    Text("\(mission.daysRemaining) days left")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(mission.daysRemaining <= 2 ? .warningRed : .systemPrimary)
                }

                GeometryReader { geometry in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Color.white.opacity(0.1))
                            .frame(height: 8)

                        RoundedRectangle(cornerRadius: 4)
                            .fill(
                                LinearGradient(
                                    colors: [Color.systemPrimary, Color(hex: "00FF88")],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                            .frame(width: geometry.size.width * progressPercent, height: 8)
                    }
                }
                .frame(height: 8)
            }

            // Weekly Target
            if let target = mission.weeklyTarget {
                HStack(spacing: 8) {
                    Image(systemName: "flag.fill")
                        .foregroundColor(.gold)
                    Text(target)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(.white)
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.gold.opacity(0.1))
                .cornerRadius(10)
            }

            // XP Reward
            HStack {
                Text("Mission Reward")
                    .font(.system(size: 14))
                    .foregroundColor(.textSecondary)

                Spacer()

                HStack(spacing: 4) {
                    Text("⚡️")
                    Text("+\(mission.xpReward) XP")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.gold)
                }
            }
        }
        .padding(20)
        .background(Color.bgCard)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.systemPrimary.opacity(0.2), lineWidth: 1)
        )
        .padding(.horizontal, 20)
    }
}

// MARK: - Coaching Message Card

struct CoachingMessageCard: View {
    let message: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "quote.opening")
                .font(.system(size: 20))
                .foregroundColor(.systemPrimary)

            Text(message)
                .font(.system(size: 14))
                .foregroundColor(.textSecondary)
                .italic()
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.bgCard)
        .cornerRadius(12)
        .padding(.horizontal, 20)
    }
}

// MARK: - Workout Prescription Card

struct WorkoutPrescriptionCard: View {
    let workout: MissionWorkoutResponse
    @State private var isExpanded = false

    var isCompleted: Bool {
        workout.status == "completed"
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header (always visible)
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            } label: {
                HStack(spacing: 14) {
                    // Day badge
                    ZStack {
                        Circle()
                            .fill(isCompleted ? Color(hex: "00FF88").opacity(0.15) : Color.systemPrimary.opacity(0.15))
                            .frame(width: 44, height: 44)

                        if isCompleted {
                            Image(systemName: "checkmark")
                                .font(.system(size: 18, weight: .bold))
                                .foregroundColor(Color(hex: "00FF88"))
                        } else {
                            Text("\(workout.dayNumber)")
                                .font(.system(size: 18, weight: .bold))
                                .foregroundColor(.systemPrimary)
                        }
                    }

                    // Info
                    VStack(alignment: .leading, spacing: 4) {
                        Text(workout.focus)
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)

                        Text("\(workout.prescriptions.count) exercises")
                            .font(.system(size: 13))
                            .foregroundColor(.textSecondary)
                    }

                    Spacer()

                    // Status
                    if isCompleted {
                        Text("Completed")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(Color(hex: "00FF88"))
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(Color(hex: "00FF88").opacity(0.1))
                            .cornerRadius(20)
                    } else {
                        Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(.textSecondary)
                    }
                }
                .padding(16)
            }
            .buttonStyle(PlainButtonStyle())

            // Exercise list (expandable)
            if isExpanded && !workout.prescriptions.isEmpty {
                VStack(spacing: 0) {
                    Divider()
                        .background(Color.white.opacity(0.05))

                    ForEach(workout.prescriptions, id: \.id) { prescription in
                        PrescriptionRow(prescription: prescription)

                        if prescription.id != workout.prescriptions.last?.id {
                            Divider()
                                .background(Color.white.opacity(0.03))
                                .padding(.leading, 16)
                        }
                    }
                }
                .padding(.bottom, 8)
            }
        }
        .background(Color.bgCard)
        .cornerRadius(14)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(
                    isCompleted ? Color(hex: "00FF88").opacity(0.3) : Color.white.opacity(0.05),
                    lineWidth: 1
                )
        )
        .padding(.horizontal, 20)
    }
}

struct PrescriptionRow: View {
    let prescription: ExercisePrescriptionResponse

    var body: some View {
        HStack(spacing: 12) {
            // Completion indicator
            Circle()
                .fill(prescription.isCompleted ? Color(hex: "00FF88") : Color.white.opacity(0.1))
                .frame(width: 8, height: 8)

            // Exercise name
            Text(prescription.exerciseName)
                .font(.system(size: 14))
                .foregroundColor(.white)
                .lineLimit(1)

            Spacer()

            // Prescription
            HStack(spacing: 4) {
                Text("\(prescription.sets) × \(prescription.reps)")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(.systemPrimary)

                if let weight = prescription.weight {
                    Text("@ \(Int(weight)) \(prescription.weightUnit)")
                        .font(.system(size: 13))
                        .foregroundColor(.textSecondary)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }
}

// MARK: - View Model

@MainActor
class MissionDetailViewModel: ObservableObject {
    @Published var mission: WeeklyMissionResponse?
    @Published var isLoading = false
    @Published var error: String?

    private let apiClient = APIClient.shared

    func loadMission(id: String) async {
        isLoading = true
        error = nil

        do {
            mission = try await APIClient.shared.getMission(id: id)
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }
}

// MARK: - Accept Mission Sheet

struct AcceptMissionSheet: View {
    let mission: WeeklyMissionSummary
    let onAccept: () -> Void
    let onDecline: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 24) {
            // Handle indicator
            Capsule()
                .fill(Color.white.opacity(0.3))
                .frame(width: 40, height: 4)
                .padding(.top, 12)

            // Header
            VStack(spacing: 8) {
                Text("🎯")
                    .font(.system(size: 48))

                Text("Weekly Mission Ready")
                    .font(.system(size: 24, weight: .bold))
                    .foregroundColor(.white)

                Text("Accept this mission to replace daily quests with focused training.")
                    .font(.system(size: 14))
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
            }

            // Mission Preview
            VStack(spacing: 16) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Goal")
                            .font(.system(size: 12))
                            .foregroundColor(.textSecondary)

                        Text("\(mission.goalExerciseName) \(Int(mission.goalTargetWeight)) \(mission.goalWeightUnit)")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)
                    }

                    Spacer()

                    VStack(alignment: .trailing, spacing: 4) {
                        Text("Reward")
                            .font(.system(size: 12))
                            .foregroundColor(.textSecondary)

                        HStack(spacing: 4) {
                            Text("⚡️")
                            Text("+\(mission.xpReward) XP")
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundColor(.gold)
                        }
                    }
                }

                Divider().background(Color.white.opacity(0.1))

                HStack {
                    ForEach(mission.workouts.indices, id: \.self) { index in
                        let workout = mission.workouts[index]
                        VStack(spacing: 6) {
                            Text("Day \(workout.dayNumber)")
                                .font(.system(size: 10, weight: .medium))
                                .foregroundColor(.textSecondary)

                            Text(workout.focus.split(separator: " ").first.map(String.init) ?? workout.focus)
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(.white)
                                .lineLimit(1)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Color.systemPrimary.opacity(0.1))
                        .cornerRadius(8)
                    }
                }
            }
            .padding(20)
            .background(Color.bgCard)
            .cornerRadius(16)

            Spacer()

            // Action Buttons
            VStack(spacing: 12) {
                Button(action: {
                    onAccept()
                    dismiss()
                }) {
                    HStack {
                        Text("Accept Mission")
                        Image(systemName: "arrow.right")
                    }
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.black)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(
                        LinearGradient(
                            colors: [Color.systemPrimary, Color(hex: "00FF88")],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .cornerRadius(14)
                }

                Button(action: {
                    onDecline()
                    dismiss()
                }) {
                    Text("Not Now")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(.textSecondary)
                }
            }
        }
        .padding(20)
        .background(Color.bgVoid)
    }
}

#Preview {
    MissionDetailView(missionId: "test")
}
