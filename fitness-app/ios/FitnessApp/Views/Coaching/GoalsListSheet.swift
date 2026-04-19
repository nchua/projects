import SwiftUI

struct GoalsListSheet: View {
    let goals: [GoalSummaryResponse]
    let maxGoals: Int
    let onDeleteGoal: (String) -> Void
    let onEditGoal: (GoalSummaryResponse) -> Void
    let onAddGoal: () -> Void
    let onDeleteAllGoals: () -> Void

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Group {
                if goals.isEmpty {
                    ContentUnavailableView(
                        "No Goals Yet",
                        systemImage: "target",
                        description: Text("Add your first strength goal to start tracking progress.")
                    )
                } else {
                    List {
                        ForEach(goals) { goal in
                            HStack(spacing: 12) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(goal.exerciseName)
                                        .font(.headline)
                                    Text("\(Int(goal.targetWeight)) \(goal.weightUnit) x \(goal.targetReps)")
                                        .font(.subheadline)
                                        .foregroundColor(.secondary)
                                }
                                Spacer()
                                Button("Edit") {
                                    dismiss()
                                    onEditGoal(goal)
                                }
                                .buttonStyle(.borderless)
                            }
                        }
                        .onDelete { indices in
                            for index in indices {
                                onDeleteGoal(goals[index].id)
                            }
                        }
                    }
                    .listStyle(.insetGrouped)
                }
            }
            .navigationTitle("Goals")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Close") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    if !goals.isEmpty {
                        Button("Delete All", role: .destructive) {
                            onDeleteAllGoals()
                        }
                    }
                }
                ToolbarItem(placement: .bottomBar) {
                    Button {
                        dismiss()
                        onAddGoal()
                    } label: {
                        Label("Add Goal (\(goals.count)/\(maxGoals))", systemImage: "plus.circle.fill")
                    }
                    .disabled(goals.count >= maxGoals)
                }
            }
        }
    }
}
