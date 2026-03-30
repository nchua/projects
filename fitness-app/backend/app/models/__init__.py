"""SQLAlchemy database models"""

from app.models.achievement import AchievementDefinition, UserAchievement
from app.models.activity import DailyActivity
from app.models.bodyweight import BodyweightEntry
from app.models.dungeon import (
    DungeonDefinition,
    DungeonObjectiveDefinition,
    DungeonObjectiveType,
    DungeonRank,
    DungeonStatus,
    UserDungeon,
    UserDungeonObjective,
)
from app.models.exercise import Exercise
from app.models.friend import FriendRequest, FriendRequestStatus, Friendship
from app.models.mission import (
    ExercisePrescription,
    Goal,
    GoalProgressSnapshot,
    GoalStatus,
    MissionGoal,
    MissionStatus,
    MissionWorkout,
    MissionWorkoutStatus,
    TrainingSplit,
    WeeklyMission,
)
from app.models.notification import DeviceToken, NotificationPreference, NotificationType
from app.models.password_reset import PasswordResetToken
from app.models.pr import PR, PRType
from app.models.progress import HunterRank, UserProgress
from app.models.quest import QuestDefinition, QuestDifficulty, QuestType, UserQuest
from app.models.scan_balance import PurchaseRecord, ScanBalance
from app.models.screenshot_usage import ScreenshotUsage
from app.models.user import E1RMFormula, TrainingExperience, User, UserProfile
from app.models.user import WeightUnit as UserWeightUnit
from app.models.workout import Set, WeightUnit, WorkoutExercise, WorkoutSession

__all__ = [
    "User",
    "UserProfile",
    "TrainingExperience",
    "UserWeightUnit",
    "E1RMFormula",
    "Exercise",
    "WorkoutSession",
    "WorkoutExercise",
    "Set",
    "WeightUnit",
    "BodyweightEntry",
    "PR",
    "PRType",
    "UserProgress",
    "HunterRank",
    "AchievementDefinition",
    "UserAchievement",
    "QuestDefinition",
    "UserQuest",
    "QuestType",
    "QuestDifficulty",
    "DailyActivity",
    "DungeonDefinition",
    "DungeonObjectiveDefinition",
    "UserDungeon",
    "UserDungeonObjective",
    "DungeonRank",
    "DungeonObjectiveType",
    "DungeonStatus",
    "FriendRequest",
    "Friendship",
    "FriendRequestStatus",
    "PasswordResetToken",
    "Goal",
    "GoalProgressSnapshot",
    "WeeklyMission",
    "MissionWorkout",
    "ExercisePrescription",
    "MissionGoal",
    "GoalStatus",
    "MissionStatus",
    "MissionWorkoutStatus",
    "TrainingSplit",
    "ScreenshotUsage",
    "ScanBalance",
    "PurchaseRecord",
    "DeviceToken",
    "NotificationPreference",
    "NotificationType",
]
