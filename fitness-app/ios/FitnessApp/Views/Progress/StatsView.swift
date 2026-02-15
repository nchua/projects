import SwiftUI
import Charts

struct StatsView: View {
    @StateObject private var viewModel = ProgressViewModel()
    @State private var selectedTab = 0

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                if viewModel.isLoading {
                    VStack(spacing: 16) {
                        SwiftUI.ProgressView()
                            .tint(.systemPrimary)
                        Text("ANALYZING...")
                            .font(.ariseMono(size: 12, weight: .medium))
                            .foregroundColor(.textMuted)
                            .tracking(2)
                    }
                } else {
                    ScrollView {
                        VStack(spacing: 24) {
                            // Header
                            PowerAnalysisHeader()

                            // Tab Selector
                            HStack(spacing: 8) {
                                ForEach(["Power", "Vessel", "Records"], id: \.self) { tab in
                                    let index = ["Power", "Vessel", "Records"].firstIndex(of: tab) ?? 0
                                    Button {
                                        withAnimation(.quickSpring) {
                                            selectedTab = index
                                        }
                                    } label: {
                                        Text(tab.uppercased())
                                            .font(.ariseMono(size: 11, weight: .semibold))
                                            .tracking(1)
                                            .foregroundColor(selectedTab == index ? .voidBlack : .textSecondary)
                                            .padding(.horizontal, 20)
                                            .padding(.vertical, 10)
                                            .background(selectedTab == index ? Color.systemPrimary : Color.voidMedium)
                                            .cornerRadius(4)
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 4)
                                                    .stroke(selectedTab == index ? Color.systemPrimary : Color.ariseBorder, lineWidth: 1)
                                            )
                                            .shadow(color: selectedTab == index ? Color.systemPrimaryGlow : .clear, radius: 8, x: 0, y: 0)
                                    }
                                }
                            }
                            .padding(.horizontal)

                            switch selectedTab {
                            case 0:
                                PowerProgressView(viewModel: viewModel)
                            case 1:
                                VesselProgressView(viewModel: viewModel)
                            case 2:
                                RecordsView(viewModel: viewModel)
                            default:
                                EmptyView()
                            }
                        }
                        .padding(.vertical)
                    }
                }
            }
            .navigationBarHidden(true)
            .refreshable {
                await viewModel.loadInitialData()
            }
        }
        .task {
            await viewModel.loadInitialData()
        }
        .alert("System Error", isPresented: .constant(viewModel.error != nil)) {
            Button("DISMISS") { viewModel.error = nil }
        } message: {
            Text(viewModel.error ?? "")
        }
    }
}

// MARK: - Header

struct PowerAnalysisHeader: View {
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("[ SYSTEM ]")
                    .font(.ariseMono(size: 11, weight: .medium))
                    .foregroundColor(.systemPrimary)
                    .tracking(2)

                Text("Power Analysis")
                    .font(.ariseHeader(size: 24, weight: .bold))
                    .foregroundColor(.textPrimary)
            }

            Spacer()
        }
        .padding(.horizontal)
    }
}

// MARK: - Power Progress (Strength)

struct PowerProgressView: View {
    @ObservedObject var viewModel: ProgressViewModel
    @State private var showAddExercise = false

    var body: some View {
        VStack(spacing: 20) {
            // Time Range Selector
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(viewModel.timeRanges, id: \.self) { range in
                        AriseTimeRangeButton(
                            range: range,
                            isSelected: viewModel.selectedTimeRange == range
                        ) {
                            viewModel.selectTimeRange(range)
                        }
                    }
                }
                .padding(.horizontal)
            }

            // Big Three Section Header
            HStack {
                HStack(spacing: 8) {
                    Image(systemName: "diamond.fill")
                        .font(.system(size: 8))
                        .foregroundColor(.systemPrimary)
                    Text("THE BIG THREE")
                        .font(.ariseMono(size: 11, weight: .semibold))
                        .foregroundColor(.textMuted)
                        .tracking(2)
                }
                Spacer()
            }
            .padding(.horizontal)

            // Big Three Cards - Now with NavigationLink
            ForEach(viewModel.bigThreeExercises) { exercise in
                NavigationLink {
                    ExerciseDetailView(
                        exercise: exercise,
                        viewModel: viewModel
                    )
                } label: {
                    MinimalExerciseCard(
                        exercise: exercise,
                        trend: viewModel.trend(for: exercise.id),
                        percentile: viewModel.percentile(for: exercise.id),
                        isCompact: false
                    )
                }
                .buttonStyle(PlainButtonStyle())
                .padding(.horizontal)
            }

            // Show message if Big Three not found
            if viewModel.bigThreeExercises.isEmpty && !viewModel.isLoading {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 24))
                        .foregroundColor(.gold)
                    Text("Complete quests with Squat, Bench, and Deadlift to see your Big Three stats.")
                        .font(.ariseMono(size: 12))
                        .foregroundColor(.textSecondary)
                        .multilineTextAlignment(.center)
                }
                .padding(20)
                .frame(maxWidth: .infinity)
                .background(Color.voidMedium)
                .cornerRadius(16)
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(Color.ariseBorder, lineWidth: 1)
                )
                .padding(.horizontal)
            }

            // Additional Exercises Section
            if !viewModel.additionalExercises.isEmpty {
                // Section divider
                HStack(spacing: 12) {
                    Rectangle()
                        .fill(Color.ariseBorder)
                        .frame(height: 1)
                    Text("ADDITIONAL SKILLS")
                        .font(.ariseMono(size: 10, weight: .semibold))
                        .foregroundColor(.textMuted)
                        .tracking(1.5)
                    Rectangle()
                        .fill(Color.ariseBorder)
                        .frame(height: 1)
                }
                .padding(.horizontal)
                .padding(.top, 8)

                ForEach(viewModel.additionalExercises) { exercise in
                    NavigationLink {
                        ExerciseDetailView(
                            exercise: exercise,
                            viewModel: viewModel
                        )
                    } label: {
                        MinimalExerciseCard(
                            exercise: exercise,
                            trend: viewModel.trend(for: exercise.id),
                            percentile: viewModel.percentile(for: exercise.id),
                            isCompact: true,
                            onRemove: {
                                withAnimation(.quickSpring) {
                                    viewModel.removeExercise(exercise.id)
                                }
                            }
                        )
                    }
                    .buttonStyle(PlainButtonStyle())
                    .padding(.horizontal)
                }
            }

            // Add Exercise Button
            Button {
                showAddExercise = true
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "plus.circle.fill")
                        .font(.system(size: 16))
                    Text("ADD SKILL")
                        .font(.ariseMono(size: 12, weight: .semibold))
                        .tracking(1)
                }
                .foregroundColor(.systemPrimary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(Color.clear)
                .cornerRadius(12)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(Color.systemPrimary.opacity(0.3), style: StrokeStyle(lineWidth: 1, dash: [6, 4]))
                )
            }
            .padding(.horizontal)
        }
        .sheet(isPresented: $showAddExercise) {
            AddSkillSheet(
                exercises: viewModel.availableExercises
            ) { exercise in
                viewModel.addExercise(exercise)
                showAddExercise = false
            }
        }
    }
}

// MARK: - Add Skill Sheet

