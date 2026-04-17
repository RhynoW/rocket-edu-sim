"""
apps.api.app.services.simulation
----------------------------------
Business logic layer: translates API request schemas → domain models,
runs the solver pipeline, and translates results → response schemas.

Solver pipeline (in order):
  1. propulsion  (per stage — embedded in staging solver)
  2. mass_budget
  3. staging
  4. trajectory  (optional, controlled by sim_config.run_trajectory)
  5. payload
  6. constraints

All solver calls are pure functions; no I/O side effects here.
"""

from __future__ import annotations

from typing import Optional

from rocket_core.vehicle.models import (
    Engine, Stage, Mission, Propellant, SimulationConfig, Vehicle,
)
from rocket_core.mass_budget.solver   import solve_mass_budget
from rocket_core.staging.solver       import solve_staging
from rocket_core.payload.solver       import estimate_payload
from rocket_core.constraints.checker  import check_constraints, ConstraintReport

from apps.api.app.schemas.simulation import (
    SimulationRequest, SimulationResponse,
    SensitivityRequest, SensitivityResponse, SensitivityPoint,
    BatchRequest, BatchResponse,
    MassBudgetOut, StagingResultOut, StageResultOut, PayloadResultOut,
    ConstraintResultOut, TrajectoryResultOut, TrajectoryPointOut,
)


# ---------------------------------------------------------------------------
# Schema → domain model
# ---------------------------------------------------------------------------

def _build_vehicle(req: SimulationRequest) -> Vehicle:
    def _engine(e) -> Engine:
        return Engine(
            name=e.name,
            thrust_sl=e.thrust_sl,
            thrust_vac=e.thrust_vac,
            isp_sl=e.isp_sl,
            isp_vac=e.isp_vac,
            mass=e.mass,
        )

    def _stage(s) -> Stage:
        return Stage(
            dry_mass=s.dry_mass,
            prop_mass=s.prop_mass,
            engine=_engine(s.engine),
            engine_count=s.engine_count,
            diameter_m=s.diameter_m,
        )

    return Vehicle(
        stage1=_stage(req.stage1),
        stage2=_stage(req.stage2),
        payload_mass=req.payload_mass,
        fairing_mass=req.fairing_mass,
        propellant=Propellant(
            oxidiser=req.propellant.oxidiser,
            fuel=req.propellant.fuel,
            mixture_ratio=req.propellant.mixture_ratio,
        ),
        mission=Mission(
            target_altitude_km=req.mission.target_altitude_km,
            reusable_booster=req.mission.reusable_booster,
            reusable_penalty_kg=req.mission.reusable_penalty_kg,
            required_delta_v_m_s=req.mission.required_delta_v_m_s,
        ),
        sim_config=SimulationConfig(
            gravity_loss_estimate_m_s=req.sim_config.gravity_loss_estimate_m_s,
            max_q_throttle_fraction=req.sim_config.max_q_throttle_fraction,
        ),
    )


# ---------------------------------------------------------------------------
# Result → response schema
# ---------------------------------------------------------------------------

def _mass_budget_out(mb) -> MassBudgetOut:
    return MassBudgetOut(
        liftoff_mass_kg    = mb.liftoff_mass_kg,
        total_dry_mass_kg  = mb.total_dry_mass_kg,
        total_prop_mass_kg = mb.total_prop_mass_kg,
        payload_mass_kg    = mb.payload_mass_kg,
        fairing_mass_kg    = mb.fairing_mass_kg,
        payload_fraction   = mb.payload_fraction,
        propellant_fraction = mb.propellant_fraction,
        structure_fraction = mb.structure_fraction,
        liftoff_twr        = mb.liftoff_twr,
        fairing_penalty_kg = mb.fairing_penalty_kg,
        recovery_penalty_kg = mb.recovery_penalty_kg,
    )


def _staging_out(sr) -> StagingResultOut:
    def _stage(s) -> StageResultOut:
        return StageResultOut(
            stage_id=s.stage_id,
            m0_kg=s.m0_kg,
            mf_kg=s.mf_kg,
            mass_ratio=s.mass_ratio,
            isp_effective_s=s.isp_effective_s,
            ideal_delta_v_m_s=s.ideal_delta_v_m_s,
            burn_time_s=s.burn_time_s,
            prop_consumed_kg=s.prop_consumed_kg,
            residual_propellant_kg=s.residual_propellant_kg,
        )
    return StagingResultOut(
        stage1=_stage(sr.stage1),
        stage2=_stage(sr.stage2),
        total_ideal_delta_v_m_s = sr.total_ideal_delta_v_m_s,
        gravity_loss_m_s        = sr.gravity_loss_m_s,
        drag_loss_m_s           = sr.drag_loss_m_s,
        steering_loss_m_s       = sr.steering_loss_m_s,
        total_losses_m_s        = sr.total_losses_m_s,
        usable_delta_v_m_s      = sr.usable_delta_v_m_s,
        required_delta_v_m_s    = sr.required_delta_v_m_s,
        delta_v_margin_m_s      = sr.delta_v_margin_m_s,
        mission_feasible        = sr.mission_feasible,
        events                  = sr.events,
    )


