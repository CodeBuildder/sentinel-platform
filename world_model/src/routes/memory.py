"""
Shared memory store routes.
POST /memory/incidents          → write incident memory record (upsert by fingerprint)
GET  /memory/incidents          → query by fault_fingerprint
POST /memory/calibration        → write calibration record
GET  /memory/calibration        → query Brier score trend by action_type
GET  /calibration               → per-action-type calibration summary
"""

from fastapi import APIRouter, HTTPException, Query

from models import CalibrationRecord, CalibrationSummary, IncidentMemory
from store import store

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("/incidents", response_model=IncidentMemory, status_code=200)
async def write_incident_memory(body: IncidentMemory) -> IncidentMemory:
    existing = await store.get_incident_memory(body.fault_fingerprint)
    if existing:
        record = IncidentMemory(**existing)
        record.actions_taken = body.actions_taken
        record.outcome = body.outcome
        record.duration_ms = body.duration_ms
        record.was_prediction_correct = body.was_prediction_correct
        from datetime import datetime, timezone
        record.updated_at = datetime.now(timezone.utc).isoformat()
    else:
        record = body
    await store.upsert_incident_memory(record.model_dump())
    return record


@router.get("/incidents")
async def query_incident_memory(
    fault_fingerprint: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[dict]:
    records = await store.list_incident_memories(
        fault_fingerprint=fault_fingerprint, limit=limit
    )
    # compute confidence per record
    for rec in records:
        actions = rec.get("actions_taken", [])
        successes = sum(1 for a in actions if a.get("outcome") == "success")
        total = len(actions) or 1
        rec["confidence"] = round(successes / total, 3)
    return records


@router.post("/calibration", response_model=CalibrationRecord, status_code=200)
async def write_calibration(body: CalibrationRecord) -> CalibrationRecord:
    if body.brier_score is None:
        predicted = body.predicted_outcome
        actual = body.actual_outcome
        # Brier score proxy: 0.0 if correct, 1.0 if wrong, 0.5 for partial match
        body.brier_score = 0.0 if predicted == actual else 1.0
    await store.push_calibration(body.action_type, body.model_dump())
    return body


@router.get("/calibration")
async def query_calibration(
    action_type: str = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    return await store.get_calibration_records(action_type, limit=limit)


# top-level summary endpoint (not under /memory prefix, added in main.py)
async def calibration_summary(action_type: str) -> CalibrationSummary:
    from config import config
    records = await store.get_calibration_records(action_type, limit=500)
    if not records:
        raise HTTPException(status_code=404, detail=f"No calibration data for {action_type!r}")
    scores = [r["brier_score"] for r in records if r.get("brier_score") is not None]
    mean_brier = sum(scores) / len(scores) if scores else 0.0
    return CalibrationSummary(
        action_type=action_type,
        record_count=len(records),
        mean_brier_score=round(mean_brier, 4),
        low_confidence=mean_brier > config.TRUST_BRIER_SURPRISE_THRESHOLD,
    )