struct AddSkillSheet: View {
    let exercises: [ExerciseResponse]
    let onSelect: (ExerciseResponse) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var searchText = ""

    var filteredExercises: [ExerciseResponse] {
        if searchText.isEmpty {
            return exercises
        }
        return exercises.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                VStack(spacing: 0) {
                    // Search Bar
                    HStack(spacing: 12) {
                        Image(systemName: "magnifyingglass")
                            .foregroundColor(.textMuted)

                        TextField("Search skills...", text: $searchText)
                            .font(.ariseMono(size: 14))
                            .foregroundColor(.textPrimary)

                        if !searchText.isEmpty {
                            Button {
                                searchText = ""
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

                    if filteredExercises.isEmpty {
                        VStack(spacing: 12) {
                            Image(systemName: "magnifyingglass")
                                .font(.system(size: 32))
                                .foregroundColor(.textMuted)
                            Text("No skills found")
                                .font(.ariseMono(size: 14))
                                .foregroundColor(.textSecondary)
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
                        List {
                            ForEach(filteredExercises) { exercise in
                                Button {
                                    onSelect(exercise)
                                } label: {
                                    HStack(spacing: 0) {
                                        Rectangle()
                                            .fill(Color.exerciseColor(for: exercise.name))
                                            .frame(width: 4, height: 40)

                                        HStack(spacing: 12) {
                                            VStack(alignment: .leading, spacing: 2) {
                                                Text(exercise.name)
                                                    .font(.ariseHeader(size: 14, weight: .medium))
                                                    .foregroundColor(.textPrimary)

                                                Text("\"\(ExerciseFantasyNames.fantasyName(for: exercise.name))\"")
                                                    .font(.ariseMono(size: 10))
                                                    .foregroundColor(.textMuted)
                                                    .italic()
                                            }

                                            Spacer()

                                            Image(systemName: "plus.circle")
                                                .foregroundColor(.systemPrimary)
                                        }
                                        .padding(.horizontal, 12)
                                    }
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
            .navigationTitle("Add Skill")
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
    }
}

struct AriseTimeRangeButton: View {
    let range: String
    let isSelected: Bool
    let action: () -> Void

    var label: String {
        switch range {
        case "4w": return "4W"
        case "8w": return "8W"
        case "12w": return "12W"
        case "26w": return "6M"
        case "52w": return "1Y"
        default: return range
        }
    }

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.ariseMono(size: 12, weight: .semibold))
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

// MARK: - Mini Sparkline

struct MiniSparkline: View {
    let dataPoints: [DataPoint]
    let color: Color
    var width: CGFloat = 100
    var height: CGFloat = 32

    var body: some View {
        GeometryReader { geometry in
            if dataPoints.count >= 2 {
                let values = dataPoints.map { $0.value }
                let minValue = values.min() ?? 0
                let maxValue = values.max() ?? 1
                let valueRange = max(maxValue - minValue, 1)

                ZStack {
                    // Area fill
                    Path { path in
                        let stepX = geometry.size.width / CGFloat(dataPoints.count - 1)

                        path.move(to: CGPoint(x: 0, y: geometry.size.height))

                        for (index, point) in dataPoints.enumerated() {
                            let x = CGFloat(index) * stepX
                            let normalizedY = (point.value - minValue) / valueRange
                            let y = geometry.size.height - (normalizedY * geometry.size.height * 0.8) - geometry.size.height * 0.1
                            path.addLine(to: CGPoint(x: x, y: y))
                        }

                        path.addLine(to: CGPoint(x: geometry.size.width, y: geometry.size.height))
                        path.closeSubpath()
                    }
                    .fill(
                        LinearGradient(
                            colors: [color.opacity(0.3), color.opacity(0)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )

                    // Line
                    Path { path in
                        let stepX = geometry.size.width / CGFloat(dataPoints.count - 1)

                        for (index, point) in dataPoints.enumerated() {
                            let x = CGFloat(index) * stepX
                            let normalizedY = (point.value - minValue) / valueRange
                            let y = geometry.size.height - (normalizedY * geometry.size.height * 0.8) - geometry.size.height * 0.1

                            if index == 0 {
                                path.move(to: CGPoint(x: x, y: y))
                            } else {
                                path.addLine(to: CGPoint(x: x, y: y))
                            }
                        }
                    }
                    .stroke(color, style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
                }
            } else {
                // Not enough data - show flat line
                Path { path in
                    path.move(to: CGPoint(x: 0, y: geometry.size.height / 2))
                    path.addLine(to: CGPoint(x: geometry.size.width, y: geometry.size.height / 2))
                }
                .stroke(color.opacity(0.3), lineWidth: 1)
            }
        }
        .frame(width: width, height: height)
    }
}

// MARK: - Minimal Exercise Card

struct MinimalExerciseCard: View {
    let exercise: ExerciseResponse
    let trend: TrendResponse?
    let percentile: ExercisePercentile?
    var isCompact: Bool = false
    var onRemove: (() -> Void)? = nil

    var exerciseColor: Color {
        Color.exerciseColor(for: exercise.name)
    }

    var rank: HunterRank {
        guard let classification = percentile?.classification.lowercased() else { return .e }
        switch classification {
        case "elite": return .s
        case "advanced": return .a
        case "intermediate": return .c
        case "novice": return .d
        default: return .e
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Top color bar
            Rectangle()
                .fill(exerciseColor)
                .frame(height: 3)

            VStack(spacing: isCompact ? 12 : 16) {
                // Main row
                HStack(spacing: isCompact ? 12 : 16) {
                    // Left: Name + Sparkline
                    VStack(alignment: .leading, spacing: isCompact ? 8 : 12) {
                        // Name group
                        VStack(alignment: .leading, spacing: 4) {
                            Text(exercise.name)
                                .font(.ariseHeader(size: isCompact ? 14 : 18, weight: .semibold))
                                .foregroundColor(.textPrimary)

                            Text("\"\(ExerciseFantasyNames.fantasyName(for: exercise.name))\"")
                                .font(.ariseMono(size: isCompact ? 9 : 11))
                                .foregroundColor(.textMuted)
                                .italic()
                        }

                        // Sparkline
                        if let dataPoints = trend?.dataPoints, !dataPoints.isEmpty {
                            MiniSparkline(
                                dataPoints: dataPoints,
                                color: exerciseColor,
                                width: isCompact ? 60 : 100,
                                height: isCompact ? 24 : 32
                            )
                        }
                    }

                    Spacer()

                    // Right: e1RM + Trend
                    VStack(alignment: .trailing, spacing: 8) {
                        if let current = trend?.currentE1rm {
                            HStack(alignment: .lastTextBaseline, spacing: 4) {
                                Text(current.formattedWeight)
                                    .font(.ariseDisplay(size: isCompact ? 24 : 36, weight: .bold))
                                    .foregroundColor(exerciseColor)

                                Text("lb")
                                    .font(.ariseMono(size: isCompact ? 10 : 12))
                                    .foregroundColor(.textMuted)
                            }

                            // Trend badge
                            if let direction = trend?.trendDirection, direction != "insufficient_data" {
                                HStack(spacing: 4) {
                                    Image(systemName: trendIcon(direction))
                                        .font(.system(size: isCompact ? 9 : 10, weight: .bold))
                                    if let percent = trend?.percentChange {
                                        Text("\(abs(percent), specifier: "%.1f")%")
                                            .font(.ariseMono(size: isCompact ? 10 : 11, weight: .semibold))
                                    }
                                }
                                .foregroundColor(trendColor(direction))
                                .padding(.horizontal, 10)
                                .padding(.vertical, 4)
                                .background(trendColor(direction).opacity(0.1))
                                .cornerRadius(12)
                            }
                        } else {
                            Text("No data")
                                .font(.ariseMono(size: 12))
                                .foregroundColor(.textMuted)
                        }
                    }
                }

                // Bottom row
                HStack(spacing: 8) {
                    // Rank pill
                    if let p = percentile?.percentile {
                        HStack(spacing: 8) {
                            Text(rank.rawValue)
                                .font(.ariseMono(size: 12, weight: .bold))
                                .foregroundColor(.voidBlack)
                                .frame(width: 24, height: 24)
                                .background(rank.color)
                                .cornerRadius(4)

                            Text("Top \(100 - p)%")
                                .font(.ariseMono(size: 11))
                                .foregroundColor(.textSecondary)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.voidLight)
                        .cornerRadius(8)
                    }

                    Spacer()

                    // Stat pills (only on non-compact)
                    if !isCompact {
                        if let total = trend?.totalWorkouts {
                            StatPill(value: "\(total)", label: "QUESTS")
                        }

                        if let multiplier = percentile?.bodyweightMultiplier {
                            StatPill(value: String(format: "%.1fx", multiplier), label: "BW")
                        }
                    }

                    // Remove button for additional skills
                    if let onRemove = onRemove {
                        Button(action: onRemove) {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 20))
                                .foregroundColor(.textMuted)
                        }
                    }

                    // Navigation arrow
                    Circle()
                        .fill(Color.voidLight)
                        .frame(width: 28, height: 28)
                        .overlay(
                            Image(systemName: "arrow.right")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(.textSecondary)
                        )
                }
            }
            .padding(isCompact ? 14 : 20)
        }
        .background(Color.voidMedium)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }

    private func trendIcon(_ direction: String) -> String {
        switch direction {
        case "improving": return "arrow.up.right"
        case "regressing": return "arrow.down.right"
        default: return "arrow.right"
        }
    }

    private func trendColor(_ direction: String) -> Color {
        switch direction {
        case "improving": return .successGreen
        case "regressing": return .warningRed
        default: return .textSecondary
        }
    }
}

// MARK: - Stat Pill

struct StatPill: View {
    let value: String
    let label: String

    var body: some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.ariseMono(size: 12, weight: .semibold))
                .foregroundColor(.textPrimary)
            Text(label)
                .font(.ariseMono(size: 8))
                .foregroundColor(.textMuted)
                .tracking(0.5)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Color.voidLight)
        .cornerRadius(8)
    }
}

// MARK: - Exercise Detail View

struct ExerciseDetailView: View {
    let exercise: ExerciseResponse
    @ObservedObject var viewModel: ProgressViewModel
    @StateObject private var historyViewModel = HistoryViewModel()
    @Environment(\.dismiss) private var dismiss
    @State private var selectedWorkoutId: String?

    var exerciseColor: Color {
        Color.exerciseColor(for: exercise.name)
    }

    var trend: TrendResponse? {
        viewModel.trend(for: exercise.id)
    }

    var percentile: ExercisePercentile? {
        viewModel.percentile(for: exercise.id)
    }

    var rank: HunterRank {
        guard let classification = percentile?.classification.lowercased() else { return .e }
        switch classification {
        case "elite": return .s
        case "advanced": return .a
        case "intermediate": return .c
        case "novice": return .d
        default: return .e
        }
    }

    var body: some View {
        ZStack {
            VoidBackground(showGrid: false, glowIntensity: 0.03)

            ScrollView {
                VStack(spacing: 0) {
                    headerSection
                    timeRangeSection
                    chartSection
                    rankSection
                    sessionsSection
                }
            }
        }
        .navigationBarHidden(true)
        .navigationDestination(item: $selectedWorkoutId) { workoutId in
            QuestDetailView(
                workoutId: workoutId,
                viewModel: historyViewModel
            )
        }
    }

    // MARK: - Header Section

    @ViewBuilder
    private var headerSection: some View {
        VStack(spacing: 0) {
            Rectangle()
                .fill(exerciseColor)
                .frame(height: 3)

            VStack(alignment: .leading, spacing: 16) {
                backButton
                titleRow
            }
            .padding(20)
            .background(headerGradient)
        }
    }

    @ViewBuilder
    private var backButton: some View {
        Button {
            dismiss()
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "arrow.left")
                    .font(.system(size: 14, weight: .semibold))
                Text("Power Analysis")
                    .font(.ariseMono(size: 12))
            }
            .foregroundColor(.systemPrimary)
        }
    }

    @ViewBuilder
    private var titleRow: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text(exercise.name)
                    .font(.ariseHeader(size: 24, weight: .bold))
                    .foregroundColor(.textPrimary)

                Text("\"\(ExerciseFantasyNames.fantasyName(for: exercise.name))\"")
                    .font(.ariseMono(size: 12))
                    .foregroundColor(.textMuted)
                    .italic()
            }

            Spacer()

            heroE1RMView
        }
    }

    @ViewBuilder
    private var heroE1RMView: some View {
        VStack(alignment: .trailing, spacing: 4) {
            if let current = trend?.currentE1rm {
                Text(current.formattedWeight)
                    .font(.ariseDisplay(size: 48, weight: .bold))
                    .foregroundColor(exerciseColor)

                Text("CURRENT E1RM (LB)")
                    .font(.ariseMono(size: 10))
                    .foregroundColor(.textMuted)
                    .tracking(1)

                trendBadge
            }
        }
    }

    @ViewBuilder
    private var trendBadge: some View {
        if let direction = trend?.trendDirection, direction != "insufficient_data" {
            HStack(spacing: 4) {
                Image(systemName: trendIcon(direction))
                    .font(.system(size: 10, weight: .bold))
                if let percent = trend?.percentChange {
                    Text("\(abs(percent), specifier: "%.1f")% vs \(viewModel.timeRangeLabel)")
                        .font(.ariseMono(size: 11, weight: .semibold))
                }
            }
            .foregroundColor(trendColor(direction))
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(trendColor(direction).opacity(0.1))
            .cornerRadius(12)
        }
    }

    private var headerGradient: some View {
        LinearGradient(
            colors: [Color.voidLight, Color.voidBlack.opacity(0)],
            startPoint: .top,
            endPoint: .bottom
        )
    }

    // MARK: - Time Range Section

    @ViewBuilder
    private var timeRangeSection: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(viewModel.timeRanges, id: \.self) { range in
                    AriseTimeRangeButton(
                        range: range,
                        isSelected: viewModel.selectedTimeRange == range
                    ) {
                        viewModel.selectTimeRange(range)
                    }
                }
            }
            .padding(.horizontal, 20)
        }
        .padding(.vertical, 16)
    }

    // MARK: - Chart Section

    @ViewBuilder
    private var chartSection: some View {
        VStack(spacing: 0) {
            chartContent
            statsGrid
        }
        .background(Color.voidMedium)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .padding(.horizontal, 20)
    }

    @ViewBuilder
    private var chartContent: some View {
        if let dataPoints = trend?.dataPoints, !dataPoints.isEmpty {
            AriseE1RMChart(dataPoints: dataPoints, onWorkoutSelected: { workoutId in
                selectedWorkoutId = workoutId
            })
            .frame(height: 200)
            .padding(20)
        } else {
            Text("Not enough data to show chart")
                .font(.ariseMono(size: 12))
                .foregroundColor(.textMuted)
                .frame(height: 200)
                .frame(maxWidth: .infinity)
        }
    }

    @ViewBuilder
    private var statsGrid: some View {
        let columns = [GridItem(.flexible()), GridItem(.flexible())]
        LazyVGrid(columns: columns, spacing: 1) {
            DetailStatCell(
                value: trend?.totalWorkouts.description ?? "-",
                unit: nil,
                label: "TOTAL QUESTS"
            )
            DetailStatCell(
                value: trend?.rollingAverage4w?.formattedWeight ?? "-",
                unit: "lb",
                label: "4W AVERAGE"
            )
            DetailStatCell(
                value: vsLastPeriodValue,
                unit: "lb",
                label: "VS LAST PERIOD"
            )
            DetailStatCell(
                value: percentile?.currentE1rm?.formattedWeight ?? trend?.currentE1rm?.formattedWeight ?? "-",
                unit: "lb",
                label: "ALL-TIME BEST"
            )
        }
        .background(Color.ariseBorder)
    }

    private var vsLastPeriodValue: String {
        guard let percentChange = trend?.percentChange, let currentE1rm = trend?.currentE1rm else { return "-" }
        return String(format: "%+.0f", percentChange / 100 * currentE1rm)
    }

    // MARK: - Rank Section

    @ViewBuilder
    private var rankSection: some View {
        if let p = percentile?.percentile {
            ExerciseRankCard(
                rank: rank,
                percentile: p,
                bodyweight: viewModel.bodyweightHistory?.entries.first?.weightDisplay,
                bodyweightMultiplier: percentile?.bodyweightMultiplier,
                exerciseColor: exerciseColor
            )
            .padding(.horizontal, 20)
            .padding(.top, 20)
        }
    }

    // MARK: - Sessions Section

    @ViewBuilder
    private var sessionsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sessionsSectionHeader
            sessionsContent
        }
        .padding(20)
    }

    @ViewBuilder
    private var sessionsSectionHeader: some View {
        HStack {
            HStack(spacing: 8) {
                Rectangle()
                    .fill(Color.systemPrimary)
                    .frame(width: 6, height: 6)
                    .rotationEffect(.degrees(45))
                Text("RECENT SESSIONS")
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(1.5)
            }
            Spacer()
        }
    }

    @ViewBuilder
    private var sessionsContent: some View {
        if let dataPoints = trend?.dataPoints {
            let recentPoints = Array(dataPoints.suffix(5).reversed())
            let maxValue = dataPoints.map { $0.value }.max() ?? 0
            ForEach(Array(recentPoints.enumerated()), id: \.element.id) { index, point in
                SessionCard(
                    dataPoint: point,
                    color: exerciseColor,
                    isPR: index == 0 && point.value == maxValue
                ) {
                    if let workoutId = point.workoutId {
                        selectedWorkoutId = workoutId
                    }
                }
            }
        } else {
            Text("No recent sessions")
                .font(.ariseMono(size: 12))
                .foregroundColor(.textMuted)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 20)
        }
    }

    private func trendIcon(_ direction: String) -> String {
        switch direction {
        case "improving": return "arrow.up.right"
        case "regressing": return "arrow.down.right"
        default: return "arrow.right"
        }
    }

    private func trendColor(_ direction: String) -> Color {
        switch direction {
        case "improving": return .successGreen
        case "regressing": return .warningRed
        default: return .textSecondary
        }
    }
}

