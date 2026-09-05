"""SQLAlchemy database models"""

from app.models.achievement import AchievementDefinition, UserAchievement
from app.models.activity import DailyActivity
from app.models.bodyweight import BodyweightEntry
from app.models.campaign import (
    Campaign,
    CampaignArc,
    CampaignSource,
    CampaignStatus,
    HuntTemplate,
    HuntType,
    PlannedHunt,
    PlannedHuntStatus,
)
from app.models.coach import CoachOutput, CoachOutputKind, CoachOutputSource
from app.models.directive import DirectiveType, UserDirective
from app.models.exercise import Exercise
from app.models.exercise_family import ExerciseFamily
from app.models.friend import FriendRequest, FriendRequestStatus, Friendship
from app.models.gate import GateRank, GateStatus, PRGate
from app.models.goal import Goal, GoalKind, GoalProgressSnapshot, GoalStatus
from app.models.notification import DeviceToken, NotificationPreference, NotificationType
from app.models.password_reset import PasswordResetToken
from app.models.pr import PR, PRType
from app.models.progress import HunterRank, UserProgress
from app.models.quest import QuestDefinition, QuestDifficulty, QuestType, UserQuest
from app.models.scan_balance import PurchaseRecord, ScanBalance
from app.models.screenshot_usage import ScreenshotUsage
from app.models.training_load import DailyTrainingLoad
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
    "ExerciseFamily",
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
    "UserDirective",
    "DirectiveType",
    "PRGate",
    "GateStatus",
    "GateRank",
    "DailyActivity",
    "FriendRequest",
    "Friendship",
    "FriendRequestStatus",
    "PasswordResetToken",
    "Goal",
    "GoalProgressSnapshot",
    "GoalStatus",
    "GoalKind",
    "Campaign",
    "CampaignArc",
    "CampaignSource",
    "CampaignStatus",
    "HuntTemplate",
    "HuntType",
    "PlannedHunt",
    "PlannedHuntStatus",
    "DailyTrainingLoad",
    "CoachOutput",
    "CoachOutputKind",
    "CoachOutputSource",
    "ScreenshotUsage",
    "ScanBalance",
    "PurchaseRecord",
    "DeviceToken",
    "NotificationPreference",
    "NotificationType",
]
