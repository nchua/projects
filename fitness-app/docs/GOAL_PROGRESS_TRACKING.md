# Goal Progress Tracking Feature

## Overview

Add visual progress tracking for strength goals that drive weekly missions. Users can see if they're on track to hit their target weight by the deadline through a graph showing projected vs actual progress.

## Current State

Goals already track:
- `exercise_id` - Which lift (Bench, Squat, etc.)
- `target_weight` - Target PR weight
- `target_reps` - Target reps (1 = true 1RM)
- `deadline` - Target date
- `starting_e1rm` - e1RM when goal was created
- `current_e1rm` - Latest e1RM

**Gap**: No historical e1RM snapshots - only current value is stored.

---

## Proposed UI

```
┌─────────────────────────────────────────────────────┐
│  BENCH PRESS                         +2 weeks ahead │
│  Target: 225 lbs by Apr 15                          │
│                                                     │
│  225 ┤                              ┈┈┈┈┈┈●  Target │
│      │                        ┈┈┈┈┈┈┈               │
│  210 ┤                  ┈┈┈┈┈┈   ●───── Actual      │
│      │            ┈┈┈┈┈┈    ●────                   │
│  195 ┤      ┈┈┈┈┈┈     ●────                        │
│      │ ┈┈┈┈┈┈    ●────                              │
│  180 ●────●────                                     │
│      └──────┬──────┬──────┬──────┬──────┬──────┤    │
│           Jan    Feb    Mar    Apr   May            │
│                                                     │
│  Current: 210 lbs e1RM  │  Weekly gain: +3.2 lbs    │
└─────────────────────────────────────────────────────┘
```

**Elements:**
- Dotted line: Projected linear progress from start to target
- Solid line: Actual e1RM over time
- Status badge: "X weeks ahead/behind" or "On track"
- Stats: Current e1RM, weekly gain rate

---

## UI Location Options

| Option | Location | Description |
|--------|----------|-------------|
| **A** | Mission Detail → Tap Goal | Expand goal card to show graph |
| **B** | Progress Tab → Goals Section | New dedicated section with all goals |
| **C** | Quest Center → Goals Header | Collapsible section above quests |
| **D** | Home Screen Card | Summary card linking to detail |

**Recommendation**: Start with **Option A** (tap to expand in Mission Detail) as it's contextual and lowest friction. Can add Option B later for users who want a dedicated view.

---

## Data Model Changes

### New Table: `goal_progress_snapshot`

```sql
CREATE TABLE goal_progress_snapshot (
    id UUID PRIMARY KEY,
    goal_id UUID REFERENCES goal(id),
    recorded_at TIMESTAMP NOT NULL,
    e1rm FLOAT NOT NULL,
    weight FLOAT,           -- Actual weight lifted
    reps INT,               -- Actual reps
    workout_id UUID,        -- Source workout (optional)
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_goal_progress_goal_id ON goal_progress_snapshot(goal_id);
CREATE INDEX idx_goal_progress_recorded_at ON goal_progress_snapshot(recorded_at);
```

### SQLAlchemy Model

```python
# backend/app/models/goal_progress.py
class GoalProgressSnapshot(Base):
    __tablename__ = "goal_progress_snapshot"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    goal_id = Column(UUID, ForeignKey("goal.id"), nullable=False)
    recorded_at = Column(DateTime, nullable=False)
    e1rm = Column(Float, nullable=False)
    weight = Column(Float, nullable=True)
    reps = Column(Integer, nullable=True)
    workout_id = Column(UUID, ForeignKey("workout_session.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    goal = relationship("Goal", back_populates="progress_snapshots")
```

---

## Backend Changes

### 1. Record Progress on Workout Save

In `mission_service.py` → `check_mission_workout_completion()`:

```python
# After detecting PR or new e1RM for a goal exercise:
if new_e1rm > goal.current_e1rm:
    # Update current e1rm
    goal.current_e1rm = new_e1rm

    # Record snapshot
    snapshot = GoalProgressSnapshot(
        goal_id=goal.id,
        recorded_at=workout.date,
        e1rm=new_e1rm,
        weight=best_set.weight,
        reps=best_set.reps,
        workout_id=workout.id
    )
    db.add(snapshot)
```