// MARK: - Exercise Rank Card

struct ExerciseRankCard: View {
    let rank: HunterRank
    let percentile: Int
    let bodyweight: Double?
    let bodyweightMultiplier: Double?
    let exerciseColor: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            rankHeader
            rankProgressBar
        }
        .padding(20)
        .background(cardGradient)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(exerciseColor.opacity(0.2), lineWidth: 1)
        )
    }

    @ViewBuilder
    private var rankHeader: some View {
        HStack(spacing: 16) {
            Text(rank.rawValue)
                .font(.ariseDisplay(size: 24, weight: .bold))
                .foregroundColor(.voidBlack)
                .frame(width: 56, height: 56)
                .background(rank.color)
                .cornerRadius(12)
                .shadow(color: rank.color.opacity(0.4), radius: 8, x: 0, y: 4)

            VStack(alignment: .leading, spacing: 4) {
                Text("\(rank.rawValue)-Rank Hunter")
                    .font(.ariseHeader(size: 18, weight: .semibold))
                    .foregroundColor(.textPrimary)

                rankSubtitle
            }

            Spacer()

            bwRatioView
        }
    }

    @ViewBuilder
    private var rankSubtitle: some View {
        if let bw = bodyweight {
            Text("Top \(100 - percentile)% of lifters at \(bw.formattedWeight) lb bodyweight")
                .font(.ariseMono(size: 12))
                .foregroundColor(.textSecondary)
        } else {
            Text("Top \(100 - percentile)% of lifters")
                .font(.ariseMono(size: 12))
                .foregroundColor(.textSecondary)
        }
    }

    @ViewBuilder
    private var bwRatioView: some View {
        if let multiplier = bodyweightMultiplier {
            VStack(alignment: .trailing, spacing: 2) {
                Text(String(format: "%.2fx", multiplier))
                    .font(.ariseDisplay(size: 24, weight: .bold))
                    .foregroundColor(.gold)
                Text("BW RATIO")
                    .font(.ariseMono(size: 10))
                    .foregroundColor(.textMuted)
            }
        }
    }

    @ViewBuilder
    private var rankProgressBar: some View {
        VStack(spacing: 8) {
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.voidLight.opacity(0.5))
                        .frame(height: 8)

                    RoundedRectangle(cornerRadius: 4)
                        .fill(progressGradient)
                        .frame(width: geometry.size.width * CGFloat(percentile) / 100, height: 8)
                        .shadow(color: .systemPrimary.opacity(0.5), radius: 4, x: 0, y: 0)
                }
            }
            .frame(height: 8)

            rankLabels
        }
    }

    private var progressGradient: LinearGradient {
        LinearGradient(
            colors: [.systemPrimary, .liftDeadlift],
            startPoint: .leading,
            endPoint: .trailing
        )
    }

    @ViewBuilder
    private var rankLabels: some View {
        HStack {
            ForEach(["E", "D", "C", "B", "A", "S"], id: \.self) { r in
                Text(r)
                    .font(.ariseMono(size: 9, weight: .medium))
                    .foregroundColor(r == rank.rawValue ? .systemPrimary : .textMuted)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(r == rank.rawValue ? Color.systemPrimary.opacity(0.15) : Color.clear)
                    .cornerRadius(4)
                if r != "S" { Spacer() }
            }
        }
    }

    private var cardGradient: some View {
        LinearGradient(
            colors: [exerciseColor.opacity(0.1), Color.voidMedium],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}

// MARK: - Detail Stat Cell

struct DetailStatCell: View {
    let value: String
    let unit: String?
    let label: String

    var body: some View {
        VStack(spacing: 4) {
            HStack(alignment: .lastTextBaseline, spacing: 4) {
                Text(value)
                    .font(.ariseDisplay(size: 22, weight: .bold))
                    .foregroundColor(.textPrimary)
                if let unit = unit {
                    Text(unit)
                        .font(.ariseMono(size: 11))
                        .foregroundColor(.textMuted)
                }
            }
            Text(label)
                .font(.ariseMono(size: 9))
                .foregroundColor(.textMuted)
                .tracking(0.5)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(Color.voidMedium)
    }
}

// MARK: - Session Card

struct SessionCard: View {
    let dataPoint: DataPoint
    let color: Color
    var isPR: Bool = false
    let onTap: () -> Void

    var formattedDate: (day: String, month: String)? {
        guard let date = dataPoint.date.parseISO8601Date() else { return nil }
        let dayFormatter = DateFormatter()
        dayFormatter.dateFormat = "d"
        let monthFormatter = DateFormatter()
        monthFormatter.dateFormat = "MMM"
        return (dayFormatter.string(from: date), monthFormatter.string(from: date).uppercased())
    }

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 12) {
                // Date
                if let formatted = formattedDate {
                    VStack(spacing: 0) {
                        Text(formatted.day)
                            .font(.ariseDisplay(size: 20, weight: .bold))
                            .foregroundColor(.textPrimary)
                        Text(formatted.month)
                            .font(.ariseMono(size: 10))
                            .foregroundColor(.textMuted)
                    }
                    .frame(width: 48)

                    Rectangle()
                        .fill(Color.ariseBorder)
                        .frame(width: 1, height: 36)
                }

                // Info
                VStack(alignment: .leading, spacing: 2) {
                    if let sets = dataPoint.sets {
                        Text("\(sets.count) sets")
                            .font(.ariseHeader(size: 14, weight: .medium))
                            .foregroundColor(.textPrimary)
                        let totalVolume = sets.reduce(0) { $0 + ($1.weight * Double($1.reps)) }
                        Text("\(totalVolume.formattedWeight) lb volume")
                            .font(.ariseMono(size: 11))
                            .foregroundColor(.textMuted)
                    } else {
                        Text("Workout")
                            .font(.ariseHeader(size: 14, weight: .medium))
                            .foregroundColor(.textPrimary)
                    }
                }

                Spacer()

                // e1RM
                VStack(alignment: .trailing, spacing: 2) {
                    Text(dataPoint.value.formattedWeight)
                        .font(.ariseDisplay(size: 18, weight: .bold))
                        .foregroundColor(color)
                    Text("E1RM")
                        .font(.ariseMono(size: 9))
                        .foregroundColor(.textMuted)

                    if isPR {
                        HStack(spacing: 4) {
                            Image(systemName: "star.fill")
                                .font(.system(size: 8))
                            Text("PR")
                                .font(.ariseMono(size: 9, weight: .semibold))
                        }
                        .foregroundColor(.gold)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(Color.gold.opacity(0.15))
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.gold.opacity(0.3), lineWidth: 1)
                        )
                        .cornerRadius(4)
                    }
                }

                Image(systemName: "arrow.right")
                    .font(.system(size: 14))
                    .foregroundColor(.textMuted)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .background(Color.voidMedium)
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
        }
        .buttonStyle(PlainButtonStyle())
    }
}

