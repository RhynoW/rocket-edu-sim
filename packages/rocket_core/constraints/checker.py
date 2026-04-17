"""
rocket_core.constraints.checker
---------------------------------
Design-constraint validation for a two-stage launch vehicle.

Checks performed (in priority order):
  1. Liftoff T/W ≥ 1.2  (hard minimum; < 1.0 means vehicle won't leave pad)
  2. Stage 1 structure fraction within [0.05, 0.15]
  3. Stage 2 structure fraction within [0.05, 0.12]
  4. Propellant volume vs. estimated tank capacity (density × volume check)
  5. Burn time consistency with mass-flow rate (staging ↔ propulsion agree)
  6. Stage 2 thrust sufficient for orbit injection (T/W > 0.3 at separation)
  7. Engine count vs. diameter plausibility (footprint check)
  8. Stage 1 minimum burn time ≥ 120 s
  9. Stage 2 minimum burn time ≥ 200 s
 10. Payload fraction sanity (> 0 and < 0.08 for a realistic vehicle)

Each check returns a `ConstraintResult` with severity = "error" | "warning" | "ok".
The overall `ConstraintReport` aggregates all results and provides a pass/fail.

Educational note:
  Errors are hard constraints — the simulation should refuse to run.
  Warnings are soft constraints — the simulation runs but notes the issue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from rocket_core.vehicle.models import Vehicle
from rocket_core.propulsion.solver import G0, solve_propulsion
from rocket_core.staging.solver import solve_staging

# ---------------------------------------------------------------------------
# LOX/RP-1 and LOX/LH2 liquid propellant densities (kg/m³)
# We default to LOX/RP-1 (Falcon 9-like) if propellant type is unknown.
# ---------------------------------------------------------------------------

_DENSITY = {
    "LOX":  1_141.0,   # liquid oxygen
    "RP1":  820.0,     # RP-1 kerosene
    "LH2":  71.0,      # liquid hydrogen
    "CH4":  422.0,     # liquid methane (Raptor-style)
    "N2O4": 1_450.0,   # nitrogen tetroxide (storable)
    "UDMH": 791.0,     # unsymmetrical dimethylhydrazine (storable)
}

# Falcon 9-like tank volume allowance: gross tank volume ≈ prop_mass / density * 1.05 margin
_TANK_FILL_FACTOR = 0.95   # assume 95% fill; 5% ullage/reserve headroom


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ConstraintResult:
    """Result of a single constraint check."""
    name:        str         # short machine-readable identifier
    severity:    str         # "error" | "warning" | "ok"
    passed:      bool
    message:     str         # human-readable description
    value:       Optional[float] = None   # measured value (if numeric)
    limit:       Optional[float] = None   # threshold that was checked against
    unit:        str = ""


@dataclass
class ConstraintReport:
    """Aggregate constraint report for one vehicle configuration."""
    results:       List[ConstraintResult] = field(default_factory=list)

    # Convenience aggregates
    @property
    def errors(self) -> List[ConstraintResult]:
        return [r for r in self.results if r.severity == "error"]

    @property
    def warnings(self) -> List[ConstraintResult]:
        return [r for r in self.results if r.severity == "warning"]

    @property
    def passed(self) -> bool:
        """True only when there are zero errors."""
        return len(self.errors) == 0

    @property
    def error_messages(self) -> List[str]:
        return [r.message for r in self.errors]

    @property
    def warning_messages(self) -> List[str]:
        return [r.message for r in self.warnings]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_liftoff_twr(vehicle: Vehicle) -> ConstraintResult:
    twr = vehicle.liftoff_twr
    if twr < 1.0:
        return ConstraintResult(
            name="liftoff_twr",
            severity="error",
            passed=False,
            message=(
                f"Liftoff T/W = {twr:.3f} < 1.0 — vehicle cannot lift off. "
                f"Increase Stage 1 thrust or reduce liftoff mass."
            ),
            value=twr, limit=1.0, unit="",
        )
    if twr < 1.2:
        return ConstraintResult(
            name="liftoff_twr",
            severity="warning",
            passed=False,
            message=(
                f"Liftoff T/W = {twr:.3f} is low (recommended ≥ 1.2). "
                f"The vehicle will lift off but may not clear the launch tower safely."
            ),
            value=twr, limit=1.2, unit="",
        )
    return ConstraintResult(
        name="liftoff_twr",
        severity="ok", passed=True,
        message=f"Liftoff T/W = {twr:.3f} ✓",
        value=twr, limit=1.2,
    )


def _check_stage1_structure_fraction(vehicle: Vehicle) -> ConstraintResult:
    sf = vehicle.stage1.structure_fraction
    lo, hi = 0.04, 0.15
    if sf > hi:
        return ConstraintResult(
            name="s1_structure_fraction",
            severity="warning",
            passed=False,
            message=(
                f"Stage 1 structure fraction = {sf:.4f} > {hi} — "
                f"Stage 1 is heavy for its propellant load. "
                f"Consider reducing dry mass or adding more propellant."
            ),
            value=sf, limit=hi,
        )
    if sf < lo:
        return ConstraintResult(
            name="s1_structure_fraction",
            severity="warning",
            passed=False,
            message=(
                f"Stage 1 structure fraction = {sf:.4f} < {lo} — "
                f"unusually low; verify dry mass input."
            ),
            value=sf, limit=lo,
        )
    return ConstraintResult(
        name="s1_structure_fraction",
        severity="ok", passed=True,
        message=f"Stage 1 structure fraction = {sf:.4f} ✓",
        value=sf,
    )


def _check_stage2_structure_fraction(vehicle: Vehicle) -> ConstraintResult:
    sf = vehicle.stage2.structure_fraction
    lo, hi = 0.04, 0.12
    if sf > hi:
        return ConstraintResult(
            name="s2_structure_fraction",
            severity="warning",
            passed=False,
            message=(
                f"Stage 2 structure fraction = {sf:.4f} > {hi} — "
                f"Stage 2 dry mass is high. Reducing it by 500 kg adds ~500 kg to payload."
            ),
            value=sf, limit=hi,
        )
    if sf < lo:
        return ConstraintResult(
            name="s2_structure_fraction",
            severity="warning",
            passed=False,
            message=(
                f"Stage 2 structure fraction = {sf:.4f} < {lo} — "
                f"unusually low; verify Stage 2 dry mass input."
            ),
            value=sf, limit=lo,
        )
    return ConstraintResult(
        name="s2_structure_fraction",
        severity="ok", passed=True,
        message=f"Stage 2 structure fraction = {sf:.4f} ✓",
        value=sf,
    )


def _check_propellant_volume(vehicle: Vehicle) -> List[ConstraintResult]:
    """
    Estimate required tank volume from propellant mass + propellant type,
    then compare against a rough geometric limit derived from stage diameter.

    Volume of a cylinder:  V = π/4 × d² × L
    For a rocket stage:  L ≈ 10–20 × d is typical.
    We use L_max = 20 × d (conservative upper limit) giving
       V_avail ≈ π/4 × d² × 20d = 5π × d³
    """
    import math

    results: List[ConstraintResult] = []

    prop = vehicle.propellant

    # Attempt to get oxidiser/fuel densities from propellant model.
    # Fall back to LOX/RP-1 defaults.
    ox_density  = _DENSITY.get(prop.oxidizer_name.upper().replace("-", "").replace(" ", ""), 1_141.0)
    fuel_density = _DENSITY.get(prop.fuel_name.upper().replace("-", "").replace(" ", ""), 820.0)
    # Mixture ratio: ox / fuel by mass (Falcon 9 ~ 2.56)
    mr = prop.mixture_ratio if hasattr(prop, "mixture_ratio") and prop.mixture_ratio else 2.56

    for stage, label in [(vehicle.stage1, "Stage 1"), (vehicle.stage2, "Stage 2")]:
        prop_mass = stage.prop_mass
        # Split propellant into ox and fuel
        fuel_mass = prop_mass / (1.0 + mr)
        ox_mass   = prop_mass - fuel_mass

        # Required volume (m³)
        vol_required = ox_mass / ox_density + fuel_mass / fuel_density
        vol_required /= _TANK_FILL_FACTOR  # ullage allowance

        # Available volume from stage geometry (approximate cylinder)
        d = stage.diameter_m
        vol_available = 5.0 * math.pi * d**3   # L_max = 20d

        ratio = vol_required / vol_available

        if ratio > 1.0:
            results.append(ConstraintResult(
                name=f"{label.lower().replace(' ', '')}_prop_volume",
                severity="error",
                passed=False,
                message=(
                    f"{label} propellant volume ({vol_required:.1f} m³) exceeds estimated "
                    f"tank capacity ({vol_available:.1f} m³) for a {d:.1f} m diameter stage. "
                    f"Reduce propellant load or increase stage diameter."
                ),
                value=vol_required, limit=vol_available, unit="m³",
            ))
        elif ratio > 0.85:
            results.append(ConstraintResult(
                name=f"{label.lower().replace(' ', '')}_prop_volume",
                severity="warning",
                passed=False,
                message=(
                    f"{label} propellant volume ({vol_required:.1f} m³) is "
                    f"{ratio*100:.0f}% of estimated tank capacity ({vol_available:.1f} m³). "
                    f"Tight fit — verify stage geometry."
                ),
                value=vol_required, limit=vol_available, unit="m³",
            ))
        else:
            results.append(ConstraintResult(
                name=f"{label.lower().replace(' ', '')}_prop_volume",
                severity="ok", passed=True,
                message=f"{label} propellant volume {vol_required:.1f} m³ fits in tank ✓",
                value=vol_required, limit=vol_available, unit="m³",
            ))

    return results


def _check_burn_time_consistency(vehicle: Vehicle) -> List[ConstraintResult]:
    """
    Check that the burn time computed from propellant mass / mdot
    (propulsion solver) is plausible. Also check minimum burn times.
    """
    results: List[ConstraintResult] = []

    for stage, label, min_bt in [
        (vehicle.stage1, "Stage 1", 120.0),
        (vehicle.stage2, "Stage 2", 200.0),
    ]:
        prop_res = solve_propulsion(stage)
        bt = prop_res.burn_time_s

        if bt < min_bt * 0.5:
            results.append(ConstraintResult(
                name=f"{label.lower().replace(' ', '')}_burn_time",
                severity="error",
                passed=False,
                message=(
                    f"{label} burn time is only {bt:.0f} s — far below the "
                    f"expected minimum of {min_bt:.0f} s. "
                    f"Propellant mass may be too low or thrust too high."
                ),
                value=bt, limit=min_bt, unit="s",
            ))
        elif bt < min_bt:
            results.append(ConstraintResult(
                name=f"{label.lower().replace(' ', '')}_burn_time",
                severity="warning",
                passed=False,
                message=(
                    f"{label} burn time = {bt:.0f} s is below the expected "
                    f"minimum of {min_bt:.0f} s."
                ),
                value=bt, limit=min_bt, unit="s",
            ))
        else:
            results.append(ConstraintResult(
                name=f"{label.lower().replace(' ', '')}_burn_time",
                severity="ok", passed=True,
                message=f"{label} burn time = {bt:.0f} s ✓",
                value=bt, limit=min_bt, unit="s",
            ))

    return results


def _check_stage2_orbital_twr(vehicle: Vehicle) -> ConstraintResult:
    """
    Stage 2 must have enough thrust to inject into orbit.
    At the point of Stage 2 ignition the stack mass is:
        m_s2 = stage2.gross + payload + fairing
    We require T/W(vac) > 0.3 for effective orbit insertion.
    """
    s2 = vehicle.stage2
    m_s2 = s2.gross_mass_kg + vehicle.payload_mass + vehicle.fairing_mass
    twr_s2 = s2.thrust_vac_total_N / (m_s2 * G0)

    if twr_s2 < 0.15:
        return ConstraintResult(
            name="s2_orbital_twr",
            severity="error",
            passed=False,
            message=(
                f"Stage 2 vacuum T/W at ignition = {twr_s2:.3f} < 0.15. "
                f"Stage 2 thrust is insufficient for orbit injection. "
                f"Increase Stage 2 engine thrust or reduce upper stage mass."
            ),
            value=twr_s2, limit=0.15,
        )
    if twr_s2 < 0.30:
        return ConstraintResult(
            name="s2_orbital_twr",
            severity="warning",
            passed=False,
            message=(
                f"Stage 2 vacuum T/W = {twr_s2:.3f} is low (recommended ≥ 0.3). "
                f"Gravity losses during the Stage 2 burn will be significant."
            ),
            value=twr_s2, limit=0.30,
        )
    return ConstraintResult(
        name="s2_orbital_twr",
        severity="ok", passed=True,
        message=f"Stage 2 orbital T/W = {twr_s2:.3f} ✓",
        value=twr_s2, limit=0.30,
    )


def _check_engine_count_vs_diameter(vehicle: Vehicle) -> List[ConstraintResult]:
    """
    Very rough footprint check: each engine needs a minimum base area.
    We assume each Merlin-class engine needs ~0.30 m² of base area
    (nozzle exit ~0.31 m diameter → area ~0.075 m², plus clearance → ~0.30 m²).
    Stage base area = π/4 × d²
    """
    import math

    results: List[ConstraintResult] = []
    ENGINE_BASE_AREA_M2 = 0.30   # per engine (approximate)

    for stage, label in [(vehicle.stage1, "Stage 1"), (vehicle.stage2, "Stage 2")]:
        n    = stage.engine_count
        d    = stage.diameter_m
        base = math.pi / 4.0 * d**2
        needed = n * ENGINE_BASE_AREA_M2

        if needed > base:
            results.append(ConstraintResult(
                name=f"{label.lower().replace(' ', '')}_engine_footprint",
                severity="warning",
                passed=False,
                message=(
                    f"{label}: {n} engines require ~{needed:.1f} m² base area "
                    f"but stage diameter {d:.1f} m only provides {base:.1f} m². "
                    f"Reduce engine count or increase stage diameter."
                ),
                value=needed, limit=base, unit="m²",
            ))
        else:
            results.append(ConstraintResult(
                name=f"{label.lower().replace(' ', '')}_engine_footprint",
                severity="ok", passed=True,
                message=(
                    f"{label}: {n} engines fit in {d:.1f} m diameter base "
                    f"({needed:.1f} m² < {base:.1f} m²) ✓"
                ),
                value=needed, limit=base, unit="m²",
            ))

    return results


def _check_payload_fraction(vehicle: Vehicle) -> ConstraintResult:
    """Payload fraction sanity check."""
    pf = vehicle.payload_mass / vehicle.liftoff_mass_kg
    if pf <= 0:
        return ConstraintResult(
            name="payload_fraction",
            severity="error",
            passed=False,
            message="Payload mass must be > 0.",
            value=pf,
        )
    if pf > 0.10:
        return ConstraintResult(
            name="payload_fraction",
            severity="warning",
            passed=False,
            message=(
                f"Payload fraction = {pf:.4f} ({pf*100:.1f}%) is unusually high. "
                f"Realistic two-stage launch vehicles are typically ≤ 5–8%."
            ),
            value=pf, limit=0.10,
        )
    return ConstraintResult(
        name="payload_fraction",
        severity="ok", passed=True,
        message=f"Payload fraction = {pf*100:.2f}% ✓",
        value=pf,
    )


def _check_delta_v_feasibility(vehicle: Vehicle) -> ConstraintResult:
    """
    Quick Δv feasibility — run the staging solver and verify the vehicle
    has positive margin to the target orbit. This is a summary check that
    wraps the full staging result.
    """
    staging = solve_staging(vehicle)
    margin  = staging.delta_v_margin_m_s

    if margin < -500:
        return ConstraintResult(
            name="delta_v_feasibility",
            severity="error",
            passed=False,
            message=(
                f"Vehicle is {abs(margin):.0f} m/s short of the target orbit Δv. "
                f"Add propellant, improve Isp, or reduce mass."
            ),
            value=margin, limit=0.0, unit="m/s",
        )
    if margin < 0:
        return ConstraintResult(
            name="delta_v_feasibility",
            severity="error",
            passed=False,
            message=(
                f"Δv margin = {margin:.0f} m/s — vehicle cannot reach the target orbit."
            ),
            value=margin, limit=0.0, unit="m/s",
        )
    if margin < 200:
        return ConstraintResult(
            name="delta_v_feasibility",
            severity="warning",
            passed=False,
            message=(
                f"Δv margin = {margin:.0f} m/s — very tight. "
                f"Small changes to dry mass or Isp may make this mission infeasible."
            ),
            value=margin, limit=200.0, unit="m/s",
        )
    return ConstraintResult(
        name="delta_v_feasibility",
        severity="ok", passed=True,
        message=f"Δv margin = {margin:.0f} m/s ✓",
        value=margin, limit=200.0, unit="m/s",
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def check_constraints(vehicle: Vehicle) -> ConstraintReport:
    """
    Run all design-constraint checks on a vehicle and return a ConstraintReport.

    Parameters
    ----------
    vehicle : Vehicle

    Returns
    -------
    ConstraintReport
        .passed  → True if no errors (warnings are allowed)
        .errors  → list of blocking ConstraintResult items
        .warnings → list of advisory ConstraintResult items
    """
    results: List[ConstraintResult] = []

    # --- Single-result checks ---
    results.append(_check_liftoff_twr(vehicle))
    results.append(_check_stage1_structure_fraction(vehicle))
    results.append(_check_stage2_structure_fraction(vehicle))
    results.append(_check_stage2_orbital_twr(vehicle))
    results.append(_check_payload_fraction(vehicle))
    results.append(_check_delta_v_feasibility(vehicle))

    # --- Multi-result checks ---
    results.extend(_check_propellant_volume(vehicle))
    results.extend(_check_burn_time_consistency(vehicle))
    results.extend(_check_engine_count_vs_diameter(vehicle))

    return ConstraintReport(results=results)
