"""Geocoding endpoint — wraps Apple MapKit Server API geocoding."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.models.user import User
from app.schemas.geocoding import GeocodeRequest, GeocodeResponse
from app.services.mapkit_api import MapKitClient

router = APIRouter(prefix="/geocode", tags=["geocoding"])


def _get_mapkit_client() -> MapKitClient:
    """Build a MapKit client from settings."""
    settings = get_settings()
    if not settings.apple_mapkit_key_id or not settings.apple_mapkit_private_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Geocoding service not configured",
        )
    return MapKitClient(
        team_id=settings.apple_team_id,
        key_id=settings.apple_mapkit_key_id,
        private_key=settings.apple_mapkit_private_key,
        http_client=httpx.AsyncClient(timeout=10.0),
    )


@router.post(
    "",
    response_model=GeocodeResponse,
    status_code=status.HTTP_200_OK,
)
async def geocode_address(
    request: GeocodeRequest,
    user: User = Depends(get_current_user),
) -> GeocodeResponse:
    """Geocode an address to lat/lng coordinates."""
    client = _get_mapkit_client()
    try:
        result = await client.geocode(request.address)
    finally:
        await client.client.aclose()

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found",
        )

    return GeocodeResponse(
        lat=result["lat"],
        lng=result["lng"],
        address=request.address,
    )