struct AriseE1RMChart: View {
    let dataPoints: [DataPoint]
    var onWorkoutSelected: ((String) -> Void)?  // Callback when user taps to view workout
    @State private var selectedDate: Date?
    @State private var longPressedPoint: DataPoint?
    @State private var isLongPressing = false

    private var selectedDataPoint: DataPoint? {
        guard let selectedDate = selectedDate else { return nil }
        // Find the closest data point to the selected date
        return dataPoints.min(by: { point1, point2 in
            abs(parseDate(point1.date).timeIntervalSince(selectedDate)) <
            abs(parseDate(point2.date).timeIntervalSince(selectedDate))
        })
    }

    private func findNearestPoint(at location: CGPoint, in proxy: ChartProxy, geometry: GeometryProxy) -> DataPoint? {
        guard let plotFrame = proxy.plotFrame else { return nil }
        let xPosition = location.x - geometry[plotFrame].origin.x
        guard let date: Date = proxy.value(atX: xPosition) else { return nil }
        return dataPoints.min(by: { point1, point2 in
            abs(parseDate(point1.date).timeIntervalSince(date)) <
            abs(parseDate(point2.date).timeIntervalSince(date))
        })
    }

    var body: some View {
        Chart {
            ForEach(dataPoints) { point in
                LineMark(
                    x: .value("Date", parseDate(point.date)),
                    y: .value("e1RM", point.value)
                )
                .foregroundStyle(Color.systemPrimary)
                .interpolationMethod(.catmullRom)
                .lineStyle(StrokeStyle(lineWidth: 2))

                AreaMark(
                    x: .value("Date", parseDate(point.date)),
                    y: .value("e1RM", point.value)
                )
                .foregroundStyle(
                    LinearGradient(
                        colors: [Color.systemPrimary.opacity(0.3), Color.clear],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .interpolationMethod(.catmullRom)

                PointMark(
                    x: .value("Date", parseDate(point.date)),
                    y: .value("e1RM", point.value)
                )
                .foregroundStyle(selectedDataPoint?.id == point.id ? Color.gold : Color.systemPrimary)
                .symbolSize(selectedDataPoint?.id == point.id ? 64 : 24)
            }

            // Selection indicator line
            if let selectedPoint = selectedDataPoint {
                RuleMark(x: .value("Selected", parseDate(selectedPoint.date)))
                    .foregroundStyle(Color.systemPrimary.opacity(0.5))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4]))
                    .annotation(position: .top, alignment: .center) {
                        VStack(spacing: 4) {
                            Text("\(Int(selectedPoint.value)) lb")
                                .font(.ariseMono(size: 14, weight: .bold))
                                .foregroundColor(.systemPrimary)
                            Text(formatDateLabel(selectedPoint.date))
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textSecondary)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color.voidMedium)
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.systemPrimary.opacity(0.3), lineWidth: 1)
                        )
                    }
            }
        }
        .chartXSelection(value: $selectedDate)
        .chartXAxis {
            AxisMarks(values: .automatic) { value in
                AxisValueLabel {
                    if let date = value.as(Date.self) {
                        Text(date.formatted(.dateTime.month(.abbreviated).day()))
                            .font(.ariseMono(size: 9))
                            .foregroundColor(.textMuted)
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading) { value in
                AxisValueLabel {
                    if let val = value.as(Double.self) {
                        Text("\(Int(val))")
                            .font(.ariseMono(size: 9))
                            .foregroundColor(.textMuted)
                    }
                }
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [4]))
                    .foregroundStyle(Color.ariseBorder)
            }
        }
        .chartOverlay { proxy in
            GeometryReader { geometry in
                Rectangle()
                    .fill(.clear)
                    .contentShape(Rectangle())
                    .gesture(
                        LongPressGesture(minimumDuration: 0.4)
                            .sequenced(before: DragGesture(minimumDistance: 0))
                            .onChanged { value in
                                switch value {
                                case .first(true):
                                    // Long press started
                                    break
                                case .second(true, let drag):
                                    if let drag = drag {
                                        if let point = findNearestPoint(at: drag.location, in: proxy, geometry: geometry) {
                                            if longPressedPoint?.id != point.id {
                                                // New point selected - haptic feedback
                                                let impact = UIImpactFeedbackGenerator(style: .light)
                                                impact.impactOccurred()
                                            }
                                            longPressedPoint = point
                                            isLongPressing = true
                                        }
                                    }
                                default:
                                    break
                                }
                            }
                            .onEnded { _ in
                                longPressedPoint = nil
                                isLongPressing = false
                            }
                    )
            }
        }
        .overlay(alignment: .top) {
            // Long-press annotation with sets breakdown
            if isLongPressing, let point = longPressedPoint, let sets = point.sets, !sets.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    // Header
                    HStack {
                        Text("\(Int(point.value)) lb")
                            .font(.ariseMono(size: 14, weight: .bold))
                            .foregroundColor(.systemPrimary)
                        Text("•")
                            .foregroundColor(.textMuted)
                        Text(formatDateLabel(point.date))
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.textSecondary)
                    }

                    Rectangle()
                        .fill(Color.ariseBorder)
                        .frame(height: 1)

                    // Sets breakdown
                    ForEach(Array(sets.prefix(5).enumerated()), id: \.offset) { index, set in
                        HStack {
                            Text("\(Int(set.weight)) × \(set.reps)")
                                .font(.ariseMono(size: 11))
                                .foregroundColor(.textPrimary)
                            Spacer()
                            Text("\(Int(set.e1rm))")
                                .font(.ariseMono(size: 11))
                                .foregroundColor(set.e1rm == point.value ? .gold : .textSecondary)
                        }
                    }

                    // View Workout button
                    if let workoutId = point.workoutId, onWorkoutSelected != nil {
                        Rectangle()
                            .fill(Color.ariseBorder)
                            .frame(height: 1)

                        Button(action: {
                            longPressedPoint = nil
                            isLongPressing = false
                            onWorkoutSelected?(workoutId)
                        }) {
                            HStack {
                                Image(systemName: "arrow.right.circle.fill")
                                    .font(.system(size: 12))
                                Text("VIEW WORKOUT")
                                    .font(.ariseMono(size: 10, weight: .semibold))
                            }
                            .foregroundColor(.gold)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 6)
                        }
                    }
                }
                .padding(12)
                .background(Color.voidBlack)
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.gold.opacity(0.5), lineWidth: 1)
                )
                .shadow(color: Color.black.opacity(0.3), radius: 8, x: 0, y: 4)
                .padding(.horizontal, 20)
                .padding(.top, 8)
                .transition(.opacity.combined(with: .scale(scale: 0.95)))
                .animation(.easeOut(duration: 0.15), value: isLongPressing)
            }
        }
    }

    private func formatDateLabel(_ dateString: String) -> String {
        dateString.parseISO8601Date()?.formattedMonthDay ?? dateString
    }

    private func parseDate(_ dateString: String) -> Date {
        dateString.parseISO8601Date() ?? Date()
    }
}

