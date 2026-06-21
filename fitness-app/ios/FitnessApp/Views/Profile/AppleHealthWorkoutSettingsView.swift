import SwiftUI

// MARK: - State

/// Counts surfaced after a manual "Import Now". This is the ONE place import results show —
/// the silent foreground path never surfaces a summary.
struct AppleHealthImportSummary {
    let imported: Int
    let updated: Int
    let skipped: Int
    let unmatched: Int
    let questsCompleted: Int
}

enum AppleHealthImportState {
    case notAvailable                       // iPad / no Health data
    case notAuthorized                      // permission not yet granted
    case idle(lastImported: Date?)          // connected, ready
    case importing
    case imported(AppleHealthImportSummary) // ran with new data
    case upToDate(lastImported: Date?)      // ran, nothing new (or Simulator)
    case error(String)
}

// MARK: - View Model

@MainActor
final class AppleHealthWorkoutSettingsViewModel: ObservableObject {
    @Published var state: AppleHealthImportState = .idle(lastImported: nil)

    private let healthKit = HealthKitManager.shared

    /// Recompute the resting state from device + auth status (call on appear).
    func refresh() {
        guard healthKit.isHealthDataAvailable else { state = .notAvailable; return }
        state = healthKit.isAuthorized
            ? .idle(lastImported: WorkoutImportStore.shared.lastWorkoutImportDate)
            : .notAuthorized
    }

    /// "Connect Apple Health": prompt for permission (the one explicit prompt), then import.
    func connect() async {
        guard healthKit.isHealthDataAvailable else { state = .notAvailable; return }
        await healthKit.requestAuthorization()
        if healthKit.isAuthorized {
            await runImport()
        } else {
            state = .notAuthorized
        }
    }

    /// Manual "Import Now".
    func runImport() async {
        guard healthKit.isHealthDataAvailable else { state = .notAvailable; return }
        guard healthKit.isAuthorized else { state = .notAuthorized; return }

        state = .importing
        let age = await currentAge()
        let response = await healthKit.importNewWorkouts(age: age)

        if let response = response, !(response.imported.isEmpty && response.sessionsUpdated.isEmpty) {
            state = .imported(AppleHealthImportSummary(
                imported: response.imported.count,
                updated: response.sessionsUpdated.count,
                skipped: response.skippedDuplicates.count,
                unmatched: response.unmatched.count,
                questsCompleted: response.questsCompleted.count
            ))
        } else {
            // nil or nothing-new. Per spec, hidden read denials surface as "no new workouts",
            // not a failure (HealthKit never tells us a read was denied).
            state = .upToDate(lastImported: WorkoutImportStore.shared.lastWorkoutImportDate)
        }
    }

    private func currentAge() async -> Int? {
        (try? await APIClient.shared.getProfile())?.age
    }
}

// MARK: - View

struct AppleHealthWorkoutSettingsView: View {
    @StateObject private var viewModel = AppleHealthWorkoutSettingsViewModel()

    var body: some View {
        ZStack {
            VoidBackground()

            ScrollView {
                VStack(spacing: 20) {
                    headerCard
                    statusSection
                    actionSection
                }
                .padding(.vertical, 24)
            }
        }
        .navigationTitle("Apple Health")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { viewModel.refresh() }
    }

    // MARK: Header

