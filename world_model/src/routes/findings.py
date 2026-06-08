"""
Write API — findings ingestion.
POST /findings  (idempotent on event_id, schema-validated)
GET  /findings  (query by entity_id, last N)
"""

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

# resolve sentinel_sdk from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
from sentinel_sdk.schema import ValidationError, validate_event

from models import FindingIngest
from store import store

router = APIRouter(tags=["findings"])


@router.post("/findings", status_code=200)
async def ingest_finding(body: FindingIngest) -> dict:
    """Idempotent finding ingestion. Re-submitting the same event_id returns 200."""
    event = body.model_dump(exclude_none=True)

    # schema validation
    try:
        validate_event(event)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # idempotency check
    if await store.finding_exists(body.event_id):
        return {"status": "duplicate", "event_id": body.event_id}

    # update entity security posture / fragility if payload carries them
    if body.entity_id:
        data = await store.get_entity(body.entity_id)
        if data:
            payload = body.payload
            updated = False
            if "security_posture" in payload:
                data["security_posture"] = payload["security_posture"]
                updated = True
            if "fragility_score" in payload:
                data["fragility_score"] = float(payload["fragility_score"])
                updated = True
            if updated:
                from datetime import datetime, timezone
                data["updated_at"] = datetime.now(timezone.utc).isoformat()
                await store.upsert_entity(data)
                from graph import graph
                graph.add_entity(data)

    await store.store_finding(event)
    return {"status": "accepted", "event_id": body.event_id}


@router.get("/findings")
async def list_findings(
    entity_id: str = Query(..., description="Filter by entity_id"),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[dict]:
    return await store.get_findings_for_entity(entity_id, limit=limit)