struct AriseTrendBadge: View {
    let direction: String
    let percent: Double?

    var color: Color {
        switch direction {
        case "improving": return .successGreen
        case "regressing": return .warningRed
        default: return .textSecondary
        }
    }

    var icon: String {
        switch direction {
        case "improving": return "arrow.up.right"
        case "regressing": return "arrow.down.right"
        default: return "arrow.right"
        }
    }

    var label: String {
        switch direction {
        case "improving": return "RISING"
        case "regressing": return "FALLING"
        default: return "STABLE"
        }
    }

    var body: some View {
        VStack(alignment: .trailing, spacing: 4) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 12, weight: .bold))
                if let percent = percent {
                    Text("\(abs(percent), specifier: "%.1f")%")
                        .font(.ariseMono(size: 14, weight: .semibold))
                }
            }
            .foregroundColor(color)

            Text(label)
                .font(.ariseMono(size: 9, weight: .medium))
                .foregroundColor(.textMuted)
                .tracking(1)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(color.opacity(0.1))
        .cornerRadius(4)
    }
}

struct RankClassificationCard: View {
    let percentile: ExercisePercentile

    var rank: HunterRank {
        switch percentile.classification.lowercased() {
        case "elite": return .s
        case "advanced": return .a
        case "intermediate": return .c
        case "novice": return .d
        default: return .e
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("HUNTER CLASSIFICATION")
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(1)

                Spacer()

                if let multiplier = percentile.bodyweightMultiplier {
                    HStack(spacing: 4) {
                        Text("\(multiplier, specifier: "%.2f")x")
                            .font(.ariseDisplay(size: 16, weight: .bold))
                            .foregroundColor(.gold)

                        Text("BW")
                            .font(.ariseMono(size: 10, weight: .medium))
                            .foregroundColor(.textMuted)
                    }
                }
            }

            HStack(spacing: 16) {
                // Rank Badge
                RankBadgeView(rank: rank, size: .large)

                VStack(alignment: .leading, spacing: 4) {
                    Text(rank.title)
                        .font(.ariseHeader(size: 18, weight: .bold))
                        .foregroundColor(.textPrimary)

                    if let p = percentile.percentile {
                        Text("Top \(100 - p)% of hunters")
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.textSecondary)
                    }
                }

                Spacer()
            }

