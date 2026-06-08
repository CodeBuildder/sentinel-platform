"""
Top-level calibration summary endpoint (separate from /memory/calibration raw records).
GET /calibration?action_type=X  → CalibrationSummary with mean Brier score
"""

from fastapi import APIRouter, HTTPException, Query

from models import CalibrationSummary
from routes.memory import calibration_summary
from store import store

router = APIRouter(tags=["calibration"])


@router.get("/calibration", response_model=CalibrationSummary)
async def get_calibration_summary(action_type: str = Query(...)) -> CalibrationSummary:
    return await calibration_summary(action_type)


@router.get("/calibration/all")
async def get_all_calibration_summaries() -> list[CalibrationSummary]:
    """Return Brier score summaries for all action types that have calibration data."""
    cursor = 0
    action_types: set[str] = set()
    while True:
        cursor, keys = await store.r.scan(
            cursor, match="wm:memory:calibration:*", count=200
        )
        for key in keys:
            action_type = key.removeprefix("wm:memory:calibration:")
            action_types.add(action_type)
        if cursor == 0:
            break

    summaries = []
    for at in action_types:
        try:
            summaries.append(await calibration_summary(at))
        except HTTPException:
            pass
    return summaries
