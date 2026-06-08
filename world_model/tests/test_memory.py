"""Tests for the shared memory store — incident memory, calibration."""

import pytest
from uuid import uuid4


async def test_write_and_read_incident_memory(client):
    payload = {
        "fault_fingerprint": "oom:pod/default/worker-1",
        "entity_id": "pod/default/worker-1",
        "failure_mode": "oom",
        "actions_taken": [
            {"action_type": "restart_pod", "action_id": str(uuid4()), "outcome": "success"}
        ],
        "outcome": "resolved",
        "duration_ms": 12000,
        "was_prediction_correct": True,
    }
    r = await client.post("/memory/incidents", json=payload)
    assert r.status_code == 200

    results = (await client.get("/memory/incidents?fault_fingerprint=oom:pod/default/worker-1")).json()
    assert len(results) == 1
    assert results[0]["fault_fingerprint"] == "oom:pod/default/worker-1"
    assert results[0]["confidence"] == 1.0  # 1 success / 1 action


async def test_incident_memory_upserts_on_same_fingerprint(client):
    fp = f"network-partition:{uuid4().hex}"
    for i in range(3):
        await client.post("/memory/incidents", json={
            "fault_fingerprint": fp,
            "outcome": "resolved",
            "duration_ms": 5000,
            "actions_taken": [
                {"action_type": "failover", "action_id": str(uuid4()), "outcome": "success"}
            ],
        })
    results = (await client.get(f"/memory/incidents?fault_fingerprint={fp}")).json()
    assert len(results) == 1  # upserted, not duplicated


async def test_calibration_write_and_read(client):
    r = await client.post("/memory/calibration", json={
        "action_id": str(uuid4()),
        "action_type": "restart_pod",
        "predicted_outcome": "resilient",
        "actual_outcome": "resilient",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["brier_score"] == 0.0  # correct prediction


async def test_calibration_wrong_prediction_brier_1(client):
    r = await client.post("/memory/calibration", json={
        "action_id": str(uuid4()),
        "action_type": "scale",
        "predicted_outcome": "resilient",
        "actual_outcome": "failed",
    })
    assert r.json()["brier_score"] == 1.0


async def test_calibration_summary(client):
    at = f"action-{uuid4().hex[:6]}"
    # 3 correct, 1 wrong → mean Brier = 0.25
    for _ in range(3):
        await client.post("/memory/calibration", json={
            "action_id": str(uuid4()),
            "action_type": at,
            "predicted_outcome": "resilient",
            "actual_outcome": "resilient",
        })
    await client.post("/memory/calibration", json={
        "action_id": str(uuid4()),
        "action_type": at,
        "predicted_outcome": "resilient",
        "actual_outcome": "failed",
    })
    resp = await client.get(f"/calibration?action_type={at}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["record_count"] == 4
    assert body["mean_brier_score"] == 0.25
