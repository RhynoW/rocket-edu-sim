"""
rocket_core.staging.solver
---------------------------
Applies the Tsiolkovsky (ideal rocket) equation stage by stage and
computes mission delta-v budget, residuals, and event log.

Tsiolkovsky rocket equation:
    Δv = Isp * g0 * ln(m0 / mf)

Where:
    m0 = initial (wet) mass of the stage stack
    mf = final (burnout) mass after expending propellant

Two-stage ascent sequence modelled here:
  1. Stage 1 burns (atmosphere + vacuum blend via weighted Isp)
  2. MECO  → stage separation → coast (3 s assumed)
  3. Stage 2 ignition → burns to orbit (vacuum Isp)
  4. Payload + fairing in orbit

Loss estimates (gravity + drag) are applied via a configurable
budget subtracted from ideal Δv to give "usable Δv".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

from rocket_core.vehicle.models import Vehicle
from rocket_core.propulsion.solver import G0, solve_propulsion

# ---------------------------------------------------------------------------
# Constants & defaults
# ---------------------------------------------------------------------------

COAST_DURATION_S: float = 5.0          # seconds between MECO and SES-1
FAIRING_SEP_AFTER_S: float = 50.0      # seconds after SES-1 to drop fairing

# Default gravity + drag losses (Falcon 9-like ascent to LEO)
DEFAULT_GRAVITY_LOSS_M_S: float = 1_200.0
DEFAULT_DRAG_LOSS_M_S:    float =   150.0
DEFAULT_STEERING_LOSS_M_S: float =   80.0


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StageResult:
    """Δv budget and mass state for one stage."""
    stage_id: str                   # "stage1" or "stage2"

    # Mass states
    m0_kg: float                    # initial total stack mass before burn
    mf_kg: float                    # final stack mass after burnout
    mass_ratio: float               # m0 / mf

    # Isp used for this stage
    isp_effective_s: float

    # Δv
    ideal_delta_v_m_s: float        # Tsiolkovsky (lossless)

    # Burn time
    burn_time_s: float

    # Propellant consumed
    prop_consumed_kg: float
    residual_propellant_kg: float   # unusable / reserve (estimated 0.5% of prop)


@dataclass
class StagingResult:
    """Full two-stage Δv budget and event log."""

    stage1: StageResult
    stage2: StageResult

    # Summed ideal Δv
    total_ideal_delta_v_m_s: float

    # Loss estimates
    gravity_loss_m_s:  float
    drag_loss_m_s:     float
    steering_loss_m_s: float
    total_losses_m_s:  float

    # Usable Δv after losses
    usable_delta_v_m_s: float

    # Mission delta-v requirement (from mission profile)
    required_delta_v_m_s: float

    # Margin
    delta_v_margin_m_s: float       # usable - required  (positive = margin)
    mission_feasible:   bool

    # Event log
    events: List[dict] = field(default_factory=list)
    # Each entry: {event, t_s, altitude_m (estimated), mass_kg, delta_v_so_far_m_s}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tsiolkovsky(m0: float, mf: float, isp: float) -> float:
    """Ideal Δv in m/s. Returns 0 if mass ratio ≤ 1."""
    if m0 <= 0 or mf <= 0 or m0 <= mf:
        return 0.0
    return isp * G0 * math.log(m0 / mf)


def _weighted_isp(isp_sl: float, isp_vac: float, weight_vac: float = 0.6) -> float:
    """
    Blend SL and vacuum Isp for a stage that burns through most of the atmosphere.
    Stage 1 spends roughly 40% of burn near sea level; weight accordingly.
    """
    return isp_sl * (1 - weight_vac) + isp_vac * weight_vac


def _required_delta_v(target_altitude_km: float) -> float:
    """
    Circular orbital velocity at target altitude [m/s].

    This is the NET velocity the vehicle must have at orbit insertion.
    Gravity, drag and steering losses are subtracted from the total ideal Δv
    *separately* in solve_staging (via usable_delta_v_m_s = total_ideal - losses).
    Do NOT add losses here; doing so would double-count them.

    Circular orbital velocity:  v = sqrt(GM / (R_e + h))
    GM  = 3.986e14 m³/s²
    R_e = 6.371e6 m
    """
    GM  = 3.986_004_418e14   # m³/s²
    R_e = 6_371_000.0        # m
    h   = target_altitude_km * 1_000.0
    return math.sqrt(GM / (R_e + h))


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def solve_staging(vehicle: Vehicle) -> StagingResult:
    """
    Compute stage-by-stage Δv budget for a two-stage vehicle.

    Parameters
    ----------
    vehicle : Vehicle

    Returns
    -------
    StagingResult
    """
    s1  = vehicle.stage1
    s2  = vehicle.stage2
    cfg = vehicle.sim_config
    mis = vehicle.mission

    # Residual propellant fraction (unavailable / reserve)
    RESIDUAL_FRAC = 0.005  # 0.5%

    # ------------------------------------------------------------------ #
    # Stage 1 Δv
    # ------------------------------------------------------------------ #
    # m0: full vehicle at liftoff
    m0_s1 = vehicle.liftoff_mass_kg

    # Stage 1 effective Isp (blended SL + vac since it burns through atmosphere)
    isp_s1 = _weighted_isp(s1.engine.isp_sl, s1.engine.isp_vac, weight_vac=0.60)

    # Propellant available (minus residuals)
    s1_residual = s1.prop_mass * RESIDUAL_FRAC
    s1_prop_used = s1.prop_mass - s1_residual

    # mf after Stage 1 burnout = m0 - prop used
    mf_s1 = m0_s1 - s1_prop_used

    # Burn time from propulsion solver
    prop_s1 = solve_propulsion(s1)

    s1_result = StageResult(
        stage_id               = "stage1",
        m0_kg                  = m0_s1,
        mf_kg                  = mf_s1,
        mass_ratio             = m0_s1 / mf_s1,
        isp_effective_s        = isp_s1,
        ideal_delta_v_m_s      = _tsiolkovsky(m0_s1, mf_s1, isp_s1),
        burn_time_s            = prop_s1.burn_time_s,
        prop_consumed_kg       = s1_prop_used,
        residual_propellant_kg = s1_residual,
    )

    # ------------------------------------------------------------------ #
    # Stage separation — drop Stage 1 body
    # ------------------------------------------------------------------ #
    # After MECO + separation: remaining stack = Stage2 + payload + fairing
    m0_s2 = s2.gross_mass_kg + vehicle.payload_mass + vehicle.fairing_mass

    # ------------------------------------------------------------------ #
    # Stage 2 Δv  (vacuum burn)
    # ------------------------------------------------------------------ #
    isp_s2 = s2.engine.isp_vac

    s2_residual  = s2.prop_mass * RESIDUAL_FRAC
    s2_prop_used = s2.prop_mass - s2_residual

    # Fairing is typically jettisoned ~50 s after SES-1 (upper atmosphere)
    # For simplicity, model fairing drop at mid-burn (conservative)
    fairing_drop_fraction = 0.3
    m0_s2_before_fairing = m0_s2
    m0_s2_after_fairing  = m0_s2 - vehicle.fairing_mass

    # Weighted average mass for Δv calc (fairing dropped partway through)
    m0_s2_eff = (
        m0_s2_before_fairing * fairing_drop_fraction
        + m0_s2_after_fairing * (1 - fairing_drop_fraction)
    )
    mf_s2 = s2.dry_mass + vehicle.payload_mass  # after burnout (fairing gone)

    prop_s2 = solve_propulsion(s2)

    s2_result = StageResult(
        stage_id               = "stage2",
        m0_kg                  = m0_s2,
        mf_kg                  = mf_s2,
        mass_ratio             = m0_s2_eff / mf_s2,
        isp_effective_s        = isp_s2,
        ideal_delta_v_m_s      = _tsiolkovsky(m0_s2_eff, mf_s2, isp_s2),
        burn_time_s            = prop_s2.burn_time_s,
        prop_consumed_kg       = s2_prop_used,
        residual_propellant_kg = s2_residual,
    )

    # ------------------------------------------------------------------ #
    # Δv budget and losses
    # ------------------------------------------------------------------ #
    total_ideal = s1_result.ideal_delta_v_m_s + s2_result.ideal_delta_v_m_s

    grav_loss    = cfg.gravity_loss_estimate_m_s
    drag_loss    = DEFAULT_DRAG_LOSS_M_S
    steer_loss   = DEFAULT_STEERING_LOSS_M_S
    total_losses = grav_loss + drag_loss + steer_loss
    usable_dv    = total_ideal - total_losses

    # Required Δv — use mission value if set, else compute from orbit
    if mis.required_delta_v_m_s is not None:
        req_dv = mis.required_delta_v_m_s
    else:
        req_dv = _required_delta_v(mis.target_altitude_km)

    margin = usable_dv - req_dv

    # ------------------------------------------------------------------ #
    # Event log (estimated times, not trajectory-integrated)
    # ------------------------------------------------------------------ #
    t_meco      = s1_result.burn_time_s
    t_sep       = t_meco + COAST_DURATION_S
    t_ses1      = t_sep  + COAST_DURATION_S
    t_fairing   = t_ses1 + FAIRING_SEP_AFTER_S
    t_seco      = t_ses1 + s2_result.burn_time_s

    events = [
        {"event": "Liftoff",       "t_s": 0.0,        "note": "Vehicle clears tower"},
        {"event": "Max-Q",         "t_s": 70.0,        "note": "Peak dynamic pressure (estimated)"},
        {"event": "Throttle-Down", "t_s": 60.0,        "note": "S1 throttle reduction before Max-Q"},
        {"event": "Throttle-Up",   "t_s": 80.0,        "note": "S1 throttle restored post Max-Q"},
        {"event": "MECO",          "t_s": round(t_meco,  1), "note": "Main Engine Cut-Off, Stage 1"},
        {"event": "Stage Sep",     "t_s": round(t_sep,   1), "note": "Stage 1 separation"},
        {"event": "SES-1",         "t_s": round(t_ses1,  1), "note": "Stage 2 engine start"},
        {"event": "Fairing Sep",   "t_s": round(t_fairing, 1), "note": "Payload fairing jettisoned"},
        {"event": "SECO",          "t_s": round(t_seco,  1), "note": "Stage 2 Engine Cut-Off / orbit insertion"},
    ]

    return StagingResult(
        stage1                    = s1_result,
        stage2                    = s2_result,
        total_ideal_delta_v_m_s   = total_ideal,
        gravity_loss_m_s          = grav_loss,
        drag_loss_m_s             = drag_loss,
        steering_loss_m_s         = steer_loss,
        total_losses_m_s          = total_losses,
        usable_delta_v_m_s        = usable_dv,
        required_delta_v_m_s      = req_dv,
        delta_v_margin_m_s        = margin,
        mission_feasible          = margin >= 0,
        events                    = events,
    )
