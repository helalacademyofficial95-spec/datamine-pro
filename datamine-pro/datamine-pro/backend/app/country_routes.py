"""Read-only API routes for country connector capabilities."""
from fastapi import APIRouter, HTTPException

from .connectors.registry import get_country_capabilities, list_country_capabilities

router = APIRouter(tags=["country-connectors"])


@router.get("/countries")
async def countries():
    """List countries and clearly-labelled connector readiness."""
    return {"countries": list_country_capabilities()}


@router.get("/countries/{country_code}")
async def country_details(country_code: str):
    """Get public-source metadata and readiness for one country."""
    result = get_country_capabilities(country_code)
    if result is None:
        raise HTTPException(status_code=404, detail="Country connector is not registered.")
    return result