    private var headerCard: some View {
        HStack(alignment: .top, spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.systemPrimary.opacity(0.1))
                    .frame(width: 48, height: 48)
                Image(systemName: "figure.run")
                    .font(.system(size: 22))
                    .foregroundColor(.systemPrimary)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Workouts & Heart Rate")
                    .font(.ariseHeader(size: 16, weight: .semibold))
                    .foregroundColor(.textPrimary)
                Text("Apple Watch workouts import automatically each time you open the app — including heart rate, zones, and calories.")
                    .font(.ariseBody(size: 12))
                    .foregroundColor(.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)
        }
        .padding(16)
        .ariseWorkoutCard()
        .padding(.horizontal)
    }

    // MARK: Status

    private var statusSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            AriseSectionHeader(title: "Status")
                .padding(.horizontal)

            VStack(alignment: .leading, spacing: 12) {
                statusContent
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
            .ariseWorkoutCard()
            .padding(.horizontal)
        }
    }

    @ViewBuilder
    private var statusContent: some View {
        switch viewModel.state {
        case .notAvailable:
            statusRow(icon: "xmark.circle", color: .textMuted,
                      title: "Not available",
                      detail: "This device has no Health data (for example, iPad).")
        case .notAuthorized:
            statusRow(icon: "lock.circle", color: .gold,
                      title: "Not connected",
                      detail: "Grant access to import Apple Watch workouts and heart rate.")
        case .idle(let last):
            statusRow(icon: "checkmark.circle", color: .successGreen,
                      title: "Connected",
                      detail: lastImportedDetail(last))
        case .importing:
            HStack(spacing: 10) {
                SwiftUI.ProgressView()
                    .tint(.systemPrimary)
                Text("Importing workouts…")
                    .font(.ariseBody(size: 13))
                    .foregroundColor(.textSecondary)
            }
        case .imported(let summary):
            importedSummary(summary)
        case .upToDate(let last):
            statusRow(icon: "checkmark.circle", color: .successGreen,
                      title: "Up to date",
                      detail: last == nil
                        ? "No new workouts found."
                        : "No new workouts found.\n\(lastImportedDetail(last))")
        case .error(let message):
            statusRow(icon: "exclamationmark.triangle", color: .warningRed,
                      title: "Something went wrong",
                      detail: message)
        }
    }

    private func statusRow(icon: String, color: Color, title: String, detail: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 18))
                .foregroundColor(color)
                .frame(width: 24)
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.ariseHeader(size: 14, weight: .semibold))
                    .foregroundColor(.textPrimary)
                Text(detail)
                    .font(.ariseBody(size: 12))
                    .foregroundColor(.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
    }

    private func importedSummary(_ summary: AppleHealthImportSummary) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Image(systemName: "checkmark.seal.fill")
                    .font(.system(size: 18))
                    .foregroundColor(.successGreen)
                    .frame(width: 24)
                Text("Import complete")
                    .font(.ariseHeader(size: 14, weight: .semibold))
                    .foregroundColor(.textPrimary)
            }

            VStack(spacing: 8) {
                if summary.imported > 0 { summaryStat("Imported", summary.imported, .systemPrimary) }
                if summary.updated > 0 { summaryStat("HR backfilled", summary.updated, .systemPrimary) }
                if summary.questsCompleted > 0 { summaryStat("Quests completed", summary.questsCompleted, .gold) }
                if summary.skipped > 0 { summaryStat("Already imported", summary.skipped, .textMuted) }
                if summary.unmatched > 0 { summaryStat("Log these first", summary.unmatched, .textMuted) }
            }
        }
    }

    private func summaryStat(_ label: String, _ value: Int, _ color: Color) -> some View {
        HStack {
            Text(label)
                .font(.ariseBody(size: 13))
                .foregroundColor(.textSecondary)
            Spacer()
            Text("\(value)")
                .font(.ariseMono(size: 14, weight: .semibold))
                .foregroundColor(color)
        }
    }

    private func lastImportedDetail(_ date: Date?) -> String {
        guard let date = date else { return "Workouts will import on your next visit." }
        return "Last checked \(date.formatted(date: .abbreviated, time: .shortened))."
    }

    // MARK: Action

    @ViewBuilder
    private var actionSection: some View {
        switch viewModel.state {
        case .notAvailable, .importing:
            EmptyView()
        case .notAuthorized:
            primaryButton(title: "CONNECT APPLE HEALTH", systemImage: "heart.text.square") {
                await viewModel.connect()
            }
        default:
            primaryButton(title: "IMPORT NOW", systemImage: "arrow.clockwise") {
                await viewModel.runImport()
            }
        }
    }

    private func primaryButton(title: String, systemImage: String, action: @escaping () async -> Void) -> some View {
        Button {
            let impact = UIImpactFeedbackGenerator(style: .medium)
            impact.impactOccurred()
            Task { await action() }
        } label: {
            HStack(spacing: 8) {
                Image(systemName: systemImage)
                    .font(.system(size: 14, weight: .bold))
                Text(title)
                    .font(.ariseHeader(size: 14, weight: .semibold))
                    .tracking(2)
            }
            .frame(maxWidth: .infinity)
            .frame(height: 54)
            .background(Color.systemPrimary)
            .foregroundColor(.voidBlack)
            .overlay(Rectangle().stroke(Color.systemPrimary, lineWidth: 2))
            .shadow(color: .systemPrimaryGlow, radius: 15, x: 0, y: 0)
        }
        .padding(.horizontal)
    }
}

// MARK: - Card chrome

private extension View {
    /// Standard ARISE settings-card chrome (file-private to avoid name clashes).
    func ariseWorkoutCard() -> some View {
        self
            .background(Color.voidMedium)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
    }
}
