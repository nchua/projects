"""SQLAlchemy database models"""

from app.models.user import User, UserProfile, TrainingExperience, WeightUnit as UserWeightUnit, E1RMFormula
from app.models.exercise import Exercise
from app.models.workout import WorkoutSession, WorkoutExercise, Set, WeightUnit
from app.models.bodyweight import BodyweightEntry
from app.models.pr import PR, PRType
from app.models.progress import UserProgress, HunterRank
from app.models.achievement import AchievementDefinition, UserAchievement
from app.models.quest import QuestDefinition, UserQuest, QuestType, QuestDifficulty
from app.models.activity import DailyActivity
from app.models.dungeon import (
    DungeonDefinition, DungeonObjectiveDefinition,
    UserDungeon, UserDungeonObjective,
    DungeonRank, DungeonObjectiveType, DungeonStatus
)
from app.models.friend import FriendRequest, Friendship, FriendRequestStatus
from app.models.password_reset import PasswordResetToken
from app.models.mission import (
    Goal, GoalProgressSnapshot, WeeklyMission, MissionWorkout, ExercisePrescription, MissionGoal,
    GoalStatus, MissionStatus, MissionWorkoutStatus, TrainingSplit
)
from app.models.screenshot_usage import ScreenshotUsage

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
]
