"""Onboarding service — pre-populate default tasks for new users.

Per spec: Pre-populate suggested daily non-negotiables
(supplements, reading, writing, coding). User can edit/remove.
"""

from sqlalchemy.orm import Session

from app.models.enums import Cadence, MissedBehavior, TaskPriority
from app.models.recurring_task import RecurringTask

DEFAULT_TASKS = [
    {
        "title": "Supplements",
        "cadence": Cadence.DAILY,
        "priority": TaskPriority.NON_NEGOTIABLE,
        "sort_order": 0,
    },
    {
        "title": "Reading",
        "cadence": Cadence.DAILY,
        "priority": TaskPriority.NON_NEGOTIABLE,
        "sort_order": 1,
    },
    {
        "title": "Writing",
        "cadence": Cadence.DAILY,
        "priority": TaskPriority.NON_NEGOTIABLE,
        "sort_order": 2,
    },
    {
        "title": "Coding",
        "cadence": Cadence.DAILY,
        "priority": TaskPriority.NON_NEGOTIABLE,
        "sort_order": 3,
    },
]


def create_default_tasks(
    user_id: str, db: Session
) -> list[RecurringTask]:
    """Pre-populate default daily non-negotiables for a new user.

    Returns the list of created tasks.
    """
    created = [
        RecurringTask(
            user_id=user_id,
            title=task_data["title"],
            cadence=task_data["cadence"].value,
            priority=task_data["priority"].value,
            missed_behavior=MissedBehavior.ROLL_FORWARD.value,
            sort_order=task_data["sort_order"],
        )
        for task_data in DEFAULT_TASKS
    ]
    db.add_all(created)
    db.flush()
    return created
