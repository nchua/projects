import SwiftUI

/// Dashboard card shown on Home tab — weekly progress + Start Workout CTA
struct DashboardCard: View {
    let workouts: Int
    let workoutsGoal: Int
    let totalVolume: Double
    let activeMinutes: Int
    let prsCount: Int

    private var progressPercent: Int {
        guard workoutsGoal > 0 else { return 0 }
        return min(100, Int(Double(workouts) / Double(workoutsGoal) * 100))
    }

    private var progressFraction: Double {
        guard workoutsGoal > 0 else { return 0 }
        return min(Double(workouts) / Double(workoutsGoal), 1.0)
    }

    private var isEmpty: Bool {
        workouts == 0 && totalVolume == 0
    }

    var body: some View {
        VStack(spacing: 16) {
            if isEmpty {
                emptyState
            } else {
                activeState
            }

            // Full-width Start Workout CTA
            ctaRow
        }
        .padding(20)
        .background(Color.voidMedium)
        .cornerRadius(20)
        .overlay(
            RoundedRectangle(cornerRadius: 20)
                .stroke(Color.glassBorder, lineWidth: 1)
        )
    }

    // MARK: - Active State

    private var activeState: some View {
        VStack(spacing: 14) {
            // Weekly workout count with progress
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("This Week")
                        .font(.system(size: 12))
                        .foregroundColor(.textSecondary)

                    HStack(alignment: .lastTextBaseline, spacing: 6) {
                        Text("\(workouts)")
                            .font(.system(size: 28, weight: .bold))
                            .foregroundColor(.systemPrimary)

                        Text("of \(workoutsGoal) workouts")
                            .font(.system(size: 14))
                            .foregroundColor(.textSecondary)
                    }
                }

                Spacer()

                // Percentage badge
                Text("\(progressPercent)%")
                    .font(.system(size: 14, weight: .bold, design: .monospaced))
                    .foregroundColor(progressPercent >= 100 ? .successGreen : .systemPrimary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(
                        (progressPercent >= 100 ? Color.successGreen : Color.systemPrimary)
                            .opacity(0.12)
                    )
                    .clipShape(Capsule())
            }

            // Progress bar
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.white.opacity(0.08))

                    RoundedRectangle(cornerRadius: 4)
                        .fill(
                            progressPercent >= 100
                                ? LinearGradient(colors: [Color.successGreen, Color(hex: "00CC6A")], startPoint: .leading, endPoint: .trailing)
                                : LinearGradient(colors: [Color.systemPrimary, Color(hex: "7B61FF")], startPoint: .leading, endPoint: .trailing)
                        )
                        .frame(width: geometry.size.width * CGFloat(progressFraction))
                }
            }
            .frame(height: 6)

            // Supporting stats row
            HStack(spacing: 0) {
                DashboardStatPill(icon: "dumbbell.fill", value: totalVolume.formattedVolume, label: "Volume")
                Spacer()
                DashboardStatPill(icon: "timer", value: "\(activeMinutes)", label: "Minutes")
                Spacer()
                DashboardStatPill(icon: "trophy.fill", value: "\(prsCount)", label: "PRs")
            }
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "target")
                .font(.system(size: 28))
                .foregroundColor(.textMuted)

            Text("No workouts this week")
                .font(.system(size: 15, weight: .medium))
                .foregroundColor(.textSecondary)

            Text("Start a workout to begin tracking")
                .font(.system(size: 12))
                .foregroundColor(.textMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
    }

    // MARK: - CTA Row

    private var ctaRow: some View {
        HStack(spacing: 10) {
            // Start Workout — primary CTA
            NavigationLink(destination: LogView()) {
                HStack(spacing: 8) {
                    Image(systemName: "bolt.fill")
                        .font(.system(size: 14))
                    Text("Start Workout")
                        .font(.system(size: 15, weight: .semibold))
                }
                .foregroundColor(.black)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(
                    LinearGradient(
                        colors: [Color(hex: "00D4FF"), Color(hex: "0099CC")],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .shadow(color: Color.systemPrimary.opacity(0.3), radius: 8, x: 0, y: 4)
            }

            // Scan — secondary icon
            NavigationLink(destination: LogView()) {
                Image(systemName: "camera.viewfinder")
                    .font(.system(size: 18, weight: .medium))
                    .foregroundColor(.systemPrimary)
                    .frame(width: 48, height: 48)
                    .background(Color.voidLight)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                    .overlay(
                        RoundedRectangle(cornerRadius: 14)
                            .stroke(Color.glassBorder, lineWidth: 1)
                    )
            }
        }
    }
}

// MARK: - Dashboard Stat Pill

private struct DashboardStatPill: View {
    let icon: String
    let value: String
    let label: String

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 12))
                .foregroundColor(.textMuted)

            VStack(alignment: .leading, spacing: 1) {
                Text(value)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.textPrimary)
                Text(label)
                    .font(.system(size: 10))
                    .foregroundColor(.textMuted)
            }
        }
    }
}