### 2. New API Endpoint

```python
# backend/app/api/goals.py

@router.get("/{goal_id}/progress")
def get_goal_progress(
    goal_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> GoalProgressResponse:
    """Get goal progress history with projected vs actual data."""

    goal = get_goal_or_404(db, goal_id, current_user.id)
    snapshots = db.query(GoalProgressSnapshot)\
        .filter(GoalProgressSnapshot.goal_id == goal_id)\
        .order_by(GoalProgressSnapshot.recorded_at)\
        .all()

    # Calculate projected line points
    projected = calculate_projected_progress(goal)

    # Calculate status (ahead/behind/on-track)
    status = calculate_progress_status(goal, snapshots)

    return GoalProgressResponse(
        goal=goal,
        snapshots=snapshots,
        projected_points=projected,
        status=status,
        weekly_gain_rate=calculate_weekly_gain(snapshots)
    )
```

### 3. Response Schema

```python
# backend/app/schemas/goal_progress.py

class ProgressPoint(BaseModel):
    date: date
    e1rm: float

class GoalProgressStatus(str, Enum):
    AHEAD = "ahead"
    ON_TRACK = "on_track"
    BEHIND = "behind"

class GoalProgressResponse(BaseModel):
    goal_id: str
    exercise_name: str
    target_weight: float
    target_date: date
    starting_e1rm: float
    current_e1rm: float

    # Graph data
    actual_points: List[ProgressPoint]
    projected_points: List[ProgressPoint]

    # Status
    status: GoalProgressStatus
    weeks_difference: int  # positive = ahead, negative = behind
    weekly_gain_rate: float  # lbs per week
    required_gain_rate: float  # needed to hit target
```

---

## iOS Implementation

### 1. API Types

```swift
// APITypes.swift

struct GoalProgressResponse: Decodable {
    let goalId: String
    let exerciseName: String
    let targetWeight: Double
    let targetDate: String
    let startingE1rm: Double
    let currentE1rm: Double
    let actualPoints: [ProgressPoint]
    let projectedPoints: [ProgressPoint]
    let status: String  // "ahead", "on_track", "behind"
    let weeksDifference: Int
    let weeklyGainRate: Double
    let requiredGainRate: Double
}

struct ProgressPoint: Decodable {
    let date: String
    let e1rm: Double
}
```

### 2. Progress Graph View

```swift
// Views/Goals/GoalProgressGraphView.swift

struct GoalProgressGraphView: View {
    let progress: GoalProgressResponse

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header with status badge
            HStack {
                Text(progress.exerciseName.uppercased())
                    .font(.ariseHeader(size: 16))
                Spacer()
                StatusBadge(status: progress.status, weeks: progress.weeksDifference)
            }

            // Target info
            Text("Target: \(Int(progress.targetWeight)) lbs by \(progress.targetDate)")
                .font(.ariseBody(size: 14))
                .foregroundColor(.textSecondary)

            // Chart
            Chart {
                // Projected line (dotted)
                ForEach(progress.projectedPoints, id: \.date) { point in
                    LineMark(
                        x: .value("Date", point.date),
                        y: .value("e1RM", point.e1rm)
                    )
                    .foregroundStyle(.textMuted)
                    .lineStyle(StrokeStyle(dash: [5, 5]))
                }

                // Actual line (solid)
                ForEach(progress.actualPoints, id: \.date) { point in
                    LineMark(
                        x: .value("Date", point.date),
                        y: .value("e1RM", point.e1rm)
                    )
                    .foregroundStyle(.systemPrimary)

                    PointMark(
                        x: .value("Date", point.date),
                        y: .value("e1RM", point.e1rm)
                    )
                    .foregroundStyle(.systemPrimary)
                }
            }
            .frame(height: 200)
            .chartYAxis { /* styling */ }
            .chartXAxis { /* styling */ }

            // Stats row
            HStack {
                StatLabel(title: "Current", value: "\(Int(progress.currentE1rm)) lbs")
                Divider()
                StatLabel(title: "Weekly Gain", value: "+\(progress.weeklyGainRate, specifier: "%.1f") lbs")
            }
        }
        .padding()
        .background(Color.voidMedium)
        .cornerRadius(8)
    }
}
```

