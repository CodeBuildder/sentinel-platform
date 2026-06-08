"""Tests for POST /findings — schema validation and idempotency."""

import pytest
from uuid import uuid4


def _finding(entity_id="pod/default/app-abc", severity="high", override=None):
    ev = {
        "event_id": str(uuid4()),
        "type": "finding",
        "source": "phoenix",
        "timestamp": "2026-06-08T00:00:00Z",
        "entity_id": entity_id,
        "severity": severity,
        "payload": {"finding_type": "oom", "description": "OOM kill detected"},
    }
    if override:
        ev.update(override)
    return ev


async def test_valid_finding_accepted(client):
    resp = await client.post("/findings", json=_finding())
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


async def test_duplicate_finding_returns_200(client):
    ev = _finding()
    r1 = await client.post("/findings", json=ev)
    r2 = await client.post("/findings", json=ev)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"


async def test_missing_required_field_returns_422(client):
    ev = _finding()
    del ev["event_id"]  # event_id has no default — must be present
    resp = await client.post("/findings", json=ev)
    assert resp.status_code == 422


async def test_unknown_source_returns_422(client):
    ev = _finding(override={"source": "unknown-agent"})
    resp = await client.post("/findings", json=ev)
    assert resp.status_code == 422


async def test_unknown_event_type_returns_422(client):
    ev = _finding(override={"type": "mystery"})
    resp = await client.post("/findings", json=ev)
    assert resp.status_code == 422


async def test_finding_from_argus_accepted(client):
    ev = _finding(override={"source": "argus", "severity": "critical"})
    resp = await client.post("/findings", json=ev)
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
