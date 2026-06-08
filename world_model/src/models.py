"""
Pydantic models for the World Model service.
These mirror the JSON schemas but are typed for FastAPI request/response handling.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid4())


# ── Entity ────────────────────────────────────────────────────────────────────

class EntityType(str, Enum):
    SERVICE = "service"
    POD = "pod"
    NODE = "node"
    VOLUME = "volume"
    VLAN = "vlan"
    INSTANCE = "instance"


class SecurityPosture(str, Enum):
    CLEAN = "clean"
    LOW_RISK = "low-risk"
    MEDIUM_RISK = "medium-risk"
    HIGH_RISK = "high-risk"
    CRITICAL = "critical"


class Entity(BaseModel):
    entity_id: str
    entity_type: EntityType
    name: str
    namespace: str = "default"
    labels: dict[str, str] = Field(default_factory=dict)
    slo_target: float = 0.999
    error_budget_remaining_minutes: float = 0.0
    fragility_score: float = 0.0
    security_posture: SecurityPosture = SecurityPosture.CLEAN
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    deleted_at: str | None = None


class EntityCreate(BaseModel):
    entity_id: str | None = None
    entity_type: EntityType
    name: str
    namespace: str = "default"
    labels: dict[str, str] = Field(default_factory=dict)
    slo_target: float = 0.999


class EntityPatch(BaseModel):
    fragility_score: float | None = None
    security_posture: SecurityPosture | None = None
    error_budget_remaining_minutes: float | None = None
    slo_target: float | None = None


# ── Edge ──────────────────────────────────────────────────────────────────────

class EdgeType(str, Enum):
    DEPENDS_ON = "depends-on"
    RUNS_ON = "runs-on"
    ROUTES_THROUGH = "routes-through"


class Edge(BaseModel):
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 0.5
    created_at: str = Field(default_factory=_now)


class TopologyResponse(BaseModel):
    nodes: list[Entity]
    edges: list[Edge]


# ── Finding ───────────────────────────────────────────────────────────────────

class FindingIngest(BaseModel):
    """Shape of the payload POSTed to /findings."""
    event_id: str
    type: str = "finding"
    source: str
    timestamp: str
    entity_id: str | None = None
    severity: str | None = None
    correlation_id: str | None = None
    replayed: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


# ── Memory store ──────────────────────────────────────────────────────────────

class ActionRecord(BaseModel):
    action_type: str
    action_id: str
    outcome: str
    duration_ms: int = 0


class IncidentMemory(BaseModel):
    incident_id: str = Field(default_factory=_uuid)
    fault_fingerprint: str
    entity_id: str | None = None
    failure_mode: str | None = None
    actions_taken: list[ActionRecord] = Field(default_factory=list)
    outcome: str  # resolved | escalated | partial
    duration_ms: int
    was_prediction_correct: bool | None = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class CalibrationRecord(BaseModel):
    action_id: str
    action_type: str
    predicted_outcome: str
    actual_outcome: str
    brier_score: float | None = None
    timestamp: str = Field(default_factory=_now)


class CalibrationSummary(BaseModel):
    action_type: str
    record_count: int
    mean_brier_score: float
    low_confidence: bool  # True if mean_brier_score > SURPRISE_THRESHOLD


# ── Trust ledger ──────────────────────────────────────────────────────────────

class TrustState(str, Enum):
    AUTO = "auto"
    GATED = "gated"


class TrustRecord(BaseModel):
    action_type: str
    state: TrustState = TrustState.GATED
    success_count: int = 0
    surprise_count: int = 0
    last_updated: str = Field(default_factory=_now)


class TrustAuditEntry(BaseModel):
    entry_id: str = Field(default_factory=_uuid)
    timestamp: str = Field(default_factory=_now)
    action_type: str
    decision: str  # auto | gated
    rationale: str
    state_before: str
    state_after: str


class TrustUpdateRequest(BaseModel):
    action_type: str
    outcome: str  # success | surprise
    brier_score: float | None = None


# ── SLO / budget ─────────────────────────────────────────────────────────────

class SLODefinition(BaseModel):
    service_id: str
    target_availability: float  # 0-1
    latency_p99_ms: int = 500
    window_days: int = 30
    total_budget_minutes: float = 0.0  # computed on write


class BudgetBurnRequest(BaseModel):
    source: str  # "chaos" | "incident" | "enforcement"
    event_id: str
    duration_minutes: float
    impact_factor: float = 1.0  # multiplier for chaos experiments


class BudgetState(BaseModel):
    service_id: str
    total_budget_minutes: float
    consumed_minutes: float
    remaining_minutes: float
    protection_score: float  # remaining / total
