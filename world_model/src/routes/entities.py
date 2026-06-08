"""
Entity and topology routes.
GET  /topology              → nodes + edges
GET  /entities/{id}         → single entity
POST /entities              → create/update entity
POST /edges                 → create/update edge
GET  /fragility             → top-N by fragility score
GET  /blast-radius          → downstream entities
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from graph import graph
from models import Edge, EdgeType, Entity, EntityCreate, EntityPatch, TopologyResponse
from store import store

router = APIRouter(tags=["topology"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/topology", response_model=TopologyResponse)
async def get_topology() -> TopologyResponse:
    entities = await store.all_entities()
    edges = await store.all_edges()
    return TopologyResponse(
        nodes=[Entity(**e) for e in entities if not e.get("deleted_at")],
        edges=[Edge(**e) for e in edges],
    )


@router.get("/entities/{entity_id}", response_model=Entity)
async def get_entity(entity_id: str) -> Entity:
    data = await store.get_entity(entity_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id!r} not found")
    return Entity(**data)


@router.post("/entities", response_model=Entity, status_code=201)
async def upsert_entity(body: EntityCreate) -> Entity:
    existing = await store.get_entity(body.entity_id) if body.entity_id else None
    if existing:
        entity = Entity(**existing)
        for field, val in body.model_dump(exclude_none=True, exclude={"entity_id"}).items():
            setattr(entity, field, val)
        entity.updated_at = _now()
    else:
        from uuid import uuid4
        eid = body.entity_id or f"{body.entity_type.value}/{body.namespace}/{body.name}-{uuid4().hex[:8]}"
        entity = Entity(
            entity_id=eid,
            entity_type=body.entity_type,
            name=body.name,
            namespace=body.namespace,
            labels=body.labels,
            slo_target=body.slo_target,
        )

    await store.upsert_entity(entity.model_dump())
    graph.add_entity(entity.model_dump())
    return entity


@router.patch("/entities/{entity_id}", response_model=Entity)
async def patch_entity(entity_id: str, body: EntityPatch) -> Entity:
    data = await store.get_entity(entity_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id!r} not found")
    entity = Entity(**data)
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(entity, field, val)
    entity.updated_at = _now()
    await store.upsert_entity(entity.model_dump())
    graph.add_entity(entity.model_dump())
    return entity


@router.post("/edges", response_model=Edge, status_code=201)
async def upsert_edge(body: Edge) -> Edge:
    src = await store.get_entity(body.source_id)
    tgt = await store.get_entity(body.target_id)
    if not src:
        raise HTTPException(status_code=422, detail=f"Source entity {body.source_id!r} not found")
    if not tgt:
        raise HTTPException(status_code=422, detail=f"Target entity {body.target_id!r} not found")

    _ALLOWED: dict[EdgeType, tuple[list[str], list[str]]] = {
        EdgeType.DEPENDS_ON: (["service", "pod"], ["service", "pod", "volume"]),
        EdgeType.RUNS_ON:    (["pod"],             ["node"]),
        EdgeType.ROUTES_THROUGH: (["service"],     ["vlan", "service"]),
    }
    allowed_src, allowed_tgt = _ALLOWED[body.edge_type]
    if src["entity_type"] not in allowed_src or tgt["entity_type"] not in allowed_tgt:
        raise HTTPException(
            status_code=422,
            detail=f"Edge type {body.edge_type} not allowed between {src['entity_type']} → {tgt['entity_type']}",
        )

    await store.upsert_edge(body.model_dump())
    graph.add_edge(body.model_dump())
    return body


@router.get("/fragility")
async def get_fragility(top: int = Query(default=10, ge=1, le=100)) -> list[dict]:
    scored = graph.top_fragile(top)
    result = []
    for entity_id, fragility_score in scored:
        data = await store.get_entity(entity_id)
        if data and not data.get("deleted_at"):
            result.append({"entity_id": entity_id, "fragility_score": fragility_score, **data})
    return result


@router.get("/blast-radius")
async def get_blast_radius(entity_id: str = Query(...)) -> dict:
    downstream = graph.blast_radius(entity_id)
    return {
        "entity_id": entity_id,
        "blast_radius": {
            "entity_count": len(downstream),
            "entity_ids": downstream,
        },
    }