def _payload_out(pr) -> PayloadResultOut:
    return PayloadResultOut(
        mission_feasible     = pr.mission_feasible,
        orbit_achieved       = pr.orbit_achieved,
        payload_mass_kg      = pr.payload_mass_kg,
        payload_fraction     = pr.payload_fraction,
        usable_delta_v_m_s   = pr.usable_delta_v_m_s,
        required_delta_v_m_s = pr.required_delta_v_m_s,
        margin_to_orbit_m_s  = pr.margin_to_orbit_m_s,
        achievable_orbit_km  = pr.achievable_orbit_km,
        max_payload_kg       = pr.max_payload_kg,
        limiting_factor      = pr.limiting_factor,
        sensitivity_hints    = pr.sensitivity_hints,
    )


def _constraints_out(report: ConstraintReport) -> list[ConstraintResultOut]:
    return [
        ConstraintResultOut(
            name=r.name,
            severity=r.severity,
            passed=r.passed,
            message=r.message,
            value=r.value,
            limit=r.limit,
            unit=r.unit,
        )
        for r in report.results
    ]


def _trajectory_out(tr) -> Optional[TrajectoryResultOut]:
    if tr is None:
        return None

    points = [
        TrajectoryPointOut(
            t_s          = p.t_s,
            altitude_km  = p.altitude_m / 1_000.0,
            downrange_km = p.downrange_m / 1_000.0,
            velocity_m_s = p.velocity_m_s,
            mass_kg      = p.mass_kg,
            phase        = p.phase,
        )
        for p in tr.timeline
    ]
    return TrajectoryResultOut(
        apogee_km          = tr.burnout_altitude_m / 1_000.0,
        max_velocity_m_s   = tr.burnout_velocity_m_s,
        max_q_Pa           = tr.max_q_Pa,
        orbit_achieved     = tr.orbit_achieved,
        final_altitude_km  = tr.burnout_altitude_m / 1_000.0,
        final_velocity_m_s = tr.burnout_velocity_m_s,
        trajectory         = points,
    )


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------

def run_simulation(req: SimulationRequest) -> SimulationResponse:
    """
    Execute the full solver pipeline for one simulation request.
    Returns a SimulationResponse (errors list populated on failure).
    """
    # --- Build domain model ---
    try:
        vehicle = _build_vehicle(req)
    except Exception as exc:
        return SimulationResponse(ok=False, errors=[f"Vehicle model error: {exc}"])

    # --- Constraint pre-check ---
    try:
        report = check_constraints(vehicle)
    except Exception as exc:
        return SimulationResponse(ok=False, errors=[f"Constraint check error: {exc}"])
    hard_errors = report.error_messages
    if hard_errors:
        return SimulationResponse(
            ok=False,
            errors=hard_errors,
            warnings=report.warning_messages,
            constraints=_constraints_out(report),
        )

    # --- Solver pipeline ---
    try:
        mass_budget = solve_mass_budget(vehicle)
        staging     = solve_staging(vehicle)
        payload     = estimate_payload(vehicle, staging)
    except Exception as exc:
        return SimulationResponse(ok=False, errors=[f"Solver error: {exc}"])

    # --- Optional trajectory ---
    traj_out = None
    if req.sim_config.run_trajectory:
        try:
            from rocket_core.trajectory.solver import simulate_trajectory
            traj = simulate_trajectory(vehicle)
            traj_out = _trajectory_out(traj)
        except Exception as exc:
            # Trajectory failure is non-fatal; degrade gracefully
            report.results.append(
                __import__("rocket_core.constraints.checker", fromlist=["ConstraintResult"])
                .ConstraintResult(
                    name="trajectory",
                    severity="warning",
                    passed=False,
                    message=f"Trajectory solver failed: {exc}",
                )
            )

    return SimulationResponse(
        ok=True,
        warnings=report.warning_messages,
        mass_budget  = _mass_budget_out(mass_budget),
        staging      = _staging_out(staging),
        payload      = _payload_out(payload),
        trajectory   = traj_out,
        constraints  = _constraints_out(report),
    )


def run_sensitivity(req: SensitivityRequest) -> SensitivityResponse:
    """
    Sweep one parameter over a list of values and collect key metrics.
    """
    import copy

    points: list[SensitivityPoint] = []

    for val in req.values:
        # Deep-copy the base request and set the swept parameter
        import json
        base_dict = req.base.model_dump()

        # Navigate the dot-path and set the value
        keys = req.parameter.split(".")
        node = base_dict
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = val

        swept_req = SimulationRequest.model_validate(base_dict)
        result = run_simulation(swept_req)

        if result.ok and result.payload and result.staging:
            points.append(SensitivityPoint(
                parameter_value    = val,
                payload_mass_kg    = result.payload.payload_mass_kg,
                max_payload_kg     = result.payload.max_payload_kg,
                delta_v_margin_m_s = result.payload.margin_to_orbit_m_s,
                mission_feasible   = result.payload.mission_feasible,
                limiting_factor    = result.payload.limiting_factor,
            ))
        else:
            points.append(SensitivityPoint(
                parameter_value    = val,
                payload_mass_kg    = 0.0,
                max_payload_kg     = None,
                delta_v_margin_m_s = -9999.0,
                mission_feasible   = False,
                limiting_factor    = "constraint_error",
            ))

    return SensitivityResponse(parameter=req.parameter, points=points)


def run_batch(req: BatchRequest) -> BatchResponse:
    """Run multiple independent simulations."""
    return BatchResponse(results=[run_simulation(r) for r in req.runs])