            // Progress Bar
            if let p = percentile.percentile {
                VStack(spacing: 6) {
                    GeometryReader { geometry in
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 2)
                                .fill(Color.voidLight)
                                .frame(height: 8)

                            RoundedRectangle(cornerRadius: 2)
                                .fill(rank.color)
                                .frame(width: geometry.size.width * CGFloat(p) / 100, height: 8)
                                .shadow(color: rank.color.opacity(0.5), radius: 4, x: 0, y: 0)
                        }
                    }
                    .frame(height: 8)

                    // Rank markers
                    HStack {
                        Text("E")
                        Spacer()
                        Text("D")
                        Spacer()
                        Text("C")
                        Spacer()
                        Text("B")
                        Spacer()
                        Text("A")
                        Spacer()
                        Text("S")
                    }
                    .font(.ariseMono(size: 9, weight: .medium))
                    .foregroundColor(.textMuted)
                }
            }
        }
        .padding(20)
        .background(Color.voidMedium)
        .overlay(
            Rectangle()
                .fill(rank.color.opacity(0.3))
                .frame(height: 1),
            alignment: .top
        )
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }
}

struct PowerStatsCard: View {
    let trend: TrendResponse

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("POWER STATISTICS")
                .font(.ariseMono(size: 10, weight: .semibold))
                .foregroundColor(.textMuted)
                .tracking(1)

            HStack(spacing: 24) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(trend.totalWorkouts)")
                        .font(.ariseDisplay(size: 24, weight: .bold))
                        .foregroundColor(.systemPrimary)

