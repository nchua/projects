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
    @State private var expandedExerciseId: String?

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

            // Big Three Cards
            ForEach(viewModel.bigThreeExercises) { exercise in
                BigThreeCard(
                    exercise: exercise,
                    trend: viewModel.trend(for: exercise.id),
                    percentile: viewModel.percentile(for: exercise.id),
                    isExpanded: expandedExerciseId == exercise.id
                ) {
                    withAnimation(.quickSpring) {
                        if expandedExerciseId == exercise.id {
                            expandedExerciseId = nil
                        } else {
                            expandedExerciseId = exercise.id
                        }
                    }
                }
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
                .cornerRadius(4)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.ariseBorder, lineWidth: 1)
                )
                .padding(.horizontal)
            }

            // Additional Exercises Section
            if !viewModel.additionalExercises.isEmpty {
                HStack {
                    HStack(spacing: 8) {
                        Image(systemName: "diamond.fill")
                            .font(.system(size: 8))
                            .foregroundColor(.systemPrimary)
                        Text("ADDITIONAL SKILLS")
                            .font(.ariseMono(size: 11, weight: .semibold))
                            .foregroundColor(.textMuted)
                            .tracking(2)
                    }
                    Spacer()
                }
                .padding(.horizontal)
                .padding(.top, 8)

                ForEach(viewModel.additionalExercises) { exercise in
                    AdditionalExerciseCard(
                        exercise: exercise,
                        trend: viewModel.trend(for: exercise.id),
                        percentile: viewModel.percentile(for: exercise.id),
                        isExpanded: expandedExerciseId == exercise.id,
                        onTap: {
                            withAnimation(.quickSpring) {
                                if expandedExerciseId == exercise.id {
                                    expandedExerciseId = nil
                                } else {
                                    expandedExerciseId = exercise.id
                                }
                            }
                        },
                        onRemove: {
                            withAnimation(.quickSpring) {
                                viewModel.removeExercise(exercise.id)
                            }
                        }
                    )
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
                .background(Color.voidMedium)
                .cornerRadius(4)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
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

// MARK: - Big Three Card

struct BigThreeCard: View {
    let exercise: ExerciseResponse
    let trend: TrendResponse?
    let percentile: ExercisePercentile?
    let isExpanded: Bool
    let onTap: () -> Void

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
            // Main Card - Always Visible
            Button(action: onTap) {
                HStack(spacing: 0) {
                    // Left color bar
                    Rectangle()
                        .fill(exerciseColor)
                        .frame(width: 4)

                    HStack(spacing: 16) {
                        // Exercise Info
                        VStack(alignment: .leading, spacing: 4) {
                            Text(exercise.name)
                                .font(.ariseHeader(size: 16, weight: .semibold))
                                .foregroundColor(.textPrimary)

                            Text("\"\(ExerciseFantasyNames.fantasyName(for: exercise.name))\"")
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textMuted)
                                .italic()
                        }

                        Spacer()

                        // E1RM Value
                        if let current = trend?.currentE1rm {
                            VStack(alignment: .trailing, spacing: 2) {
                                HStack(alignment: .lastTextBaseline, spacing: 4) {
                                    Text(current.formattedWeight)
                                        .font(.ariseDisplay(size: 28, weight: .bold))
                                        .foregroundColor(.systemPrimary)

                                    Text("lb")
                                        .font(.ariseMono(size: 11))
                                        .foregroundColor(.textMuted)
                                }

                                // Trend indicator
                                if let direction = trend?.trendDirection {
                                    HStack(spacing: 4) {
                                        Image(systemName: trendIcon(direction))
                                            .font(.system(size: 10, weight: .bold))
                                        if let percent = trend?.percentChange {
                                            Text("\(abs(percent), specifier: "%.1f")%")
                                                .font(.ariseMono(size: 10, weight: .semibold))
                                        }
                                    }
                                    .foregroundColor(trendColor(direction))
                                }
                            }
                        } else {
                            Text("No data")
                                .font(.ariseMono(size: 12))
                                .foregroundColor(.textMuted)
                        }

                        // Expand indicator
                        Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.textMuted)
                    }
                    .padding(16)
                }
                .background(Color.voidMedium)
            }
            .buttonStyle(PlainButtonStyle())

            // Expanded Content
            if isExpanded {
                VStack(spacing: 16) {
                    // Chart
                    if let dataPoints = trend?.dataPoints, !dataPoints.isEmpty {
                        AriseE1RMChart(dataPoints: dataPoints)
                            .frame(height: 140)
                    }

                    // Rank and Stats Row
                    HStack(spacing: 12) {
                        // Rank Badge
                        if percentile != nil {
                            HStack(spacing: 8) {
                                RankBadgeView(rank: rank, size: .small)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(rank.title)
                                        .font(.ariseMono(size: 11, weight: .semibold))
                                        .foregroundColor(.textPrimary)
                                    if let p = percentile?.percentile {
                                        Text("Top \(100 - p)%")
                                            .font(.ariseMono(size: 9))
                                            .foregroundColor(.textMuted)
                                    }
                                }
                            }
                            .padding(10)
                            .background(Color.voidLight)
                            .cornerRadius(4)
                        }

                        Spacer()

                        // Workouts count
                        if let total = trend?.totalWorkouts {
                            VStack(alignment: .trailing, spacing: 2) {
                                Text("\(total)")
                                    .font(.ariseDisplay(size: 20, weight: .bold))
                                    .foregroundColor(.textPrimary)
                                Text("QUESTS")
                                    .font(.ariseMono(size: 9, weight: .medium))
                                    .foregroundColor(.textMuted)
                                    .tracking(0.5)
                            }
                        }

                        // 4W Average
                        if let avg = trend?.rollingAverage4w {
                            VStack(alignment: .trailing, spacing: 2) {
                                HStack(alignment: .lastTextBaseline, spacing: 2) {
                                    Text(avg.formattedWeight)
                                        .font(.ariseDisplay(size: 20, weight: .bold))
                                        .foregroundColor(.textPrimary)
                                    Text("lb")
                                        .font(.ariseMono(size: 9))
                                        .foregroundColor(.textMuted)
                                }
                                Text("4W AVG")
                                    .font(.ariseMono(size: 9, weight: .medium))
                                    .foregroundColor(.textMuted)
                                    .tracking(0.5)
                            }
                        }
                    }
                }
                .padding(16)
                .background(Color.voidDark)
            }
        }
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .overlay(
            Rectangle()
                .fill(exerciseColor.opacity(0.3))
                .frame(height: 1),
            alignment: .top
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

// MARK: - Additional Exercise Card

struct AdditionalExerciseCard: View {
    let exercise: ExerciseResponse
    let trend: TrendResponse?
    let percentile: ExercisePercentile?
    let isExpanded: Bool
    let onTap: () -> Void
    let onRemove: () -> Void

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
            // Main Card
            Button(action: onTap) {
                HStack(spacing: 0) {
                    Rectangle()
                        .fill(exerciseColor)
                        .frame(width: 4)

                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(exercise.name)
                                .font(.ariseHeader(size: 14, weight: .medium))
                                .foregroundColor(.textPrimary)

                            Text("\"\(ExerciseFantasyNames.fantasyName(for: exercise.name))\"")
                                .font(.ariseMono(size: 9))
                                .foregroundColor(.textMuted)
                                .italic()
                        }

                        Spacer()

                        if let current = trend?.currentE1rm {
                            VStack(alignment: .trailing, spacing: 2) {
                                HStack(alignment: .lastTextBaseline, spacing: 4) {
                                    Text(current.formattedWeight)
                                        .font(.ariseDisplay(size: 22, weight: .bold))
                                        .foregroundColor(.systemPrimary)
                                    Text("lb")
                                        .font(.ariseMono(size: 10))
                                        .foregroundColor(.textMuted)
                                }

                                // Trend indicator
                                if let direction = trend?.trendDirection, direction != "insufficient_data" {
                                    HStack(spacing: 4) {
                                        Image(systemName: trendIcon(direction))
                                            .font(.system(size: 9, weight: .bold))
                                        if let percent = trend?.percentChange {
                                            Text("\(abs(percent), specifier: "%.1f")%")
                                                .font(.ariseMono(size: 9, weight: .semibold))
                                        }
                                    }
                                    .foregroundColor(trendColor(direction))
                                }
                            }
                        } else {
                            Text("No data")
                                .font(.ariseMono(size: 11))
                                .foregroundColor(.textMuted)
                        }

                        // Remove button
                        Button(action: onRemove) {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 18))
                                .foregroundColor(.textMuted)
                        }

                        Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(.textMuted)
                    }
                    .padding(12)
                }
                .background(Color.voidMedium)
            }
            .buttonStyle(PlainButtonStyle())

            // Expanded Content
            if isExpanded {
                VStack(spacing: 16) {
                    // Chart
                    if let dataPoints = trend?.dataPoints, !dataPoints.isEmpty {
                        AriseE1RMChart(dataPoints: dataPoints)
                            .frame(height: 120)
                    }

                    // Rank and Stats Row
                    HStack(spacing: 12) {
                        // Rank Badge - only show if we have a real percentile
                        if let p = percentile?.percentile {
                            HStack(spacing: 8) {
                                RankBadgeView(rank: rank, size: .small)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(rank.title)
                                        .font(.ariseMono(size: 11, weight: .semibold))
                                        .foregroundColor(.textPrimary)
                                    Text("Top \(100 - p)%")
                                        .font(.ariseMono(size: 9))
                                        .foregroundColor(.textMuted)
                                }
                            }
                            .padding(10)
                            .background(Color.voidLight)
                            .cornerRadius(4)
                        }

                        Spacer()

                        // Workouts count
                        if let total = trend?.totalWorkouts {
                            VStack(alignment: .trailing, spacing: 2) {
                                Text("\(total)")
                                    .font(.ariseDisplay(size: 20, weight: .bold))
                                    .foregroundColor(.textPrimary)
                                Text("QUESTS")
                                    .font(.ariseMono(size: 9, weight: .medium))
                                    .foregroundColor(.textMuted)
                                    .tracking(0.5)
                            }
                        }

                        // 4W Average
                        if let avg = trend?.rollingAverage4w {
                            VStack(alignment: .trailing, spacing: 2) {
                                HStack(alignment: .lastTextBaseline, spacing: 2) {
                                    Text(avg.formattedWeight)
                                        .font(.ariseDisplay(size: 20, weight: .bold))
                                        .foregroundColor(.textPrimary)
                                    Text("lb")
                                        .font(.ariseMono(size: 9))
                                        .foregroundColor(.textMuted)
                                }
                                Text("4W AVG")
                                    .font(.ariseMono(size: 9, weight: .medium))
                                    .foregroundColor(.textMuted)
                                    .tracking(0.5)
                            }
                        }
                    }
                }
                .padding(12)
                .background(Color.voidDark)
            }
        }
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
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

struct AriseE1RMChart: View {
    let dataPoints: [DataPoint]
    @State private var selectedDate: Date?

    private var selectedDataPoint: DataPoint? {
        guard let selectedDate = selectedDate else { return nil }
        // Find the closest data point to the selected date
        return dataPoints.min(by: { point1, point2 in
            abs(parseDate(point1.date).timeIntervalSince(selectedDate)) <
            abs(parseDate(point2.date).timeIntervalSince(selectedDate))
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
