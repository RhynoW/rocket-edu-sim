"""
rocket_core.mass_budget.solver
-------------------------------
Breaks the total vehicle mass into components and computes key
mass-efficiency metrics used in the educational UI.

Outputs
-------
- Stage-by-stage breakdown (dry, propellant, gross)
- Dead-weight sub-items (structural shell, tanks, engines, avionics, …)
- Structure fraction  sf = dry / (dry + prop)   — lower is better
- Propellant mass fraction  pmf = total_prop / liftoff_mass
- Payload fraction  pf = payload / liftoff_mass
- Fairing + reserve penalties

Educational note:
  Dead-weight minimisation is the primary lever students have on payload.
  Every kilogram saved from Stage 2 dry mass adds ~1 kg of payload.
  Stage 1 dry mass has a smaller but still significant effect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from rocket_core.vehicle.models import Stage, Vehicle


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StageMassBudget:
    """Mass budget for one stage."""

    stage_id: str               # "stage1" or "stage2"
    dry_mass_kg:   float
    prop_mass_kg:  float
    gross_mass_kg: float        # dry + prop

    # Engine hardware
    engine_mass_total_kg: float
    engine_count: int

    # Efficiency metrics
    structure_fraction: float   # dry / (dry + prop)
    propellant_fraction: float  # prop / gross

    # Optional itemised dead-weight
    dead_weight: Dict[str, Optional[float]] = field(default_factory=dict)


@dataclass
class MassBudgetResult:
    """Full vehicle mass budget."""

    # Component masses
    stage1: StageMassBudget
    stage2: StageMassBudget
    payload_mass_kg:  float
    fairing_mass_kg:  float
    liftoff_mass_kg:  float

    # Totals
    total_dry_mass_kg:  float
    total_prop_mass_kg: float

    # Vehicle-level efficiency metrics
    payload_fraction:    float   # payload / liftoff_mass
    propellant_fraction: float   # total_prop / liftoff_mass
    structure_fraction:  float   # total_dry / (total_dry + total_prop)

    # Liftoff T/W
    liftoff_twr: float

    # Penalty breakdown
    fairing_penalty_kg:   float
    recovery_penalty_kg:  float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _structure_fraction(dry: float, prop: float) -> float:
    total = dry + prop
    if total <= 0:
        return 0.0
    return dry / total


def _build_dead_weight(stage: Stage) -> Dict[str, Optional[float]]:
    """Extract dead-weight breakdown from stage model (if provided)."""
    dw = stage.dead_weight
    if dw is None:
        # Estimate proportional breakdown from dry mass
        dm = stage.dry_mass
        engine_mass = stage.engine.mass * stage.engine_count
        remainder   = dm - engine_mass
        return {
            "structural_shell_kg":  round(remainder * 0.40, 1),
            "propellant_tanks_kg":  round(remainder * 0.30, 1),
            "engines_kg":           round(engine_mass, 1),
            "avionics_kg":          round(remainder * 0.05, 1),
            "interstage_kg":        round(remainder * 0.10, 1),
            "recovery_hardware_kg": round(remainder * 0.10, 1),
            "reserve_propellant_kg": round(remainder * 0.05, 1),
        }
    return {
        "structural_shell_kg":   dw.structural_shell_kg,
        "propellant_tanks_kg":   dw.propellant_tanks_kg,
        "engines_kg":            dw.engines_kg,
        "avionics_kg":           dw.avionics_kg,
        "interstage_kg":         dw.interstage_kg,
        "fairing_kg":            dw.fairing_kg,
        "recovery_hardware_kg":  dw.recovery_hardware_kg,
        "reserve_propellant_kg": dw.reserve_propellant_kg,
    }


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def solve_mass_budget(vehicle: Vehicle) -> MassBudgetResult:
    """
    Compute complete mass budget for a two-stage vehicle.

    Parameters
    ----------
    vehicle : Vehicle
        Fully populated vehicle model.

    Returns
    -------
    MassBudgetResult
    """
    s1 = vehicle.stage1
    s2 = vehicle.stage2

    # --- Stage 1 ---
    s1_engine_mass = s1.engine.mass * s1.engine_count
    s1_budget = StageMassBudget(
        stage_id             = "stage1",
        dry_mass_kg          = s1.dry_mass,
        prop_mass_kg         = s1.prop_mass,
        gross_mass_kg        = s1.gross_mass_kg,
        engine_mass_total_kg = s1_engine_mass,
        engine_count         = s1.engine_count,
        structure_fraction   = _structure_fraction(s1.dry_mass, s1.prop_mass),
        propellant_fraction  = s1.prop_mass / s1.gross_mass_kg,
        dead_weight          = _build_dead_weight(s1),
    )

    # --- Stage 2 ---
    s2_engine_mass = s2.engine.mass * s2.engine_count
    s2_budget = StageMassBudget(
        stage_id             = "stage2",
        dry_mass_kg          = s2.dry_mass,
        prop_mass_kg         = s2.prop_mass,
        gross_mass_kg        = s2.gross_mass_kg,
        engine_mass_total_kg = s2_engine_mass,
        engine_count         = s2.engine_count,
        structure_fraction   = _structure_fraction(s2.dry_mass, s2.prop_mass),
        propellant_fraction  = s2.prop_mass / s2.gross_mass_kg,
        dead_weight          = _build_dead_weight(s2),
    )

    # --- Vehicle totals ---
    liftoff_mass = vehicle.liftoff_mass_kg
    total_dry    = s1.dry_mass + s2.dry_mass
    total_prop   = s1.prop_mass + s2.prop_mass

    # Recovery penalty from mission flags
    recovery_penalty = vehicle.mission.reusable_penalty_kg

    result = MassBudgetResult(
        stage1               = s1_budget,
        stage2               = s2_budget,
        payload_mass_kg      = vehicle.payload_mass,
        fairing_mass_kg      = vehicle.fairing_mass,
        liftoff_mass_kg      = liftoff_mass,
        total_dry_mass_kg    = total_dry,
        total_prop_mass_kg   = total_prop,
        payload_fraction     = vehicle.payload_mass / liftoff_mass,
        propellant_fraction  = total_prop / liftoff_mass,
        structure_fraction   = _structure_fraction(total_dry, total_prop),
        liftoff_twr          = vehicle.liftoff_twr,
        fairing_penalty_kg   = vehicle.fairing_mass,
        recovery_penalty_kg  = recovery_penalty,
    )
    return result
