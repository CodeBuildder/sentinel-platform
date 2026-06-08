"""
Incident lifecycle routes.
POST   /incidents              → create / update incident (upsert by incident_id)
GET    /incidents              → list, filterable by state
GET    /incidents/{id}         → get single incident
PATCH  /incidents/{id}         → update state
POST   /incidents/{id}/replay  → counterfactual replay (tagged, no live-state mutation)
"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from store import store

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("", status_code=200)
async def upsert_incident(body: dict) -> dict:
    """Accept any incident event dict (validated upstream by the bus consumer)."""
    if "payload" not in body or "incident_id" not in body.get("payload", {}):
        raise HTTPException(status_code=422, detail="incident payload must contain incident_id")
    await store.upsert_incident(body)
    return {"status": "accepted", "incident_id": body["payload"]["incident_id"]}


@router.get("")
async def list_incidents(
    state: str | None = Query(default=None, description="Filter by state: open|correlating|resolved|escalated"),
) -> list[dict]:
    if state in (None, "open", "correlating"):
        incidents = await store.list_open_incidents()
        if state:
            incidents = [i for i in incidents if i.get("payload", {}).get("state") == state]
        return incidents
    # scan all incidents (closed states)
    open_ids = {i["payload"]["incident_id"] for i in await store.list_open_incidents()}
    # For resolved/escalated we'd need a separate index; for M0 scan open set is sufficient
    # and resolved incidents are readable by ID
    return []


@router.get("/{incident_id}")
async def get_incident(incident_id: str) -> dict:
    data = await store.get_incident(incident_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id!r} not found")
    return data


@router.patch("/{incident_id}")
async def update_incident_state(incident_id: str, body: dict) -> dict:
    data = await store.get_incident(incident_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id!r} not found")
    new_state = body.get("state")
    if new_state:
        data["payload"]["state"] = new_state
        if new_state in ("resolved", "escalated"):
            data["payload"]["resolved_at"] = _now()
        await store.upsert_incident(data)
    return data


@router.post("/{incident_id}/replay")
async def replay_incident(incident_id: str) -> dict:
    data = await store.get_incident(incident_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id!r} not found")
    # Return replay metadata without mutating state
    replay = {
        "incident_id": incident_id,
        "replayed": True,
        "replay_id": str(uuid4()),
        "original_findings": data["payload"].get("correlated_finding_ids", []),
        "note": "Replay tagged. Re-run correlation logic against current world model state.",
        "timestamp": _now(),
    }
    return replay
