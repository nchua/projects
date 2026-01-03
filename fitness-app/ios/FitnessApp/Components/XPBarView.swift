import SwiftUI

/// ARISE XP bar with centered text and shimmer animation
struct XPBarView: View {
    let current: Int
    let toNextLevel: Int
    let progress: Double
    var showText: Bool = true
    var height: CGFloat = 20

    // Legacy initializer for backwards compatibility
    init(current: Int, max: Int, showText: Bool = true, height: CGFloat = 20) {
        self.current = current
        self.toNextLevel = max - current
        self.progress = max > 0 ? Double(current) / Double(max) : 0
        self.showText = showText
        self.height = height
    }

    // New initializer with explicit progress
    init(current: Int, toNextLevel: Int, progress: Double, showText: Bool = true, height: CGFloat = 20) {
        self.current = current
        self.toNextLevel = toNextLevel
        self.progress = progress
        self.showText = showText
        self.height = height
    }

    var clampedProgress: CGFloat {
        CGFloat(min(max(progress, 0), 1))
    }

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                // Background
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.voidLight)

                // Fill with gradient and shimmer
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.gradientXP)
                    .frame(width: geo.size.width * clampedProgress)
                    .shimmer()

                // Centered text showing XP to next level
                if showText {
                    Text("\(toNextLevel) XP to next level")
                        .font(.ariseMono(size: 12, weight: .medium))
                        .foregroundColor(.textPrimary)
                        .shadow(color: .black.opacity(0.5), radius: 2, x: 0, y: 1)
                        .frame(maxWidth: .infinity)
                }
            }
            .overlay(
                RoundedRectangle(cornerRadius: 2)
                    .stroke(Color.systemPrimary.opacity(0.3), lineWidth: 1)
            )
        }
        .frame(height: height)
    }
}

/// ARISE progress bar (simpler version without text)
struct AriseProgressBar: View {
    let progress: Double // 0.0 to 1.0
    var color: Color = .systemPrimary
    var height: CGFloat = 8
    var showShimmer: Bool = true

    var clampedProgress: CGFloat {
        CGFloat(min(max(progress, 0), 1))
    }

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                // Background
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.voidLight)

                // Fill
                RoundedRectangle(cornerRadius: 2)
                    .fill(
                        LinearGradient(
                            colors: [color.opacity(0.7), color],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .frame(width: geo.size.width * clampedProgress)
                    .if(showShimmer) { view in
                        view.shimmer()
                    }
            }
        }
        .frame(height: height)
    }
}

/// Quest progress bar (thicker, with percentage)
struct QuestProgressBar: View {
    let current: Int
    let target: Int
    var color: Color = .systemPrimary
    var label: String? = nil

    var progress: Double {
        guard target > 0 else { return 0 }
        return Double(current) / Double(target)
    }

    var isComplete: Bool {
        current >= target
    }

    var displayColor: Color {
        isComplete ? .successGreen : color
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let label = label {
                HStack {
                    Text(label)
                        .font(.ariseHeader(size: 13, weight: .medium))
                        .foregroundColor(.textSecondary)
                        .textCase(.uppercase)
                        .tracking(1)

                    Spacer()

                    Text("\(current)/\(target)")
                        .font(.ariseMono(size: 12, weight: .medium))
                        .foregroundColor(isComplete ? .successGreen : .textMuted)
                }
            }

            AriseProgressBar(
                progress: progress,
                color: displayColor,
                height: 12,
                showShimmer: !isComplete
            )

            if isComplete {
                HStack {
                    Spacer()
                    Text("\u{2713} COMPLETE")
                        .font(.ariseMono(size: 10, weight: .semibold))
                        .foregroundColor(.successGreen)
                        .tracking(1)
                }
            }
        }
    }
}

/// Day tracker circles (for weekly view)
struct DayTrackerView: View {
    let days: [DayStatus]

    enum DayStatus {
        case completed
        case current
        case upcoming
        case restDay

        var backgroundColor: Color {
            switch self {
            case .completed: return .successGreen
            case .current: return .clear
            case .upcoming: return .clear
            case .restDay: return .clear
            }
        }

        var borderColor: Color {
            switch self {
            case .completed: return .successGreen
            case .current: return .systemPrimary
            case .upcoming: return .textMuted
            case .restDay: return .textMuted
            }
        }

        var borderStyle: some ShapeStyle {
            borderColor
        }
    }

    var body: some View {
        HStack(spacing: 8) {
            ForEach(Array(days.enumerated()), id: \.offset) { index, status in
                DayCircle(day: index + 1, status: status)
            }
        }
    }
}

struct DayCircle: View {
    let day: Int
    let status: DayTrackerView.DayStatus

    var body: some View {
        ZStack {
            Circle()
                .fill(status.backgroundColor)
                .frame(width: 36, height: 36)
                .overlay(
                    Circle()
                        .stroke(
                            status.borderColor,
                            style: StrokeStyle(
                                lineWidth: status == .restDay ? 1 : 2,
                                dash: status == .restDay ? [4, 4] : []
                            )
                        )
                )
                .if(status == .current) { view in
                    view.shadow(color: .systemPrimaryGlow, radius: 8, x: 0, y: 0)
                }

            if status == .completed {
                Image(systemName: "checkmark")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(.voidBlack)
            } else {
                Text("\(day)")
                    .font(.ariseMono(size: 14, weight: .medium))
                    .foregroundColor(status == .current ? .systemPrimary : .textMuted)
            }
        }
    }
}

#Preview {
    ZStack {
        VoidBackground()

        VStack(spacing: 32) {
            // XP Bar
            VStack(alignment: .leading, spacing: 8) {
                Text("Experience")
                    .font(.ariseHeader(size: 12))
                    .foregroundColor(.textMuted)

                XPBarView(current: 1250, max: 2000)
            }

            // Simple progress bar
            VStack(alignment: .leading, spacing: 8) {
                Text("Progress")
                    .font(.ariseHeader(size: 12))
                    .foregroundColor(.textMuted)

                AriseProgressBar(progress: 0.65)
            }

            // Quest progress
            QuestProgressBar(current: 8, target: 10, label: "Squat Sets")

            QuestProgressBar(current: 10, target: 10, label: "Bench Sets")

            // Day tracker
            VStack(alignment: .leading, spacing: 8) {
                Text("This Week")
                    .font(.ariseHeader(size: 12))
                    .foregroundColor(.textMuted)

                DayTrackerView(days: [
                    .completed,
                    .completed,
                    .restDay,
                    .completed,
                    .current,
                    .upcoming,
                    .restDay
                ])
            }
        }
        .padding(24)
    }
}