### 3. Integration Point (Mission Detail)

```swift
// In MissionDetailView.swift - Goal card becomes tappable

GoalCard(goal: goal)
    .onTapGesture {
        selectedGoalId = goal.id
        showProgressSheet = true
    }
    .sheet(isPresented: $showProgressSheet) {
        GoalProgressDetailView(goalId: selectedGoalId)
    }
```

---

## Migration Strategy

### Backfill Historical Data

Create a migration script to populate initial snapshots from existing PR data:

```python
# scripts/backfill_goal_progress.py

def backfill_goal_progress(db: Session):
    """Create initial snapshots from PR history for existing goals."""

    goals = db.query(Goal).filter(Goal.status == "active").all()

    for goal in goals:
        # Get PRs for this exercise since goal creation
        prs = db.query(PR).filter(
            PR.user_id == goal.user_id,
            PR.exercise_id == goal.exercise_id,
            PR.achieved_at >= goal.created_at
        ).order_by(PR.achieved_at).all()

        for pr in prs:
            snapshot = GoalProgressSnapshot(
                goal_id=goal.id,
                recorded_at=pr.achieved_at,
                e1rm=pr.e1rm,
                weight=pr.weight,
                reps=pr.reps
            )
            db.add(snapshot)

        # Also add starting point
        if goal.starting_e1rm:
            snapshot = GoalProgressSnapshot(
                goal_id=goal.id,
                recorded_at=goal.created_at,
                e1rm=goal.starting_e1rm
            )
            db.add(snapshot)

    db.commit()
```

---

## Goal Setup Enhancement (Future)

### Simple (MVP)
- Target weight + deadline (current)

### Guided (v2)
Add aggressiveness slider:
- Conservative: +2.5 lbs/week
- Moderate: +5 lbs/week
- Aggressive: +7.5 lbs/week

System validates if goal is achievable and suggests adjusted deadline if too aggressive.

### Smart (v3)
- User only enters target weight
- System analyzes historical progress rate
- Automatically suggests realistic deadline
- "Based on your +4.2 lbs/week average, you could hit 225 lbs by April 20"

---

## Open Questions

1. **Granularity**: Should we record a snapshot on every workout with the goal exercise, or only when e1RM improves?
   - Recommendation: Every workout (shows plateaus, which are useful data)

2. **Multiple exercises per goal**: If user does both Bench and Incline Bench, which e1RM counts?
   - Recommendation: Primary exercise only (the one in `goal.exercise_id`)

3. **Retroactive goals**: If user creates a goal for an exercise they've been doing, should we backfill from PR history?
   - Recommendation: Yes, via migration script

4. **Goal editing**: If user changes deadline or target, recalculate projected line?
   - Recommendation: Yes, and keep old snapshots

---

## Implementation Order

1. **Backend**: Add `goal_progress_snapshot` model + migration
2. **Backend**: Add snapshot recording in workout save flow
3. **Backend**: Add `/goals/{id}/progress` endpoint
4. **Backend**: Backfill script for existing goals
5. **iOS**: Add API types and client method
6. **iOS**: Create `GoalProgressGraphView` component
7. **iOS**: Integrate into Mission Detail (tap goal to expand)
8. **iOS**: Add loading/empty states

---

## Estimated Effort

| Component | Estimate |
|-----------|----------|
| Backend model + migration | 1 hour |
| Backend snapshot recording | 1 hour |
| Backend progress endpoint | 2 hours |
| Backfill script | 1 hour |
| iOS graph component | 3 hours |
| iOS integration | 2 hours |
| Testing & polish | 2 hours |
| **Total** | ~12 hours |
