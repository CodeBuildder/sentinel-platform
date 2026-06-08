"""
Redis-backed state store for the World Model.

Key layout:
  wm:entity:{entity_id}          → JSON blob (Entity)
  wm:entities                    → SET of all entity_ids
  wm:edge:{src}:{tgt}:{type}     → JSON blob (Edge)
  wm:edges:{entity_id}           → SET of edge keys originating from entity_id
  wm:finding:{event_id}          → JSON blob (idempotency store, TTL 7d)
  wm:memory:incident:{fingerprint} → JSON blob (IncidentMemory, upsert on fingerprint)
  wm:memory:calibration:{action_type} → LIST of CalibrationRecord JSON (LPUSH, capped)
  wm:trust:{action_type}         → JSON blob (TrustRecord)
  wm:trust:audit                 → LIST of TrustAuditEntry JSON (LPUSH, capped at 10k)
  wm:slo:{service_id}            → JSON blob (SLODefinition + budget state)
  wm:slo:burns:{service_id}      → LIST of burn event JSON (LPUSH, capped)
  wm:incident:{incident_id}      → JSON blob (incident payload)
  wm:incidents:open              → SET of incident_ids with state=open
"""

import json
from typing import Any

import redis.asyncio as aioredis

FINDING_TTL_SECONDS = 7 * 86_400
CALIBRATION_CAP = 500
AUDIT_CAP = 10_000
BURNS_CAP = 10_000


