"""Tests for the trust ledger — promotion, demotion, audit log."""

import pytest


async def test_new_action_type_defaults_to_gated(client):
    resp = await client.get("/trust/pod-kill")
    assert resp.status_code == 200
    assert resp.json()["state"] == "gated"


async def test_five_successes_promote_to_auto(client):
    for _ in range(5):
        await client.post("/trust/update", json={"action_type": "scale", "outcome": "success"})
    resp = await client.get("/trust/scale")
    assert resp.json()["state"] == "auto"


async def test_surprise_demotes_to_gated(client):
    # Promote first
    for _ in range(5):
        await client.post("/trust/update", json={"action_type": "restart", "outcome": "success"})
    assert (await client.get("/trust/restart")).json()["state"] == "auto"

    # Surprise demotes
    await client.post("/trust/update", json={"action_type": "restart", "outcome": "surprise"})
    assert (await client.get("/trust/restart")).json()["state"] == "gated"


async def test_high_brier_score_demotes(client):
    for _ in range(5):
        await client.post("/trust/update", json={"action_type": "failover", "outcome": "success"})
    assert (await client.get("/trust/failover")).json()["state"] == "auto"

    await client.post("/trust/update", json={
        "action_type": "failover",
        "outcome": "success",
        "brier_score": 0.9,
    })
    assert (await client.get("/trust/failover")).json()["state"] == "gated"


async def test_audit_log_records_transitions(client):
    for _ in range(5):
        await client.post("/trust/update", json={"action_type": "circuit-break", "outcome": "success"})
    audit = (await client.get("/trust/audit?action_type=circuit-break")).json()
    states = [e["state_after"] for e in audit]
    assert "auto" in states
