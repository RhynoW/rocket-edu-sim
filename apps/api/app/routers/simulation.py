"""
apps.api.app.routers.simulation
---------------------------------
FastAPI router for all simulation endpoints.

Endpoints:
  POST /api/simulate            — run full simulation pipeline
  POST /api/sensitivity         — parameter sweep
  POST /api/simulate/batch      — run N independent simulations
  GET  /api/templates           — list available vehicle templates
  GET  /api/templates/{name}    — fetch a specific vehicle template
  GET  /api/engines             — list available engine definitions
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, status

from apps.api.app.schemas.simulation import (
    SimulationRequest, SimulationResponse,
    SensitivityRequest, SensitivityResponse,
    BatchRequest, BatchResponse,
)
from apps.api.app.services.simulation import run_simulation, run_sensitivity, run_batch

router = APIRouter(prefix="/api", tags=["simulation"])

# Data directory (relative to repo root)
_DATA_DIR = Path(__file__).resolve().parents[5] / "data"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Any:
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Data file not found: {path.name}",
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Simulation endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/simulate",
    response_model=SimulationResponse,
    summary="Run full simulation pipeline",
    description=(
        "Accepts a vehicle configuration and mission parameters, "
        "runs the propulsion → mass budget → staging → trajectory → payload "
        "→ constraints pipeline, and returns all results."
    ),
)
async def simulate(req: SimulationRequest) -> SimulationResponse:
    return run_simulation(req)


@router.post(
    "/sensitivity",
    response_model=SensitivityResponse,
    summary="Parameter sensitivity sweep",
    description=(
        "Sweep one vehicle parameter over a list of values. "
        "Returns payload and Δv metrics at each point."
    ),
)
async def sensitivity(req: SensitivityRequest) -> SensitivityResponse:
    return run_sensitivity(req)


@router.post(
    "/simulate/batch",
    response_model=BatchResponse,
    summary="Run multiple simulations",
    description="Execute up to 50 independent simulations in a single request.",
)
async def batch(req: BatchRequest) -> BatchResponse:
    return run_batch(req)


# ---------------------------------------------------------------------------
# Template / catalog endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/templates",
    response_model=List[Dict[str, Any]],
    summary="List available vehicle templates",
)
async def list_templates() -> List[Dict[str, Any]]:
    templates_dir = _DATA_DIR / "templates"
    if not templates_dir.exists():
        return []
    result = []
    for f in sorted(templates_dir.glob("*.json")):
        data = _load_json(f)
        result.append({
            "id":          f.stem,
            "name":        data.get("name", f.stem),
            "description": data.get("description", ""),
        })
    return result


@router.get(
    "/templates/{template_id}",
    response_model=Dict[str, Any],
    summary="Fetch a vehicle template by ID",
)
async def get_template(template_id: str) -> Dict[str, Any]:
    # Sanitise: only allow simple alphanumeric + underscores/hyphens
    safe_id = "".join(c for c in template_id if c.isalnum() or c in ("-", "_"))
    path = _DATA_DIR / "templates" / f"{safe_id}.json"
    return _load_json(path)


@router.get(
    "/engines",
    response_model=List[Dict[str, Any]],
    summary="List available engine definitions",
)
async def list_engines() -> List[Dict[str, Any]]:
    path = _DATA_DIR / "engines" / "merlin_catalog.json"
    data = _load_json(path)
    # Expect a top-level list or {"engines": [...]}
    if isinstance(data, list):
        return data
    return data.get("engines", [])