class Store:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self._url = redis_url
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._redis = await aioredis.from_url(
            self._url, encoding="utf-8", decode_responses=True
        )

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    @property
    def r(self) -> aioredis.Redis:
        assert self._redis is not None, "Store.connect() not called"
        return self._redis

    # ── entities ──────────────────────────────────────────────────────────────

    async def upsert_entity(self, entity: dict) -> None:
        eid = entity["entity_id"]
        async with self.r.pipeline() as pipe:
            pipe.set(f"wm:entity:{eid}", json.dumps(entity))
            pipe.sadd("wm:entities", eid)
            await pipe.execute()

    async def get_entity(self, entity_id: str) -> dict | None:
        raw = await self.r.get(f"wm:entity:{entity_id}")
        return json.loads(raw) if raw else None

    async def all_entities(self) -> list[dict]:
        ids = await self.r.smembers("wm:entities")
        if not ids:
            return []
        keys = [f"wm:entity:{eid}" for eid in ids]
        raws = await self.r.mget(keys)
        return [json.loads(r) for r in raws if r]

    async def tombstone_entity(self, entity_id: str, deleted_at: str) -> None:
        raw = await self.r.get(f"wm:entity:{entity_id}")
        if raw:
            entity = json.loads(raw)
            entity["deleted_at"] = deleted_at
            await self.r.set(f"wm:entity:{entity_id}", json.dumps(entity))

    # ── edges ─────────────────────────────────────────────────────────────────

    async def upsert_edge(self, edge: dict) -> None:
        key = f"wm:edge:{edge['source_id']}:{edge['target_id']}:{edge['edge_type']}"
        async with self.r.pipeline() as pipe:
            pipe.set(key, json.dumps(edge))
            pipe.sadd(f"wm:edges:{edge['source_id']}", key)
            await pipe.execute()

    async def edges_from(self, entity_id: str) -> list[dict]:
        keys = await self.r.smembers(f"wm:edges:{entity_id}")
        if not keys:
            return []
        raws = await self.r.mget(list(keys))
        return [json.loads(r) for r in raws if r]

    async def all_edges(self) -> list[dict]:
        entity_ids = await self.r.smembers("wm:entities")
        edges: list[dict] = []
        for eid in entity_ids:
            edges.extend(await self.edges_from(eid))
        return edges

    # ── findings (idempotency) ─────────────────────────────────────────────────

    async def finding_exists(self, event_id: str) -> bool:
        return await self.r.exists(f"wm:finding:{event_id}") > 0

    async def store_finding(self, event: dict) -> None:
        await self.r.set(
            f"wm:finding:{event['event_id']}",
            json.dumps(event),
            ex=FINDING_TTL_SECONDS,
        )

    async def get_findings_for_entity(self, entity_id: str, limit: int = 50) -> list[dict]:
        """Scan findings by entity_id. Not indexed — only for small clusters."""
        cursor = 0
        results: list[dict] = []
        while True:
            cursor, keys = await self.r.scan(cursor, match="wm:finding:*", count=200)
            if keys:
                raws = await self.r.mget(keys)
                for r in raws:
                    if r:
                        ev = json.loads(r)
                        if ev.get("entity_id") == entity_id:
                            results.append(ev)
                            if len(results) >= limit:
                                return results
            if cursor == 0:
                break
        return results

    # ── incident memory ────────────────────────────────────────────────────────

    async def upsert_incident_memory(self, record: dict) -> None:
        fp = record["fault_fingerprint"]
        await self.r.set(f"wm:memory:incident:{fp}", json.dumps(record))

    async def get_incident_memory(self, fault_fingerprint: str) -> dict | None:
        raw = await self.r.get(f"wm:memory:incident:{fault_fingerprint}")
        return json.loads(raw) if raw else None

    async def list_incident_memories(
        self, fault_fingerprint: str | None = None, limit: int = 20
    ) -> list[dict]:
        if fault_fingerprint:
            rec = await self.get_incident_memory(fault_fingerprint)
            return [rec] if rec else []
        cursor = 0
        results: list[dict] = []
        while True:
            cursor, keys = await self.r.scan(
                cursor, match="wm:memory:incident:*", count=200
            )
            if keys:
                raws = await self.r.mget(keys)
                for r in raws:
                    if r:
                        results.append(json.loads(r))
                        if len(results) >= limit:
                            return results
            if cursor == 0:
                break
        return results

    # ── calibration ───────────────────────────────────────────────────────────

    async def push_calibration(self, action_type: str, record: dict) -> None:
        key = f"wm:memory:calibration:{action_type}"
        await self.r.lpush(key, json.dumps(record))
        await self.r.ltrim(key, 0, CALIBRATION_CAP - 1)

    async def get_calibration_records(
        self, action_type: str, limit: int = 100
    ) -> list[dict]:
        key = f"wm:memory:calibration:{action_type}"
        raws = await self.r.lrange(key, 0, limit - 1)
        return [json.loads(r) for r in raws]

    # ── trust ledger ──────────────────────────────────────────────────────────

    async def get_trust(self, action_type: str) -> dict | None:
        raw = await self.r.get(f"wm:trust:{action_type}")
        return json.loads(raw) if raw else None

    async def set_trust(self, record: dict) -> None:
        await self.r.set(f"wm:trust:{record['action_type']}", json.dumps(record))

    async def all_trust_records(self) -> list[dict]:
        cursor = 0
        results: list[dict] = []
        while True:
            cursor, keys = await self.r.scan(cursor, match="wm:trust:*", count=200)
            filtered = [k for k in keys if not k.endswith(":audit")]
            if filtered:
                raws = await self.r.mget(filtered)
                results.extend(json.loads(r) for r in raws if r)
            if cursor == 0:
                break
        return results

    async def append_audit(self, entry: dict) -> None:
        await self.r.lpush("wm:trust:audit", json.dumps(entry))
        await self.r.ltrim("wm:trust:audit", 0, AUDIT_CAP - 1)

    async def get_audit_log(
        self, action_type: str | None = None, limit: int = 100
    ) -> list[dict]:
        raws = await self.r.lrange("wm:trust:audit", 0, limit * 5)
        entries = [json.loads(r) for r in raws]
        if action_type:
            entries = [e for e in entries if e.get("action_type") == action_type]
        return entries[:limit]

    # ── SLO / error budget ────────────────────────────────────────────────────

    async def get_slo(self, service_id: str) -> dict | None:
        raw = await self.r.get(f"wm:slo:{service_id}")
        return json.loads(raw) if raw else None

    async def set_slo(self, slo: dict) -> None:
        await self.r.set(f"wm:slo:{slo['service_id']}", json.dumps(slo))

    async def record_burn(self, service_id: str, burn: dict) -> None:
        key = f"wm:slo:burns:{service_id}"
        await self.r.lpush(key, json.dumps(burn))
        await self.r.ltrim(key, 0, BURNS_CAP - 1)

    async def get_burns(self, service_id: str, limit: int = 100) -> list[dict]:
        raws = await self.r.lrange(f"wm:slo:burns:{service_id}", 0, limit - 1)
        return [json.loads(r) for r in raws]

    # ── incidents ─────────────────────────────────────────────────────────────

    async def upsert_incident(self, incident: dict) -> None:
        iid = incident["payload"]["incident_id"]
        await self.r.set(f"wm:incident:{iid}", json.dumps(incident))
        state = incident["payload"].get("state", "open")
        if state == "open" or state == "correlating":
            await self.r.sadd("wm:incidents:open", iid)
        else:
            await self.r.srem("wm:incidents:open", iid)

    async def get_incident(self, incident_id: str) -> dict | None:
        raw = await self.r.get(f"wm:incident:{incident_id}")
        return json.loads(raw) if raw else None

    async def list_open_incidents(self) -> list[dict]:
        ids = await self.r.smembers("wm:incidents:open")
        if not ids:
            return []
        keys = [f"wm:incident:{iid}" for iid in ids]
        raws = await self.r.mget(keys)
        return [json.loads(r) for r in raws if r]

    # ── generic ───────────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        try:
            return await self.r.ping()
        except Exception:
            return False


store = Store()
