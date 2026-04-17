"""
apps.api.app.main
------------------
FastAPI application entry point.

Run with:
    uvicorn apps.api.app.main:app --reload --host 0.0.0.0 --port 8000

Or from the repo root:
    cd rocket-edu-sim
    uvicorn apps.api.app.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.routers.simulation import router as simulation_router

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Falcon 9-like Rocket Educational Simulator",
    description=(
        "API for a two-stage launch vehicle educational simulator. "
        "Computes Δv budgets, mass fractions, payload capability, "
        "and 2D gravity-turn trajectory for Falcon 9-inspired configurations."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow the Vite dev server (port 5173) and any localhost origin in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(simulation_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "service": "rocket-edu-sim-api"}


@app.get("/", tags=["system"])
async def root() -> dict:
    return {
        "message": "Rocket Educational Simulator API",
        "docs":    "/docs",
        "health":  "/health",
    }
