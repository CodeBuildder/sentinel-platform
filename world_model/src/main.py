"""
World Model service — FastAPI entrypoint.
Copyright (c) 2026 Kaushikkumaran

The single source of truth for the Sentinel platform. Owns:
  - Entity + topology graph (nodes, edges, fragility, blast-radius)
  - Finding write API (idempotent ingestion from Argus + Phoenix)
  - Shared memory store (incident memory + calibration)
  - Trust ledger (autonomy state per action type)
  - SLO / error-budget engine
  - Incident lifecycle

All Argus and Phoenix agents read from and write to this service.
The Sentinel correlation engine reads topology and findings from here.
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import config
from graph import graph
from routes.calibration import router as calibration_router
from routes.entities import router as entities_router
from routes.findings import router as findings_router
from routes.incidents import router as incidents_router
from routes.memory import router as memory_router
from routes.slo import router as slo_router
from routes.trust import router as trust_router
from store import store

logging.basicConfig(level=logging.INFO)
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("world_model_starting", redis=config.REDIS_URL)
    await store.connect()

    # Rebuild in-memory topology graph from persisted state
    entities = await store.all_entities()
    edges = await store.all_edges()
    graph.rebuild(entities, edges)
    log.info("topology_loaded", nodes=len(entities), edges=len(edges))

    yield

    await store.close()
    log.info("world_model_stopped")


app = FastAPI(
    title="Sentinel World Model",
    description=(
        "Shared state service for the Sentinel platform. "
        "Single source of truth for topology, findings, SLOs, trust, and memory."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(entities_router)
app.include_router(findings_router)
app.include_router(memory_router)
app.include_router(trust_router)
app.include_router(slo_router)
app.include_router(incidents_router)
app.include_router(calibration_router)


@app.get("/health")
async def health() -> dict:
    redis_ok = await store.ping()
    return {
        "status": "ok" if redis_ok else "degraded",
        "service": config.SERVICE_NAME,
        "version": "0.1.0",
        "topology": {
            "nodes": graph.node_count,
        },
        "redis": "ok" if redis_ok else "unreachable",
    }


@app.get("/metrics")
async def metrics() -> str:
    """Minimal Prometheus-format metrics."""
    node_count = graph.node_count
    return (
        "# HELP wm_topology_nodes Current number of entities in the topology graph\n"
        "# TYPE wm_topology_nodes gauge\n"
        f"wm_topology_nodes {node_count}\n"
    )
