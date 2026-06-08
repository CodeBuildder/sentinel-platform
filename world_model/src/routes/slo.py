"""
SLO / error-budget routes.
POST /slo                        → define / update SLO for a service
GET  /slo/{service_id}/budget    → current budget state
POST /slo/{service_id}/burn      → deduct from budget
GET  /slo/{service_id}/burns     → burn history
"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from config import config
from models import BudgetBurnRequest, BudgetState, SLODefinition
from store import store

router = APIRouter(prefix="/slo", tags=["slo"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_total_budget(target_availability: float, window_days: int) -> float:
    window_minutes = window_days * 24 * 60
    return (1.0 - target_availability) * window_minutes


@router.post("", response_model=SLODefinition, status_code=201)
async def define_slo(body: SLODefinition) -> SLODefinition:
    body.total_budget_minutes = _compute_total_budget(
        body.target_availability, body.window_days
    )
    existing = await store.get_slo(body.service_id)
    if existing:
        # preserve consumed budget
        consumed = existing.get("consumed_minutes", 0.0)
        slo_dict = body.model_dump()
        slo_dict["consumed_minutes"] = consumed
    else:
        slo_dict = body.model_dump()
        slo_dict["consumed_minutes"] = 0.0
    await store.set_slo(slo_dict)
    return body


@router.get("/{service_id}/budget", response_model=BudgetState)
async def get_budget(service_id: str) -> BudgetState:
    data = await store.get_slo(service_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"No SLO defined for {service_id!r}")
    total = data.get("total_budget_minutes", 0.0)
    consumed = data.get("consumed_minutes", 0.0)
    remaining = max(0.0, total - consumed)
    protection_score = (remaining / total) if total > 0 else 0.0
    return BudgetState(
        service_id=service_id,
        total_budget_minutes=total,
        consumed_minutes=consumed,
        remaining_minutes=remaining,
        protection_score=round(protection_score, 4),
    )


@router.post("/{service_id}/burn", response_model=BudgetState)
async def burn_budget(service_id: str, body: BudgetBurnRequest) -> BudgetState:
    data = await store.get_slo(service_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"No SLO defined for {service_id!r}")

    deduction = body.duration_minutes * body.impact_factor
    data["consumed_minutes"] = data.get("consumed_minutes", 0.0) + deduction
    await store.set_slo(data)

    burn_record = {
        "burn_id": str(uuid4()),
        "service_id": service_id,
        "source": body.source,
        "event_id": body.event_id,
        "duration_minutes": body.duration_minutes,
        "impact_factor": body.impact_factor,
        "deduction_minutes": deduction,
        "timestamp": _now(),
    }
    await store.record_burn(service_id, burn_record)

    total = data["total_budget_minutes"]
    consumed = data["consumed_minutes"]
    remaining = max(0.0, total - consumed)

    if remaining == 0.0:
        # Budget exhausted — future callers of get_budget will see protection_score=0
        pass

    return BudgetState(
        service_id=service_id,
        total_budget_minutes=total,
        consumed_minutes=consumed,
        remaining_minutes=remaining,
        protection_score=round((remaining / total) if total > 0 else 0.0, 4),
    )


@router.get("/{service_id}/burns")
async def get_burns(service_id: str, limit: int = 50) -> list[dict]:
    return await store.get_burns(service_id, limit=limit)