                    Text("QUESTS")
                        .font(.ariseMono(size: 9, weight: .medium))
                        .foregroundColor(.textMuted)
                        .tracking(0.5)
                }

                if let avg = trend.rollingAverage4w {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(alignment: .lastTextBaseline, spacing: 4) {
                            Text(avg.formattedWeight)
                                .font(.ariseDisplay(size: 24, weight: .bold))
                                .foregroundColor(.textPrimary)

                            Text("lb")
                                .font(.ariseMono(size: 12))
                                .foregroundColor(.textMuted)
                        }

                        Text("4W AVG")
                            .font(.ariseMono(size: 9, weight: .medium))
                            .foregroundColor(.textMuted)
                            .tracking(0.5)
                    }
                }

                Spacer()
            }
        }
        .padding(20)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }
}

// MARK: - Vessel Progress (Bodyweight)

struct VesselProgressView: View {
    @ObservedObject var viewModel: ProgressViewModel

    var body: some View {
        VStack(spacing: 20) {
            if let history = viewModel.bodyweightHistory, !history.entries.isEmpty {
                // Current Vessel Stats Card
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("VESSEL MASS")
                                .font(.ariseMono(size: 10, weight: .semibold))
                                .foregroundColor(.textMuted)
                                .tracking(1)

                            if let latest = history.entries.first {
                                HStack(alignment: .lastTextBaseline, spacing: 6) {
                                    Text(latest.weightDisplay.formattedWeight)
                                        .font(.ariseDisplay(size: 36, weight: .bold))
                                        .foregroundColor(.textPrimary)

                                    Text(latest.weightUnit)
                                        .font(.ariseMono(size: 14))
                                        .foregroundColor(.textMuted)
                                }
                            }
                        }

                        Spacer()

                        VStack(alignment: .trailing, spacing: 4) {
                            HStack(spacing: 4) {
                                Image(systemName: trendIcon(history.trend))
                                    .font(.system(size: 12, weight: .bold))
                                if let rate = history.trendRatePerWeek {
                                    Text("\(abs(rate), specifier: "%.1f") lb/wk")
                                        .font(.ariseMono(size: 13, weight: .semibold))
                                }
                            }
                            .foregroundColor(trendColor(history.trend))

                            Text(trendLabel(history.trend))
                                .font(.ariseMono(size: 9, weight: .medium))
                                .foregroundColor(.textMuted)
                                .tracking(1)
                        }
                    }

                    if history.isPlateau {
                        HStack(spacing: 6) {
                            Image(systemName: "pause.circle.fill")
                                .font(.system(size: 12))
                            Text("PLATEAU DETECTED")
                                .font(.ariseMono(size: 10, weight: .semibold))
                                .tracking(1)
                        }
                        .foregroundColor(.gold)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.gold.opacity(0.1))
                        .cornerRadius(4)
                    }
                }
                .padding(20)
                .background(Color.voidMedium)
                .overlay(
                    Rectangle()
                        .fill(Color.systemPrimary.opacity(0.3))
                        .frame(height: 1),
                    alignment: .top
                )
                .cornerRadius(4)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.ariseBorder, lineWidth: 1)
                )
                .padding(.horizontal)

                // Chart
                VStack(alignment: .leading, spacing: 12) {
                    Text("VESSEL HISTORY")
                        .font(.ariseMono(size: 10, weight: .semibold))
                        .foregroundColor(.textMuted)
                        .tracking(1)

                    AriseBodyweightChart(entries: history.entries)
                        .frame(height: 160)
                }
                .padding(20)
                .background(Color.voidMedium)
                .cornerRadius(4)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.ariseBorder, lineWidth: 1)
                )
                .padding(.horizontal)

                // Averages
                HStack(spacing: 12) {
                    if let avg7 = history.rollingAverage7day {
                        VesselStatCard(title: "7-Day Avg", value: avg7, color: .systemPrimary)
                    }
                    if let avg14 = history.rollingAverage14day {
                        VesselStatCard(title: "14-Day Avg", value: avg14, color: .systemPrimary)
                    }
                }
                .padding(.horizontal)

                // Range
                HStack(spacing: 12) {
                    if let min = history.minWeight {
                        VesselStatCard(title: "Min", value: min, color: .successGreen)
                    }
                    if let max = history.maxWeight {
                        VesselStatCard(title: "Max", value: max, color: .warningRed)
                    }
                }
                .padding(.horizontal)
            } else {
                NoDataPanel(message: "No vessel data recorded.\nLog your weight from the Hunter Profile.")
                    .padding(.horizontal)
            }
        }
    }

    private func trendIcon(_ trend: String) -> String {
        switch trend {
        case "gaining": return "arrow.up.right"
        case "losing": return "arrow.down.right"
        default: return "arrow.right"
        }
    }

    private func trendColor(_ trend: String) -> Color {
        switch trend {
        case "gaining": return .warningRed
        case "losing": return .successGreen
        default: return .textSecondary
        }
    }

    private func trendLabel(_ trend: String) -> String {
        switch trend {
        case "gaining": return "GAINING"
        case "losing": return "CUTTING"
        default: return "STABLE"
        }
    }
}

struct AriseBodyweightChart: View {
    let entries: [BodyweightResponse]

