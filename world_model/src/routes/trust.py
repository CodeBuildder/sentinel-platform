"""
Trust ledger routes.
GET  /trust/{action_type}        → current autonomy state
POST /trust/update               → update after outcome (promote / demote)
GET  /trust                      → all action types + states
GET  /trust/audit                → audit log
"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Query

from config import config
from models import TrustAuditEntry, TrustRecord, TrustState, TrustUpdateRequest
from store import store

router = APIRouter(prefix="/trust", tags=["trust"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("", response_model=list[TrustRecord])
async def list_trust() -> list[TrustRecord]:
    records = await store.all_trust_records()
    return [TrustRecord(**r) for r in records]


@router.get("/audit")
async def get_audit_log(
    action_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    return await store.get_audit_log(action_type=action_type, limit=limit)


@router.get("/{action_type}", response_model=TrustRecord)
async def get_trust(action_type: str) -> TrustRecord:
    data = await store.get_trust(action_type)
    if not data:
        # default: new action types are gated
        record = TrustRecord(action_type=action_type)
        await store.set_trust(record.model_dump())
        return record
    return TrustRecord(**data)


@router.post("/update", response_model=TrustRecord)
async def update_trust(body: TrustUpdateRequest) -> TrustRecord:
    data = await store.get_trust(body.action_type)
    record = TrustRecord(**data) if data else TrustRecord(action_type=body.action_type)

    state_before = record.state

    is_surprise = (
        body.outcome == "surprise"
        or (body.brier_score is not None and body.brier_score > config.TRUST_BRIER_SURPRISE_THRESHOLD)
    )

    if is_surprise:
        record.state = TrustState.GATED
        record.surprise_count += 1
        record.success_count = 0  # reset streak
        rationale = f"Surprise outcome (brier={body.brier_score}) — demoted to gated"
    else:
        record.success_count += 1
        if (
            record.state == TrustState.GATED
            and record.success_count >= config.TRUST_PROMOTE_THRESHOLD
        ):
            record.state = TrustState.AUTO
            rationale = f"Promoted after {record.success_count} consecutive successes"
        else:
            remaining = config.TRUST_PROMOTE_THRESHOLD - record.success_count
            rationale = (
                f"Success recorded ({record.success_count}/{config.TRUST_PROMOTE_THRESHOLD})"
                if remaining > 0
                else "Already auto"
            )

    record.last_updated = _now()
    await store.set_trust(record.model_dump())

    audit = TrustAuditEntry(
        entry_id=str(uuid4()),
        timestamp=_now(),
        action_type=body.action_type,
        decision=record.state.value,
        rationale=rationale,
        state_before=state_before.value,
        state_after=record.state.value,
    )
    await store.append_audit(audit.model_dump())

    return record
