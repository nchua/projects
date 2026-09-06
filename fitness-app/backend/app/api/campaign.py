"""
Campaign API (ARISE v3 spec §4.5): current, import, manual create, update.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.campaign import CampaignStatus
from app.models.user import User
from app.schemas.campaign import (
    CampaignCreate,
    CampaignImportRequest,
    CampaignImportResponse,
    CampaignResponse,
    CampaignUpdate,
)
from app.services import campaign_service

router = APIRouter()


def _parse_client_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@router.get("/current", response_model=CampaignResponse)
async def get_current_campaign(
    client_date: Optional[str] = Query(None, description="Client's local date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The active campaign + arcs + current arc index + week-in-arc + deload flag."""
    campaign = campaign_service.get_active_campaign(db, current_user.id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active campaign")
    return campaign_service.campaign_to_dict(db, campaign, _parse_client_date(client_date))


@router.post("/import", response_model=CampaignImportResponse, status_code=status.HTTP_201_CREATED)
async def import_campaign(
    body: CampaignImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import the training-calendar PWA's ``PHASES`` array verbatim (spec §4.3).

    409 when an active campaign exists unless ``replace`` is true (the old
    one is completed and its future planned hunts deleted).
    """
    try:
        _, payload = campaign_service.apply_import(
            db, current_user.id,
            name=body.name,
            phases=[p.model_dump() for p in body.phases],
            objectives=body.objectives,
            start_date=body.start_date,
            client_date=body.client_date,
            goal=body.goal,
            replace=body.replace,
        )
    except campaign_service.ActiveCampaignExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active campaign already exists; send replace=true to retire it.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    db.commit()
    return payload


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Minimal manual create — arcs only, no templates (templates come from import)."""
    try:
        campaign = campaign_service.create_campaign(
            db, current_user.id,
            name=body.name,
            arcs=[a.model_dump() for a in body.arcs],
            start_date=body.start_date,
            client_date=body.client_date,
            goal=body.goal,
        )
    except campaign_service.ActiveCampaignExists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An active campaign already exists")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    db.commit()
    return campaign_service.campaign_to_dict(db, campaign, body.client_date)


@router.put("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: str,
    body: CampaignUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Edit status / name / goal and arc mileage bands; future planned hunts are re-prescribed."""
    campaign = campaign_service.get_campaign(db, current_user.id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if body.status is not None:
        if body.status not in [s.value for s in CampaignStatus]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {[s.value for s in CampaignStatus]}",
            )
        if body.status == CampaignStatus.ACTIVE.value and campaign.status != CampaignStatus.ACTIVE.value:
            other = campaign_service.get_active_campaign(db, current_user.id)
            if other is not None and other.id != campaign.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Another campaign is active")
        campaign.status = body.status
    if body.name is not None:
        campaign.name = body.name
    if body.goal is not None:
        campaign.goal = body.goal

    arcs_changed = False
    if body.arcs:
        by_id = {arc.id: arc for arc in campaign.arcs}
        for edit in body.arcs:
            arc = by_id.get(edit.id)
            if arc is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Arc {edit.id} not found")
            for field in ("run_miles_min", "run_miles_max", "long_run_miles", "weeks"):
                value = getattr(edit, field)
                if value is not None:
                    setattr(arc, field, value)
                    arcs_changed = True
            if arc.run_miles_min is not None and arc.run_miles_max is not None and arc.run_miles_max < arc.run_miles_min:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="run_miles_max must be ≥ run_miles_min")
    db.flush()
    if arcs_changed and campaign.status == CampaignStatus.ACTIVE.value:
        today = body.client_date or date.today()
        campaign_service.refresh_planned_hunts(
            db, campaign, campaign_service._future_planned(db, campaign, today)
        )
    db.commit()
    campaign = campaign_service.get_campaign(db, current_user.id, campaign_id)
    return campaign_service.campaign_to_dict(db, campaign, body.client_date)