    var body: some View {
        Chart {
            ForEach(entries.reversed()) { entry in
                LineMark(
                    x: .value("Date", parseDate(entry.date)),
                    y: .value("Weight", entry.weightDisplay)
                )
                .foregroundStyle(Color.gold)
                .interpolationMethod(.catmullRom)
                .lineStyle(StrokeStyle(lineWidth: 2))

                AreaMark(
                    x: .value("Date", parseDate(entry.date)),
                    y: .value("Weight", entry.weightDisplay)
                )
                .foregroundStyle(
                    LinearGradient(
                        colors: [Color.gold.opacity(0.3), Color.clear],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .interpolationMethod(.catmullRom)

                PointMark(
                    x: .value("Date", parseDate(entry.date)),
                    y: .value("Weight", entry.weightDisplay)
                )
                .foregroundStyle(Color.gold)
                .symbolSize(16)
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic) { value in
                AxisValueLabel {
                    if let date = value.as(Date.self) {
                        Text(date.formatted(.dateTime.month(.abbreviated).day()))
                            .font(.ariseMono(size: 9))
                            .foregroundColor(.textMuted)
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading) { value in
                AxisValueLabel {
                    if let val = value.as(Double.self) {
                        Text("\(Int(val))")
                            .font(.ariseMono(size: 9))
                            .foregroundColor(.textMuted)
                    }
                }
            }
        }
    }

    private func parseDate(_ dateString: String) -> Date {
        dateString.parseISO8601Date() ?? Date()
    }
}

struct VesselStatCard: View {
    let title: String
    let value: Double
    var color: Color = .textPrimary

    var body: some View {
        VStack(spacing: 6) {
            Text(title.uppercased())
                .font(.ariseMono(size: 9, weight: .semibold))
                .foregroundColor(.textMuted)
                .tracking(1)

            HStack(alignment: .lastTextBaseline, spacing: 4) {
                Text(value.formattedWeight)
                    .font(.ariseDisplay(size: 20, weight: .bold))
                    .foregroundColor(color)

                Text("lb")
                    .font(.ariseMono(size: 10))
                    .foregroundColor(.textMuted)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }
}

// MARK: - Records View (PRs)

struct RecordsView: View {
    @ObservedObject var viewModel: ProgressViewModel
    @State private var filterType: String? = nil

    var filteredPRs: [PRResponse] {
        if let type = filterType {
            return viewModel.prs.filter { $0.prType == type }
        }
        return viewModel.prs
    }

    var body: some View {
        VStack(spacing: 16) {
            // Filter
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    AriseFilterChip(title: "ALL", isSelected: filterType == nil) {
                        filterType = nil
                    }
                    AriseFilterChip(title: "POWER", isSelected: filterType == "e1rm") {
                        filterType = "e1rm"
                    }
                    AriseFilterChip(title: "ENDURANCE", isSelected: filterType == "rep") {
                        filterType = "rep"
                    }
                }
                .padding(.horizontal)
            }

            if filteredPRs.isEmpty {
                NoDataPanel(message: "No records achieved yet.\nComplete quests to set new records!")
                    .padding(.horizontal)
            } else {
                ForEach(Array(filteredPRs.enumerated()), id: \.element.id) { index, pr in
                    RecordCard(pr: pr)
                        .padding(.horizontal)
                        .fadeIn(delay: Double(index) * 0.05)
                }
            }
        }
    }
}

struct AriseFilterChip: View {
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

struct RecordCard: View {
    let pr: PRResponse

    var exerciseColor: Color {
        Color.exerciseColor(for: pr.displayName)
    }

    var fantasyName: String {
        ExerciseFantasyNames.fantasyName(for: pr.displayName)
    }

    var body: some View {
        HStack(spacing: 0) {
            // Left color indicator
            Rectangle()
                .fill(exerciseColor)
                .frame(width: 4)

            HStack(spacing: 12) {
                // Trophy icon
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.gold.opacity(0.1))
                        .frame(width: 48, height: 48)

                    Image(systemName: pr.prType == "e1rm" ? "trophy.fill" : "star.fill")
                        .font(.system(size: 20))
                        .foregroundColor(.gold)
                }

                // Info
                VStack(alignment: .leading, spacing: 4) {
                    Text(pr.displayName)
                        .font(.ariseHeader(size: 14, weight: .semibold))
                        .foregroundColor(.textPrimary)

                    Text("\"\(fantasyName)\"")
                        .font(.ariseMono(size: 10))
                        .foregroundColor(.textMuted)
                        .italic()

                    if pr.prType == "e1rm", let value = pr.value {
                        Text("\(value.formattedWeight) lb e1RM")
                            .font(.ariseMono(size: 12, weight: .semibold))
                            .foregroundColor(.systemPrimary)
                    } else if let reps = pr.reps, let weight = pr.weight {
                        Text("\(reps) reps @ \(weight.formattedWeight) lb")
                            .font(.ariseMono(size: 12, weight: .semibold))
                            .foregroundColor(.successGreen)
                    }
                }

                Spacer()

                // Date
                VStack(alignment: .trailing, spacing: 2) {
                    Text("ACHIEVED")
                        .font(.ariseMono(size: 8, weight: .medium))
                        .foregroundColor(.textMuted)
                        .tracking(0.5)

                    Text(formatDate(pr.achievedAt))
                        .font(.ariseMono(size: 11))
                        .foregroundColor(.textSecondary)
                }
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

    private func formatDate(_ dateString: String) -> String {
        dateString.parseISO8601Date()?.formattedRelative ?? dateString
    }
}

// MARK: - Shared Components

struct NoDataPanel: View {
    let message: String
    @State private var showContent = false

    var body: some View {
        VStack(spacing: 20) {
            ZStack {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.voidLight)
                    .frame(width: 72, height: 72)

                Image(systemName: "chart.bar.xaxis")
                    .font(.system(size: 32))
                    .foregroundColor(.textMuted)
            }
            .opacity(showContent ? 1 : 0)
            .scaleEffect(showContent ? 1 : 0.8)

            Text(message)
                .font(.ariseMono(size: 13))
                .foregroundColor(.textSecondary)
                .multilineTextAlignment(.center)
                .lineSpacing(4)
                .opacity(showContent ? 1 : 0)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .onAppear {
            withAnimation(.easeOut(duration: 0.5).delay(0.2)) {
                showContent = true
            }
        }
    }
}

struct SkillPickerSheet: View {
    let exercises: [ExerciseResponse]
    let selectedExercise: ExerciseResponse?
    let onSelect: (ExerciseResponse) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var searchText = ""

    var filteredExercises: [ExerciseResponse] {
        if searchText.isEmpty {
            return exercises
        }
        return exercises.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                VStack(spacing: 0) {
                    // Search Bar
                    HStack(spacing: 12) {
                        Image(systemName: "magnifyingglass")
                            .foregroundColor(.textMuted)

                        TextField("Search skills...", text: $searchText)
                            .font(.ariseMono(size: 14))
                            .foregroundColor(.textPrimary)

                        if !searchText.isEmpty {
                            Button {
                                searchText = ""
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

                    List {
                        ForEach(filteredExercises) { exercise in
                            Button {
                                onSelect(exercise)
                            } label: {
                                HStack(spacing: 0) {
                                    Rectangle()
                                        .fill(Color.exerciseColor(for: exercise.name))
                                        .frame(width: 4, height: 40)

                                    HStack(spacing: 12) {
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(exercise.name)
                                                .font(.ariseHeader(size: 14, weight: .medium))
                                                .foregroundColor(.textPrimary)

                                            Text("\"\(ExerciseFantasyNames.fantasyName(for: exercise.name))\"")
                                                .font(.ariseMono(size: 10))
                                                .foregroundColor(.textMuted)
                                                .italic()
                                        }

                                        Spacer()

                                        if selectedExercise?.id == exercise.id {
                                            Image(systemName: "checkmark.circle.fill")
                                                .foregroundColor(.systemPrimary)
                                        }
                                    }
                                    .padding(.horizontal, 12)
                                }
                            }
                            .listRowBackground(Color.voidMedium)
                            .listRowSeparatorTint(Color.ariseBorder)
                        }
                    }
                    .listStyle(.plain)
                    .scrollContentBackground(.hidden)
                }
            }
            .navigationTitle("Select Skill")
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
    }
}

// MARK: - Legacy Aliases

typealias ProgressHeader = PowerAnalysisHeader
typealias StrengthProgressView = PowerProgressView
typealias TimeRangeButton = AriseTimeRangeButton
typealias E1RMTrendChart = AriseE1RMChart
typealias ProgressTrendBadge = AriseTrendBadge
typealias PercentileCard = RankClassificationCard
typealias StatsSummaryCard = PowerStatsCard
typealias BodyweightProgressView = VesselProgressView
typealias BodyweightChart = AriseBodyweightChart
typealias AverageCard = VesselStatCard
typealias RangeCard = VesselStatCard
typealias PRsView = RecordsView
typealias FilterChip = AriseFilterChip
typealias ProgressPRCard = RecordCard
typealias NoDataCard = NoDataPanel
typealias ExercisePickerSheet = SkillPickerSheet

#Preview {
    SwiftUI.ProgressView()
}
