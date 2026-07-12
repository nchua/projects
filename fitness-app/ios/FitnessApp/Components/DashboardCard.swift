import SwiftUI

/// "This Week" card on the Status tab — weekly progress, BEGIN HUNT + SCAN
/// CTAs, and the Weekly Report link row (absorbed from the old
/// WeeklyReportCard per ARISE v2 spec §8.1-5).
struct DashboardCard: View {
    let workouts: Int
    let workoutsGoal: Int
    let totalVolume: Double
    let activeMinutes: Int
    let prsCount: Int
    /// "on_track" | "ahead" | "behind" — nil hides the Weekly Report row.
    var weeklyReportStatus: String? = nil
    var onWeeklyReportTap: (() -> Void)? = nil

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

            // Full-width BEGIN HUNT CTA
            ctaRow

            // Weekly Report link row (absorbed WeeklyReportCard)
            if weeklyReportStatus != nil {
                weeklyReportRow
            }
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
                        .font(.ariseMono(size: 12))
                        .foregroundColor(.textSecondary)

                    HStack(alignment: .lastTextBaseline, spacing: 6) {
                        Text("\(workouts)")
                            .font(.ariseDisplay(size: 28, weight: .bold))
                            .foregroundColor(.systemPrimary)

                        Text("of \(workoutsGoal) workouts")
                            .font(.system(size: 14))
                            .foregroundColor(.textSecondary)
                    }
                }

                Spacer()

                // Percentage badge
                Text("\(progressPercent)%")
                    .font(.ariseMono(size: 14, weight: .bold))
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
            // BEGIN HUNT — primary CTA
            NavigationLink(destination: LogView()) {
                HStack(spacing: 8) {
                    Image(systemName: "bolt.fill")
                        .font(.system(size: 14))
                    Text("BEGIN HUNT")
                        .font(.ariseHeader(size: 15, weight: .semibold))
                        .tracking(1)
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

            // SCAN — secondary
            NavigationLink(destination: LogView()) {
                HStack(spacing: 6) {
                    Image(systemName: "camera.viewfinder")
                        .font(.system(size: 15, weight: .medium))
                    Text("SCAN")
                        .font(.ariseMono(size: 12, weight: .semibold))
                        .tracking(1)
                }
                .foregroundColor(.systemPrimary)
                .padding(.horizontal, 16)
                .frame(height: 48)
                .background(Color.voidLight)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(Color.glassBorder, lineWidth: 1)
                )
            }
        }
    }

    // MARK: - Weekly Report Row

    private var statusLabel: String {
        switch weeklyReportStatus {
        case "ahead": return "AHEAD"
        case "behind": return "BEHIND"
        default: return "ON TRACK"
        }
    }

    private var statusColor: Color {
        switch weeklyReportStatus {
        case "ahead": return .gold
        case "behind": return .warningRed
        default: return .systemPrimary
        }
    }

    private var weeklyReportRow: some View {
        Button {
            onWeeklyReportTap?()
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.system(size: 13))
                    .foregroundColor(.systemPrimary)

                Text("Weekly Report")
                    .font(.ariseMono(size: 12, weight: .medium))
                    .foregroundColor(.textSecondary)

                Spacer()

                Text(statusLabel)
                    .font(.ariseMono(size: 9, weight: .bold))
                    .foregroundColor(statusColor)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(statusColor.opacity(0.15))
                    .clipShape(Capsule())

                Image(systemName: "chevron.right")
                    .font(.system(size: 11))
                    .foregroundColor(.textMuted)
            }
            .padding(.top, 2)
        }
        .buttonStyle(PlainButtonStyle())
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
                    .font(.ariseMono(size: 10))
                    .foregroundColor(.textMuted)
            }
        }
    }
}
