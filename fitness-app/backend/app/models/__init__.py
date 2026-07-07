"""SQLAlchemy database models"""

from app.models.achievement import AchievementDefinition, UserAchievement
from app.models.activity import DailyActivity
from app.models.bodyweight import BodyweightEntry
from app.models.exercise import Exercise
from app.models.friend import FriendRequest, FriendRequestStatus, Friendship
from app.models.goal import Goal, GoalProgressSnapshot, GoalStatus
from app.models.notification import DeviceToken, NotificationPreference, NotificationType
from app.models.password_reset import PasswordResetToken
from app.models.pr import PR, PRType
from app.models.progress import HunterRank, UserProgress
from app.models.quest import QuestDefinition, QuestDifficulty, QuestType, UserQuest
from app.models.scan_balance import PurchaseRecord, ScanBalance
from app.models.screenshot_usage import ScreenshotUsage
from app.models.user import E1RMFormula, TrainingExperience, User, UserProfile
from app.models.user import WeightUnit as UserWeightUnit
from app.models.whoop import WhoopConnection
from app.models.workout import (
    HeartRateSample,
    Set,
    WeightUnit,
    WorkoutExercise,
    WorkoutSession,
)

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
    "HeartRateSample",
    "WeightUnit",
    "WhoopConnection",
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
    "FriendRequest",
    "Friendship",
    "FriendRequestStatus",
    "PasswordResetToken",
    "Goal",
    "GoalProgressSnapshot",
    "GoalStatus",
    "ScreenshotUsage",
    "ScanBalance",
    "PurchaseRecord",
    "DeviceToken",
    "NotificationPreference",
    "NotificationType",
]
