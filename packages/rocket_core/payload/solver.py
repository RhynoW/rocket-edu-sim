"""
rocket_core.payload.solver
---------------------------
Integrates upstream solver outputs (mass budget + staging) into the
student-facing payload capability estimate.

Key outputs:
  - payload_to_target_orbit_kg   : can this vehicle reach the target?
  - payload_fraction             : payload / liftoff_mass
  - margin_to_orbit_m_s          : spare delta-v after reaching target orbit
  - limiting_factor              : which constraint is binding (stage2_dry,
                                   stage1_thrust, total_prop, …)
  - achievable_orbit_km          : highest circular orbit reachable with
                                   current payload, regardless of target

Educational note:
  Stage 2 dry mass is the dominant lever:
    d(payload) / d(m2_dry) ≈ -1  (almost 1:1 mass exchange)
  Stage 1 dry mass is ~3–4× less sensitive due to mass ratio compounding.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from rocket_core.vehicle.models import Vehicle
from rocket_core.staging.solver import StagingResult, _tsiolkovsky, _required_delta_v, G0

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class PayloadResult:
    """Payload capability summary."""

    # Mission feasibility
    mission_feasible:        bool
    orbit_achieved:          bool   # from trajectory (if run); else from delta-v check

    # Payload numbers
    payload_mass_kg:         float  # as configured
    payload_fraction:        float  # payload / liftoff_mass

    # Delta-v breakdown
    usable_delta_v_m_s:      float
    required_delta_v_m_s:    float
    margin_to_orbit_m_s:     float  # positive = margin, negative = shortfall

    # Achievable orbit (what orbit can we actually reach?)
    achievable_orbit_km:     float

    # Maximum payload this vehicle could carry to the target orbit
    max_payload_kg:          Optional[float]

    # What's holding us back?
    limiting_factor:         str    # e.g. "stage2_dry_mass", "stage1_thrust", "feasible"

    # Sensitivity hints for the UI
    sensitivity_hints: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GM  = 3.986_004_418e14
_R_E = 6_371_000.0


def _circular_orbit_velocity(altitude_km: float) -> float:
    h = altitude_km * 1_000.0
    return math.sqrt(_GM / (_R_E + h))


def _max_altitude_for_dv(usable_dv_m_s: float) -> float:
    """
    Invert:  v_circular(h) + losses = usable_dv
    => v_circular = usable_dv - losses
    => h = GM / v_c^2 - R_E
    Returns altitude in km.
    """
    from rocket_core.staging.solver import (
        DEFAULT_GRAVITY_LOSS_M_S, DEFAULT_DRAG_LOSS_M_S, DEFAULT_STEERING_LOSS_M_S
    )
    total_losses = DEFAULT_GRAVITY_LOSS_M_S + DEFAULT_DRAG_LOSS_M_S + DEFAULT_STEERING_LOSS_M_S
    v_c = usable_dv_m_s - total_losses
    if v_c <= 0:
        return 0.0
    h = _GM / v_c**2 - _R_E
    return max(h / 1_000.0, 0.0)


def _max_payload_for_target(
    vehicle: Vehicle,
    staging: StagingResult,
    target_altitude_km: float,
) -> Optional[float]:
    """
    Binary-search for the maximum payload that still meets the target orbit Δv.
    Returns None if even payload=0 is infeasible.
    """
    from rocket_core.vehicle.models import Vehicle as V
    from rocket_core.staging.solver import solve_staging

    req_dv = _required_delta_v(target_altitude_km)

    # Quick feasibility check at zero payload
    test_vehicle = vehicle.model_copy(update={"payload_mass": 0.0})
    test_staging = solve_staging(test_vehicle)
    if test_staging.usable_delta_v_m_s < req_dv:
        return None  # vehicle cannot reach orbit even without payload

    # Binary search between 0 and (current payload * 3) for max feasible payload
    lo, hi = 0.0, vehicle.payload_mass * 3.0 + 10_000.0
    for _ in range(30):
        mid = (lo + hi) / 2
        tv  = vehicle.model_copy(update={"payload_mass": mid})
        ts  = solve_staging(tv)
        if ts.usable_delta_v_m_s >= req_dv:
            lo = mid
        else:
            hi = mid
    return round(lo, 0)


def _determine_limiting_factor(vehicle: Vehicle, staging: StagingResult) -> str:
    """Identify which design parameter is closest to its limit."""
    twr = vehicle.liftoff_twr

    if twr < 1.2:
        return "stage1_thrust_too_low"
    if vehicle.stage2.structure_fraction > 0.10:
        return "stage2_dry_mass_high"
    if vehicle.stage1.structure_fraction > 0.10:
        return "stage1_dry_mass_high"
    if staging.delta_v_margin_m_s < 0:
        return "insufficient_total_delta_v"
    if staging.delta_v_margin_m_s < 200:
        return "low_delta_v_margin"
    return "feasible"


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def estimate_payload(vehicle: Vehicle, staging: StagingResult) -> PayloadResult:
    """
    Derive payload capability metrics from a completed staging result.

    Parameters
    ----------
    vehicle  : Vehicle
    staging  : StagingResult  (output of solve_staging)

    Returns
    -------
    PayloadResult
    """
    mis = vehicle.mission
    tgt_alt = mis.target_altitude_km

    usable_dv = staging.usable_delta_v_m_s
    req_dv    = staging.required_delta_v_m_s
    margin    = staging.delta_v_margin_m_s
    feasible  = staging.mission_feasible

    # What's the highest orbit we can reach with this payload?
    achievable_alt_km = _max_altitude_for_dv(usable_dv)

    # Maximum payload to target orbit
    max_pl = _max_payload_for_target(vehicle, staging, tgt_alt)

    limiting = _determine_limiting_factor(vehicle, staging)

    # Build educational sensitivity hints
    hints: List[str] = []
    s2_sf = vehicle.stage2.structure_fraction
    if s2_sf > 0.07:
        hints.append(
            f"Stage 2 structure fraction is {s2_sf:.3f} — "
            f"reducing Stage 2 dry mass by 500 kg would add ~500 kg of payload."
        )
    if vehicle.liftoff_twr < 1.35:
        hints.append(
            f"Liftoff T/W = {vehicle.liftoff_twr:.2f} is low. "
            f"Consider adding engines or reducing liftoff mass."
        )
    if vehicle.mission.reusable_booster and vehicle.mission.reusable_penalty_kg > 0:
        hints.append(
            f"Reusable booster mode carries a {vehicle.mission.reusable_penalty_kg:.0f} kg penalty. "
            f"Switching to expendable would recover this as payload."
        )
    if margin < 300 and feasible:
        hints.append(
            f"Delta-v margin is only {margin:.0f} m/s. "
            f"Consider increasing Stage 2 propellant or Isp."
        )

    return PayloadResult(
        mission_feasible       = feasible,
        orbit_achieved         = feasible,
        payload_mass_kg        = vehicle.payload_mass,
        payload_fraction       = vehicle.payload_mass / vehicle.liftoff_mass_kg,
        usable_delta_v_m_s     = round(usable_dv, 1),
        required_delta_v_m_s   = round(req_dv, 1),
        margin_to_orbit_m_s    = round(margin, 1),
        achievable_orbit_km    = round(achievable_alt_km, 1),
        max_payload_kg         = max_pl,
        limiting_factor        = limiting,
        sensitivity_hints      = hints,
    )
