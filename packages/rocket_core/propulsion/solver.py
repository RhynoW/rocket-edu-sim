"""
rocket_core.propulsion.solver
------------------------------
Computes propulsion parameters for a single stage:
  - Total sea-level and vacuum thrust
  - Mass flow rate (mdot)
  - Effective Isp at a given altitude
  - Estimated burn time from propellant mass
  - Engine thrust-to-weight ratio
  - Interpolated thrust at arbitrary altitude/throttle

Physics:
  F   = Isp * g0 * mdot          (thrust from Isp definition)
  mdot = F / (Isp * g0)          (mass flow rate)
  Isp_eff(h) = Isp_sl + (Isp_vac - Isp_sl) * (1 - p(h)/p0)
               (linear interpolation; p(h) from US Std Atm approx)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

from rocket_core.vehicle.models import Stage

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

G0: float = 9.80665   # standard gravity [m/s²]
P0: float = 101_325.0 # sea-level pressure [Pa]
H_SCALE: float = 8_500.0  # atmospheric scale height [m] (simple exponential model)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PropulsionResult:
    """Output of the propulsion solver for one stage."""

    # --- sea-level values ---
    thrust_sl_N: float          # Total SL thrust [N]
    mdot_sl_kg_s: float         # Mass flow rate at SL [kg/s]
    isp_sl_s: float             # Effective SL Isp [s]

    # --- vacuum values ---
    thrust_vac_N: float         # Total vacuum thrust [N]
    mdot_vac_kg_s: float        # Mass flow rate in vacuum [kg/s]
    isp_vac_s: float            # Effective vacuum Isp [s]

    # --- derived ---
    burn_time_s: float          # Estimated burn time from propellant mass [s]
    engine_twr: float           # Engine TWR (thrust / engine_mass / g0)
    avg_mdot_kg_s: float        # Average mdot used for burn-time calc

    # --- throttle profile snapshot ---
    thrust_timeline: List[dict] = field(default_factory=list)
    # Each entry: {t_s, throttle_frac, thrust_N, mdot_kg_s, altitude_m, isp_s}


# ---------------------------------------------------------------------------
# Atmospheric helpers
# ---------------------------------------------------------------------------

def atmospheric_pressure_Pa(altitude_m: float) -> float:
    """
    Simple exponential atmosphere.
    Accurate enough for educational use up to ~80 km.
    """
    if altitude_m < 0:
        altitude_m = 0.0
    return P0 * math.exp(-altitude_m / H_SCALE)


def isp_at_altitude(isp_sl: float, isp_vac: float, altitude_m: float) -> float:
    """
    Linearly interpolate Isp between sea-level and vacuum
    based on ambient pressure ratio.
    """
    p_ratio = atmospheric_pressure_Pa(altitude_m) / P0   # 1.0 at sea level, → 0 in vacuum
    return isp_sl + (isp_vac - isp_sl) * (1.0 - p_ratio)


def thrust_at_altitude(
    thrust_sl: float,
    thrust_vac: float,
    isp_sl: float,
    isp_vac: float,
    altitude_m: float,
    throttle: float = 1.0,
) -> tuple[float, float]:
    """
    Return (thrust_N, mdot_kg_s) at a given altitude and throttle fraction.

    Throat area is fixed; nozzle exit pressure changes with ambient pressure.
    Approximation: linear interpolation between SL and vacuum performance.
    """
    throttle = max(0.0, min(1.0, throttle))
    isp_eff  = isp_at_altitude(isp_sl, isp_vac, altitude_m)
    # Full-throttle vacuum mdot is fixed by nozzle geometry
    mdot_full = thrust_vac / (isp_vac * G0)
    mdot      = mdot_full * throttle
    thrust    = mdot * isp_eff * G0
    return thrust, mdot


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def solve_propulsion(stage: Stage) -> PropulsionResult:
    """
    Compute propulsion parameters for a single stage at sea level (full throttle)
    and in vacuum (full throttle), plus burn-time estimate.

    Parameters
    ----------
    stage : Stage
        Stage model containing engine and propellant mass.

    Returns
    -------
    PropulsionResult
    """
    eng = stage.engine
    n   = stage.engine_count

    # --- Sea-level totals ---
    thrust_sl_N   = eng.thrust_sl * n
    mdot_sl_kg_s  = thrust_sl_N / (eng.isp_sl * G0)

    # --- Vacuum totals ---
    thrust_vac_N  = eng.thrust_vac * n
    mdot_vac_kg_s = thrust_vac_N / (eng.isp_vac * G0)

    # --- Burn-time estimate ---
    # For upper stages that operate almost entirely in vacuum (thrust_sl ≈ 0),
    # the SL mass-flow-rate is negligible.  Averaging it with the vacuum rate
    # would halve the apparent mdot and double the burn time — a serious error.
    # Use vacuum mdot if SL thrust is < 1 % of vacuum thrust; average otherwise.
    if eng.thrust_sl < 0.01 * eng.thrust_vac:
        avg_mdot = mdot_vac_kg_s        # upper stage: burns entirely in vacuum
    else:
        avg_mdot = (mdot_sl_kg_s + mdot_vac_kg_s) / 2.0   # main stage: atmosphere → vacuum
    burn_time_s = stage.prop_mass / avg_mdot

    # --- Engine TWR (engine hardware only, not full stage) ---
    engine_mass_total = eng.mass * n
    engine_twr = thrust_sl_N / (engine_mass_total * G0)

    # --- Representative thrust timeline (3 snap-shots) ---
    timeline: List[dict] = []
    for frac, alt in [(0.0, 0.0), (0.5, 40_000.0), (1.0, 80_000.0)]:
        t_sec = frac * burn_time_s
        thr, mdt = thrust_at_altitude(
            eng.thrust_sl, eng.thrust_vac,
            eng.isp_sl,    eng.isp_vac,
            alt, throttle=1.0,
        )
        isp_eff = isp_at_altitude(eng.isp_sl, eng.isp_vac, alt)
        timeline.append({
            "t_s":         round(t_sec, 1),
            "altitude_m":  alt,
            "throttle":    1.0,
            "thrust_N":    round(thr * n, 1),
            "mdot_kg_s":   round(mdt * n, 3),
            "isp_s":       round(isp_eff, 2),
        })

    return PropulsionResult(
        thrust_sl_N   = thrust_sl_N,
        mdot_sl_kg_s  = mdot_sl_kg_s,
        isp_sl_s      = eng.isp_sl,
        thrust_vac_N  = thrust_vac_N,
        mdot_vac_kg_s = mdot_vac_kg_s,
        isp_vac_s     = eng.isp_vac,
        burn_time_s   = burn_time_s,
        engine_twr    = engine_twr,
        avg_mdot_kg_s = avg_mdot,
        thrust_timeline = timeline,
    )
