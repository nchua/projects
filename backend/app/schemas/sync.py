"""
Sync Pydantic schemas for request/response validation
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime as datetime_type
from app.schemas.workout import WorkoutCreate
from app.schemas.bodyweight import BodyweightCreate


class SyncConflict(BaseModel):
    """A sync conflict that was resolved"""
    entity_type: str  # "workout", "bodyweight", "profile"
    entity_id: str
    resolution: str  # "client_wins", "server_wins", "merged"
    details: Optional[str] = None


class ProfileUpdate(BaseModel):
    """Profile data for sync"""
    age: Optional[int] = None
    sex: Optional[str] = None
    bodyweight: Optional[float] = None
    height_inches: Optional[float] = None
    training_experience: Optional[str] = None
    preferred_unit: Optional[str] = None
    e1rm_formula: Optional[str] = None
    updated_at: Optional[str] = None


class SyncRequest(BaseModel):
    """Request body for bulk sync"""
    workouts: List[WorkoutCreate] = Field(default_factory=list)
    bodyweight_entries: List[BodyweightCreate] = Field(default_factory=list)
    profile: Optional[ProfileUpdate] = None
    client_timestamp: str = Field(..., description="Client's current timestamp in ISO format")
    device_id: Optional[str] = None


class SyncResult(BaseModel):
    """Result for a single synced entity"""
    entity_type: str
    entity_id: str
    status: str  # "created", "updated", "skipped", "conflict"


class SyncResponse(BaseModel):
    """Response from bulk sync"""
    success: bool
    synced_at: str
    results: List[SyncResult]
    conflicts: List[SyncConflict]
    workouts_synced: int
    bodyweight_entries_synced: int
    profile_synced: bool


class SyncStatusResponse(BaseModel):
    """Response for sync status"""
    last_sync_at: Optional[str] = None
    pending_workouts: int = 0
    pending_bodyweight_entries: int = 0
    is_synced: bool = True
