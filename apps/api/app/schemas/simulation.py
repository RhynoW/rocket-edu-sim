"""
apps.api.app.schemas.simulation
---------------------------------
Pydantic v2 request / response schemas for the simulation API.

These are *API-boundary* schemas — separate from the internal domain models
in rocket_core so that the API contract can evolve independently.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class EngineIn(BaseModel):
    name:       str   = "Merlin 1D"
    thrust_sl:  float = Field(845_000.0,  gt=0, description="Sea-level thrust per engine [N]")
    thrust_vac: float = Field(934_000.0,  gt=0, description="Vacuum thrust per engine [N]")
    isp_sl:     float = Field(282.0,      gt=0, description="Sea-level Isp [s]")
    isp_vac:    float = Field(311.0,      gt=0, description="Vacuum Isp [s]")
    mass:       float = Field(470.0,      gt=0, description="Engine dry mass [kg]")


class StageIn(BaseModel):
    dry_mass:       float = Field(..., gt=0, description="Stage dry mass [kg]")
    prop_mass:      float = Field(..., gt=0, description="Propellant mass [kg]")
    engine:         EngineIn
    engine_count:   int   = Field(1, ge=1)
    diameter_m:     float = Field(3.7, gt=0, description="Stage outer diameter [m]")


class MissionIn(BaseModel):
    target_altitude_km:     float = Field(400.0, gt=0, description="Target orbit altitude [km]")
    reusable_booster:       bool  = False
    reusable_penalty_kg:    float = Field(0.0, ge=0, description="Recovery hardware/propellant penalty [kg]")
    required_delta_v_m_s:   Optional[float] = Field(None, description="Override mission Δv [m/s]")


class PropellantIn(BaseModel):
    oxidiser:      str   = "LOX"
    fuel:          str   = "RP1"
    mixture_ratio: float = Field(2.56, gt=0, description="Oxidiser/fuel mass ratio")


class SimConfigIn(BaseModel):
    gravity_loss_estimate_m_s:  float = Field(1_200.0, ge=0)
    max_q_throttle_fraction:    float = Field(0.72, gt=0, le=1.0)
    run_trajectory:             bool  = True


class SimulationRequest(BaseModel):
    """Full simulation request body."""
    stage1:     StageIn
    stage2:     StageIn
    payload_mass:   float        = Field(...,   gt=0,  description="Payload mass [kg]")
    fairing_mass:   float        = Field(1_900.0, gt=0, description="Fairing mass [kg]")
    propellant:     PropellantIn = PropellantIn()
    mission:        MissionIn    = MissionIn()
    sim_config:     SimConfigIn  = SimConfigIn()


class SensitivityRequest(BaseModel):
    """Run a sweep of one parameter and return results for each step."""
    base: SimulationRequest
    parameter: str  = Field(
        ...,
        description=(
            "Dot-path to the parameter to sweep, e.g. 'stage2.dry_mass' "
            "or 'payload_mass'"
        ),
    )
    values: List[float] = Field(..., min_length=2, description="List of values to evaluate")


class BatchRequest(BaseModel):
    """Run multiple independent simulations in one request."""
    runs: List[SimulationRequest] = Field(..., min_length=1, max_length=50)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class StageResultOut(BaseModel):
    stage_id:              str
    m0_kg:                 float
    mf_kg:                 float
    mass_ratio:            float
    isp_effective_s:       float
    ideal_delta_v_m_s:     float
    burn_time_s:           float
    prop_consumed_kg:      float
    residual_propellant_kg: float


class StagingResultOut(BaseModel):
    stage1:                    StageResultOut
    stage2:                    StageResultOut
    total_ideal_delta_v_m_s:   float
    gravity_loss_m_s:          float
    drag_loss_m_s:             float
    steering_loss_m_s:         float
    total_losses_m_s:          float
    usable_delta_v_m_s:        float
    required_delta_v_m_s:      float
    delta_v_margin_m_s:        float
    mission_feasible:          bool
    events:                    List[Dict[str, Any]]


class MassBudgetOut(BaseModel):
    liftoff_mass_kg:    float
    total_dry_mass_kg:  float
    total_prop_mass_kg: float
    payload_mass_kg:    float
    fairing_mass_kg:    float
    payload_fraction:   float
    propellant_fraction: float
    structure_fraction: float
    liftoff_twr:        float
    fairing_penalty_kg: float
    recovery_penalty_kg: float


class PayloadResultOut(BaseModel):
    mission_feasible:       bool
    orbit_achieved:         bool
    payload_mass_kg:        float
    payload_fraction:       float
    usable_delta_v_m_s:     float
    required_delta_v_m_s:   float
    margin_to_orbit_m_s:    float
    achievable_orbit_km:    float
    max_payload_kg:         Optional[float]
    limiting_factor:        str
    sensitivity_hints:      List[str]


class ConstraintResultOut(BaseModel):
    name:     str
    severity: str   # "ok" | "warning" | "error"
    passed:   bool
    message:  str
    value:    Optional[float] = None
    limit:    Optional[float] = None
    unit:     str = ""


class TrajectoryPointOut(BaseModel):
    t_s:         float
    altitude_km: float
    downrange_km: float
    velocity_m_s: float
    mass_kg:     float
    phase:       str


class TrajectoryResultOut(BaseModel):
    apogee_km:               float
    max_velocity_m_s:        float
    max_q_Pa:                float
    orbit_achieved:          bool
    final_altitude_km:       float
    final_velocity_m_s:      float
    trajectory:              List[TrajectoryPointOut]


class SimulationResponse(BaseModel):
    """Complete simulation response."""
    ok:          bool
    errors:      List[str]  = []
    warnings:    List[str]  = []

    # Solver outputs (populated when ok=True)
    mass_budget:  Optional[MassBudgetOut]      = None
    staging:      Optional[StagingResultOut]   = None
    payload:      Optional[PayloadResultOut]   = None
    trajectory:   Optional[TrajectoryResultOut] = None
    constraints:  List[ConstraintResultOut]    = []


class SensitivityPoint(BaseModel):
    parameter_value:    float
    payload_mass_kg:    float
    max_payload_kg:     Optional[float]
    delta_v_margin_m_s: float
    mission_feasible:   bool
    limiting_factor:    str


class SensitivityResponse(BaseModel):
    parameter:  str
    points:     List[SensitivityPoint]


class BatchResponse(BaseModel):
    results: List[SimulationResponse]
