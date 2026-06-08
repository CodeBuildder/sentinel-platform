"""Tests for entity CRUD, topology, fragility, and blast-radius."""

import pytest


async def test_create_entity(client):
    resp = await client.post("/entities", json={
        "entity_type": "service",
        "name": "payment-api",
        "namespace": "prod",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["entity_type"] == "service"
    assert body["name"] == "payment-api"
    assert "entity_id" in body


async def test_topology_returns_created_entities(client):
    await client.post("/entities", json={"entity_type": "pod", "name": "worker-1", "namespace": "default"})
    await client.post("/entities", json={"entity_type": "node", "name": "node-a", "namespace": "cluster"})

    resp = await client.get("/topology")
    assert resp.status_code == 200
    body = resp.json()
    names = [n["name"] for n in body["nodes"]]
    assert "worker-1" in names
    assert "node-a" in names


async def test_fragility_ranking(client):
    r1 = await client.post("/entities", json={"entity_type": "service", "name": "svc-a", "namespace": "ns"})
    r2 = await client.post("/entities", json={"entity_type": "service", "name": "svc-b", "namespace": "ns"})
    id_a = r1.json()["entity_id"]
    id_b = r2.json()["entity_id"]

    # set fragility scores
    await client.patch(f"/entities/{id_a}", json={"fragility_score": 0.9})
    await client.patch(f"/entities/{id_b}", json={"fragility_score": 0.3})

    resp = await client.get("/fragility?top=5")
    assert resp.status_code == 200
    results = resp.json()
    assert results[0]["entity_id"] == id_a  # highest fragility first


async def test_blast_radius_follows_depends_on_edges(client):
    r_svc = await client.post("/entities", json={"entity_type": "service", "name": "frontend", "namespace": "ns"})
    r_db = await client.post("/entities", json={"entity_type": "service", "name": "db", "namespace": "ns"})
    svc_id = r_svc.json()["entity_id"]
    db_id = r_db.json()["entity_id"]

    # frontend depends-on db
    await client.post("/edges", json={
        "source_id": svc_id,
        "target_id": db_id,
        "edge_type": "depends-on",
    })

    resp = await client.get(f"/blast-radius?entity_id={svc_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert db_id in body["blast_radius"]["entity_ids"]


async def test_invalid_edge_type_rejected(client):
    r1 = await client.post("/entities", json={"entity_type": "node", "name": "n1", "namespace": "cluster"})
    r2 = await client.post("/entities", json={"entity_type": "service", "name": "s1", "namespace": "ns"})
    resp = await client.post("/edges", json={
        "source_id": r1.json()["entity_id"],
        "target_id": r2.json()["entity_id"],
        "edge_type": "runs-on",  # node cannot be source for runs-on
    })
    assert resp.status_code == 422


async def test_empty_blast_radius_for_unknown_entity(client):
    resp = await client.get("/blast-radius?entity_id=nonexistent")
    assert resp.status_code == 200
    assert resp.json()["blast_radius"]["entity_count"] == 0
