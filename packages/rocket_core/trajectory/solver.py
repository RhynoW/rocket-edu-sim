"""
rocket_core.trajectory.solver
------------------------------
2-D point-mass ascent simulation (downrange x, altitude y).

Degrees of freedom: [x, y, vx, vy, mass]

Forces modelled:
  - Thrust     : phase-dependent guidance law (see below)
  - Gravity    : inverse-square, Earth-centred
  - Drag       : F_D = ½ ρ v² Cd A_ref  (exponential atmosphere)
  - Centrifugal: vx²/(R+alt) in local-vertical frame (spherical Earth)

Ascent sequence (two-burn Stage-2 profile):
  Phase 0  Vertical rise     0 → pitch_over_altitude_m
  Phase 1  Gravity turn      pitch kick → MECO  (cosine schedule, 90°→30°)
  Phase 2  S1/S2 coast       MECO → SES-1  (~10 s)
  Phase 3  S2 Burn 1         SES-1 → SECO-1  (prograde, terminates when
                             instantaneous orbit apogee = target altitude)
  Phase 4  Hohmann coast     SECO-1 → apogee  (no thrust, ~44 min for 400 km)
  Phase 5  S2 Burn 2         apogee → SECO-2  (prograde circularisation)

Notes:
  - No 6-DOF; attitude is controlled by the guidance law, not integrated.
  - Fairing jettisoned at t_ses1 + 50 s (during Burn 1).
  - Integration uses scipy RK45 with terminal event detection.
  - All SI units internally; results converted for display.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np
from scipy.integrate import solve_ivp

from rocket_core.vehicle.models import Vehicle
from rocket_core.propulsion.solver import (
    G0, atmospheric_pressure_Pa, thrust_at_altitude, P0
)

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

GM_EARTH:    float = 3.986_004_418e14  # m³/s²
R_EARTH:     float = 6_371_000.0       # m
RHO0:        float = 1.225             # kg/m³  sea-level air density
H_RHO_SCALE: float = 8_500.0          # m      density scale height

COAST_S:         float = 5.0   # seconds between MECO and SES-1
FAIRING_SEP_S:   float = 50.0  # seconds after SES-1 to drop fairing


# ---------------------------------------------------------------------------
# Atmosphere
# ---------------------------------------------------------------------------

def air_density_kg_m3(altitude_m: float) -> float:
    if altitude_m < 0:
        altitude_m = 0.0
    return RHO0 * math.exp(-altitude_m / H_RHO_SCALE)


def dynamic_pressure_Pa(velocity_m_s: float, altitude_m: float) -> float:
    rho = air_density_kg_m3(altitude_m)
    return 0.5 * rho * velocity_m_s ** 2


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TrajectoryPoint:
    t_s:          float
    altitude_m:   float
    downrange_m:  float
    velocity_m_s: float
    vx_m_s:       float
    vy_m_s:       float
    mass_kg:      float
    thrust_N:     float
    drag_N:       float
    q_Pa:         float      # dynamic pressure
    accel_g:      float      # net acceleration in g
    phase:        str


@dataclass
class TrajectoryResult:
    """Full ascent trajectory output."""
    timeline: List[TrajectoryPoint]

    # Key events
    max_q_Pa:         float
    max_q_time_s:     float
    max_q_altitude_m: float

    max_accel_g:      float
    burnout_velocity_m_s: float
    burnout_altitude_m:   float

    # Orbit insertion check
    target_altitude_m:    float
    target_velocity_m_s:  float   # circular orbital velocity
    achieved_velocity_m_s: float
    orbit_achieved:       bool

    # Δv actually achieved by integration
    integrated_delta_v_m_s: float

    # Warnings
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ODE right-hand side
# ---------------------------------------------------------------------------

def _odes(
    t: float,
    state: np.ndarray,
    vehicle: Vehicle,
    phase: str,
    t_pitch_over: float,
    t_meco: float,
) -> np.ndarray:
    """
    State: [x, y, vx, vy, mass]
    Returns dstate/dt.

    Guidance law:
      - vertical    : thrust straight up
      - gravity_turn: cosine pitch schedule from 90° at t_pitch_over to 30° at
                      t_meco.  Ending at 30° (not 0°) ensures Stage 2 starts with
                      ~1100 m/s upward momentum on a climbing arc to ~170+ km.
      - coast       : no thrust
      - stage2      : ZEV (Zero-Effort-Velocity) guidance with average centrifugal
                      correction.  At each instant, computes the pitch that brings
                      the vehicle to (v_circ, vy=0) at SECO using the mean
                      centrifugal correction between current vx and v_circ_target
                      to avoid over-steering early in the burn.
    """
    x, y, vx, vy, mass = state
    alt   = max(y, 0.0)
    v_mag = math.sqrt(vx**2 + vy**2) + 1e-9  # avoid /0

    # ---------- Gravity (inverse square) ----------
    r      = R_EARTH + alt
    g_mag  = GM_EARTH / r**2
    gx, gy = 0.0, -g_mag

    # ---------- Thrust direction ----------
    if phase == "vertical":
        thrust_dir_x, thrust_dir_y = 0.0, 1.0

    elif phase == "gravity_turn":
        # Cosine pitch programme: 90° (vertical) at t_pitch_over → MECO_PITCH at t_meco.
        # 30° ensures Stage 2 starts with ~1100 m/s upward velocity so the vehicle
        # climbs to ~200 km peak altitude during the Stage 2 burn.
        MECO_PITCH = math.radians(30.0)      # flight path angle at Stage 1 MECO
        t_prog  = max(t_meco - t_pitch_over, 1.0)
        frac    = max(0.0, min(1.0, (t - t_pitch_over) / t_prog))
        # Cosine schedule: 90° at frac=0  →  MECO_PITCH at frac=1
        pitch   = MECO_PITCH + (math.pi / 2.0 - MECO_PITCH) * 0.5 * (1.0 + math.cos(math.pi * frac))
        thrust_dir_x = math.cos(pitch)
        thrust_dir_y = math.sin(pitch)

    elif phase == "stage2_burn1":
        # ZEV guidance targeting the TRANSFER-ORBIT perigee velocity.
        #
        # For a Hohmann-like ascent, Burn 1 must end with the instantaneous
        # orbit having apogee = target altitude.  The required horizontal speed
        # at the current altitude r is the vis-viva perigee velocity:
        #
        #   v_transfer = sqrt( GM * (2/r − 1/a_transfer) )
        #   a_transfer = (r + r_target) / 2
        #
        # This target is ~270 m/s higher than v_circ(target), which is the
        # correct velocity to SET the apogee (not to orbit there).
        # ZEV with average centrifugal correction is used to compute pitch,
        # matching the same formulation as the circularisation guidance but
        # with the transfer-orbit target instead of v_circ.
        #
        # t_pitch_over / t_meco are repurposed as t_ses1 / t_burn1_max.
        # r = R_EARTH + alt, g_mag = GM/r² — both computed at top of _odes
        h_target_m  = vehicle.mission.target_altitude_km * 1_000.0
        r_target    = R_EARTH + h_target_m
        a_transfer  = (r + r_target) / 2.0
        v_tgt       = math.sqrt(GM_EARTH * (2.0 / r - 1.0 / a_transfer))

        T_go        = max(t_meco - t, 1.0)
        vx_avg      = (vx + v_tgt) / 2.0
        cent_avg    = vx_avg ** 2 / r
        g_net_avg   = max(g_mag - cent_avg, 0.0)

        dvy_tgt = -vy + g_net_avg * T_go
        dvx_tgt = max(v_tgt - vx, 1.0)
        pitch   = math.atan2(dvy_tgt, dvx_tgt)
        pitch   = max(0.0, min(math.radians(70.0), pitch))

        thrust_dir_x = math.cos(pitch)
        thrust_dir_y = math.sin(pitch)

    elif phase == "stage2_burn2":
        # Circularisation at apogee.  At apogee vy ≈ 0 so prograde ≈ horizontal.
        # Use prograde to handle any small residual vy gracefully.
        thrust_dir_x = vx / v_mag
        thrust_dir_y = vy / v_mag

    else:
        # coast / coast2: no thrust (handled by zero thrust_total below)
        thrust_dir_x, thrust_dir_y = 0.0, 1.0

    # ---------- Thrust magnitude ----------
    if phase in ("vertical", "gravity_turn"):
        s = vehicle.stage1
    else:
        s = vehicle.stage2   # stage2_burn1 / stage2_burn2 / coast / coast2

    eng = s.engine
    n   = s.engine_count

    if phase in ("coast", "coast2"):
        thrust_total = 0.0
        mdot_total   = 0.0
    else:
        # Throttle: 72 % during max-Q window (T=60–80 s, Stage 1 only)
        throttle = 0.72 if (phase == "gravity_turn" and 60.0 <= t <= 80.0) else 1.0

        # Propellant-exhaustion guard: stop burning when dry mass is reached
        if phase in ("vertical", "gravity_turn"):
            min_mass = (vehicle.stage1.dry_mass + vehicle.stage2.gross_mass_kg
                        + vehicle.payload_mass + vehicle.fairing_mass)
        else:  # stage2_burn1 / stage2_burn2
            min_mass = vehicle.stage2.dry_mass + vehicle.payload_mass

        if mass <= min_mass + 1.0:
            thrust_total = 0.0
            mdot_total   = 0.0
        else:
            thrust_per_engine, mdot_per_engine = thrust_at_altitude(
                eng.thrust_sl, eng.thrust_vac,
                eng.isp_sl,    eng.isp_vac,
                alt, throttle=throttle,
            )
            thrust_total = thrust_per_engine * n
            mdot_total   = mdot_per_engine   * n

    tx = thrust_total * thrust_dir_x
    ty = thrust_total * thrust_dir_y

    # ---------- Drag ----------
    v2       = vx**2 + vy**2
    rho      = air_density_kg_m3(alt)
    A_ref    = math.pi * (s.diameter_m / 2.0) ** 2
    Cd       = vehicle.sim_config.drag_coefficient
    drag_mag = 0.5 * rho * v2 * Cd * A_ref
    if v_mag > 1e-3:
        dx_drag = -drag_mag * vx / v_mag
        dy_drag = -drag_mag * vy / v_mag
    else:
        dx_drag = dy_drag = 0.0

    # ---------- Equations of motion ----------
    # In the 2-D LOCAL FRAME (x = downrange arc, y = altitude) the correct EOM
    # for a spherical Earth are:
    #
    #   dvx/dt = F_x/m  −  vy·vx / r          (tangential; −vy·vx/r conserves h = r·vx)
    #   dvy/dt = F_y/m  −  GM/r²  +  vx²/r    (radial;    +vx²/r is the centrifugal term)
    #
    # The centrifugal term in y makes circular orbital speed self-sustaining:
    #   at v_circ = sqrt(GM/r), vx²/r = GM/r² = g → net vertical acc = 0.
    #
    # The Coriolis-like term in x (-vy·vx/r) ensures angular-momentum conservation
    # (d(r·vx)/dt = 0 for unthrusted flight).  Without it, vx stays constant while
    # the vehicle climbs, so orbital energy grows without bound — a Hohmann coast
    # from 140 km to 400 km would spuriously escape Earth.
    centrifugal_y  = vx ** 2 / r           # r = R_EARTH + alt, computed above
    coriolis_x     = -(vy * vx) / r        # angular-momentum conservation

    ax    = (tx + dx_drag) / mass + gx + coriolis_x
    ay    = (ty + dy_drag) / mass + gy + centrifugal_y
    dm_dt = -mdot_total

    return np.array([vx, vy, ax, ay, dm_dt])


# ---------------------------------------------------------------------------
# Phase integrator
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Orbital mechanics helpers for event detection
# ---------------------------------------------------------------------------

def _instantaneous_apogee_alt_m(state: np.ndarray) -> float:
    """
    Compute the apogee altitude [m] of the instantaneous Keplerian orbit.

    In the 2-D local frame: vx is tangential (horizontal) and r = R_EARTH + alt.
    Specific angular momentum  h = r * vx.
    Returns a large sentinel for escape trajectories (E ≥ 0).
    """
    x, y, vx, vy, mass = state
    alt   = max(y, 0.0)
    r     = R_EARTH + alt
    v_sq  = vx ** 2 + vy ** 2
    if v_sq < 1.0 or vx <= 0.0:
        return alt          # degenerate / suborbital - no useful apogee

    E = v_sq / 2.0 - GM_EARTH / r
    if E >= 0.0:
        return R_EARTH * 100  # escape trajectory — sentinel > any target

    h_ang = r * vx             # specific angular momentum
    a     = -GM_EARTH / (2.0 * E)
    e2    = max(0.0, 1.0 - h_ang ** 2 / (a * GM_EARTH))
    e     = math.sqrt(e2)
    return a * (1.0 + e) - R_EARTH


def _make_apogee_target_event(target_apogee_m: float):
    """Terminal event: fires when instantaneous apogee reaches the target."""
    def event(t, state):
        return _instantaneous_apogee_alt_m(state) - target_apogee_m
    event.terminal  = True
    event.direction = 1     # only fire when apogee is rising through the target
    return event


def _make_apogee_reached_event():
    """Terminal event: fires when the vehicle reaches orbital apogee (vy → 0⁻)."""
    def event(t, state):
        return state[3]     # vy
    event.terminal  = True
    event.direction = -1    # fire when vy passes through zero going negative
    return event


def _make_circular_event():
    """
    Terminal event for Burn 2: fires when vx reaches circular-orbit speed at the
    current altitude (orbit has been circularised).

    At apogee, vy ≈ 0, so the orbit is circular when  vx = v_circ(alt) = sqrt(GM/r).
    The event function is  vx - v_circ(r), which rises from negative (pre-circularisation)
    to zero (exactly circular) as Burn 2 adds horizontal velocity.
    """
    def event(t, state):
        alt   = max(state[1], 0.0)
        r     = R_EARTH + alt
        v_circ = math.sqrt(GM_EARTH / r)
        return state[2] - v_circ   # vx - v_circ
    event.terminal  = True
    event.direction = 1     # fires when vx increases through v_circ
    return event


# ---------------------------------------------------------------------------
# Phase integrator
# ---------------------------------------------------------------------------

def _integrate_phase(
    t0: float,
    tf: float,
    state0: np.ndarray,
    vehicle: Vehicle,
    phase: str,
    dt: float,
    t_pitch_over: float,
    t_meco: float,
    events=None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Integrate one flight phase.

    If *events* is given, `solve_ivp` will terminate at the first terminal
    event.  Returns (t_array, states_array) up to and including that point.
    """
    t_eval = np.arange(t0, tf, dt)
    if len(t_eval) == 0 or t_eval[-1] < tf:
        t_eval = np.append(t_eval, tf)

    sol = solve_ivp(
        fun=lambda t, y: _odes(t, y, vehicle, phase, t_pitch_over, t_meco),
        t_span=(t0, tf),
        y0=state0,
        method="RK45",
        t_eval=t_eval,
        rtol=1e-3,
        atol=[1.0, 1.0, 0.1, 0.1, 1.0],   # pos(m), pos(m), vel(m/s), vel(m/s), mass(kg)
        max_step=dt * 2,
        events=events,
    )
    return sol.t, sol.y


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def simulate_trajectory(vehicle: Vehicle) -> TrajectoryResult:
    """
    Simulate 2-D ascent from liftoff to orbit insertion.

    Parameters
    ----------
    vehicle : Vehicle

    Returns
    -------
    TrajectoryResult
    """
    cfg = vehicle.sim_config
    s1  = vehicle.stage1
    s2  = vehicle.stage2
    mis = vehicle.mission
    dt  = cfg.dt_s

    pitch_over_alt   = cfg.pitch_over_altitude_m
    warnings: List[str] = []

    # Initial state: [x, y, vx, vy, mass]
    state0 = np.array([0.0, 0.0, 0.0, 0.1, vehicle.liftoff_mass_kg])

    # Estimate time to reach pitch-over altitude (rough: 150 m at ~0.5 g net)
    t_pitch_over = math.sqrt(2 * pitch_over_alt / (vehicle.liftoff_twr * G0 * 0.4))
    t_pitch_over = max(t_pitch_over, 5.0)

    # --- Propellant budget for phase end times ---
    from rocket_core.propulsion.solver import solve_propulsion
    prop_s1 = solve_propulsion(s1)
    prop_s2 = solve_propulsion(s2)

    t_meco       = prop_s1.burn_time_s
    t_sep        = t_meco  + COAST_S
    t_ses1       = t_sep   + COAST_S
    t_fair       = t_ses1  + FAIRING_SEP_S
    t_max_s2burn = t_ses1  + prop_s2.burn_time_s   # upper bound if no event fires

    target_apogee_m = mis.target_altitude_km * 1_000.0

    # ------------------------------------------------------------------ #
    # Phase 0: Vertical rise  (0 → t_pitch_over)
    # ------------------------------------------------------------------ #
    t_arr0, y_arr0 = _integrate_phase(
        0.0, t_pitch_over, state0, vehicle,
        "vertical", dt, t_pitch_over, t_meco
    )

    # No pitch-kick velocity rotation needed: the cosine pitch programme in
    # _odes smoothly pitches the vehicle from vertical at t_pitch_over to
    # horizontal at t_meco.  Just hand the state directly to Phase 1.
    state_after_vertical = y_arr0[:, -1].copy()

    # ------------------------------------------------------------------ #
    # Phase 1: Gravity turn  (t_pitch_over → MECO)
    # ------------------------------------------------------------------ #
    t_arr1, y_arr1 = _integrate_phase(
        t_pitch_over, t_meco, state_after_vertical, vehicle,
        "gravity_turn", dt, t_pitch_over, t_meco
    )

    # ------------------------------------------------------------------ #
    # Phase 2: Coast (MECO → SES-1) — no thrust, gravity + drag only
    # State mass: drop Stage 1 (dry mass)
    # ------------------------------------------------------------------ #
    state_at_meco = y_arr1[:, -1].copy()
    # At stage separation the entire Stage 1 (dry structure + any residual /
    # unburnt propellant) is physically jettisoned.  Reset the mass to the
    # correct Stage-2-stack value instead of merely subtracting s1.dry_mass:
    # this removes the ~15 t of unburnt S1 prop that accumulated from the
    # max-Q throttle-down and was otherwise carried as dead weight into S2.
    state_at_meco[4] = s2.gross_mass_kg + vehicle.payload_mass + vehicle.fairing_mass

    t_arr2, y_arr2 = _integrate_phase(
        t_meco, t_ses1, state_at_meco, vehicle,
        "coast", dt, t_pitch_over, t_meco
    )

    # ------------------------------------------------------------------ #
    # Phase 3  S2 Burn 1  (SES-1 → apogee = target altitude)
    #   Prograde guidance; event fires when instantaneous orbit apogee
    #   reaches target_altitude_km.  Split at fairing separation so the
    #   ODE integrates with the correct mass after jettison.
    # ------------------------------------------------------------------ #
    state_at_ses1   = y_arr2[:, -1].copy()
    apogee_evt      = _make_apogee_target_event(target_apogee_m)

    # 3-pre:  SES-1 → fairing separation (apogee event may fire early)
    t_arr3pre, y_arr3pre = _integrate_phase(
        t_ses1, t_fair, state_at_ses1, vehicle,
        "stage2_burn1", dt, t_ses1, t_max_s2burn,
        events=[apogee_evt],
    )
    seco1_before_fairing = t_arr3pre[-1] < t_fair - 0.5  # event fired early

    if seco1_before_fairing:
        # Apogee already reached before fairing drop – no need to continue
        t_arr_b1 = t_arr3pre
        y_arr_b1 = y_arr3pre
    else:
        # Drop fairing from state
        state_after_fair      = y_arr3pre[:, -1].copy()
        state_after_fair[4]   = max(
            state_after_fair[4] - vehicle.fairing_mass,
            s2.dry_mass + vehicle.payload_mass,
        )
        # 3-post: fairing separation → apogee event
        apogee_evt2 = _make_apogee_target_event(target_apogee_m)
        t_arr3post, y_arr3post = _integrate_phase(
            t_fair, t_max_s2burn, state_after_fair, vehicle,
            "stage2_burn1", dt, t_ses1, t_max_s2burn,
            events=[apogee_evt2],
        )
        t_arr_b1 = np.concatenate([t_arr3pre, t_arr3post])
        y_arr_b1 = np.concatenate([y_arr3pre, y_arr3post], axis=1)

    t_seco1        = t_arr_b1[-1]
    state_at_seco1 = y_arr_b1[:, -1].copy()

    # ------------------------------------------------------------------ #
    # Phase 4  Hohmann coast  (SECO-1 → apogee)
    #   No thrust; event fires when vy crosses zero (vehicle at apogee).
    #   Use coarser dt for this long (~44-min) coast.
    # ------------------------------------------------------------------ #
    dt_coast2   = max(dt * 10.0, 10.0)          # 10× coarser — sufficient for a coast arc
    t_coast_max = t_seco1 + 6_000.0             # ≫ half-period of any 400 km transfer orbit
    apogee_reach_evt = _make_apogee_reached_event()

    t_arr4, y_arr4 = _integrate_phase(
        t_seco1, t_coast_max, state_at_seco1, vehicle,
        "coast2", dt_coast2, t_ses1, t_max_s2burn,
        events=[apogee_reach_evt],
    )
    t_apogee        = t_arr4[-1]
    state_at_apogee = y_arr4[:, -1].copy()

    # ------------------------------------------------------------------ #
    # Phase 5  S2 Burn 2  (apogee circularisation)
    #   Prograde thrust until the orbit is circular (vx = v_circ at current alt).
    #   A propellant-exhaustion guard in _odes provides a hard backstop.
    # ------------------------------------------------------------------ #
    remaining_prop  = max(
        state_at_apogee[4] - (s2.dry_mass + vehicle.payload_mass), 0.0
    )
    mdot_vac        = s2.engine.thrust_vac / (s2.engine.isp_vac * G0)
    t_burn2_max     = t_apogee + remaining_prop / mdot_vac + 30.0   # hard upper bound

    circular_evt = _make_circular_event()
    t_arr5, y_arr5 = _integrate_phase(
        t_apogee, t_burn2_max, state_at_apogee, vehicle,
        "stage2_burn2", dt, t_ses1, t_max_s2burn,
        events=[circular_evt],
    )

    # ------------------------------------------------------------------ #
    # Assemble all arrays
    # ------------------------------------------------------------------ #
    t_arr3 = t_arr_b1           # Burn 1 (phase label: "stage2_burn1")
    y_arr3 = y_arr_b1

    # ------------------------------------------------------------------ #
    # Assemble timeline  (all six phases)
    # ------------------------------------------------------------------ #
    all_t = np.concatenate([t_arr0, t_arr1, t_arr2, t_arr3, t_arr4, t_arr5])
    all_y = np.concatenate([y_arr0, y_arr1, y_arr2, y_arr3, y_arr4, y_arr5], axis=1)

    phase_labels = (
        [(t, "vertical")       for t in t_arr0] +
        [(t, "gravity_turn")   for t in t_arr1] +
        [(t, "coast")          for t in t_arr2] +
        [(t, "stage2_burn1")   for t in t_arr3] +
        [(t, "coast2")         for t in t_arr4] +
        [(t, "stage2_burn2")   for t in t_arr5]
    )
    phase_map = {t: p for t, p in phase_labels}

    points: List[TrajectoryPoint] = []
    max_q_Pa     = 0.0
    max_q_time   = 0.0
    max_q_alt    = 0.0
    max_accel_g  = 0.0
    prev_v       = 0.0
    int_dv       = 0.0

    for i in range(len(all_t)):
        t   = all_t[i]
        x, y_pos, vx, vy, mass = all_y[:, i]
        alt = max(y_pos, 0.0)
        v   = math.sqrt(vx**2 + vy**2)

        # Drag
        rho   = air_density_kg_m3(alt)
        q_Pa  = 0.5 * rho * v**2

        phase_str = phase_map.get(t, "unknown")
        s = s1 if phase_str in ("vertical", "gravity_turn") else s2

        A_ref    = math.pi * (s.diameter_m / 2)**2
        drag_mag = q_Pa * vehicle.sim_config.drag_coefficient * A_ref

        # Net acceleration (simplified)
        if phase_str in ("coast", "coast2"):
            thrust_here = 0.0
            net_a_g = 0.0
        else:
            thrust_here, _ = thrust_at_altitude(
                s.engine.thrust_sl, s.engine.thrust_vac,
                s.engine.isp_sl,    s.engine.isp_vac,
                alt
            )
            thrust_here *= s.engine_count
            g_local = GM_EARTH / (R_EARTH + alt)**2
            net_a_g = abs(thrust_here - drag_mag - mass * g_local) / (mass * G0)

        # Track max-q
        if q_Pa > max_q_Pa:
            max_q_Pa, max_q_time, max_q_alt = q_Pa, t, alt

        # Track max-accel
        if net_a_g > max_accel_g:
            max_accel_g = net_a_g

        # Δv integration (trapezoidal)
        if i > 0:
            int_dv += abs(v - prev_v)
        prev_v = v

        points.append(TrajectoryPoint(
            t_s=round(t, 2),
            altitude_m=round(alt, 1),
            downrange_m=round(x, 1),
            velocity_m_s=round(v, 2),
            vx_m_s=round(vx, 2),
            vy_m_s=round(vy, 2),
            mass_kg=round(mass, 1),
            thrust_N=round(thrust_here, 0),
            drag_N=round(drag_mag, 0),
            q_Pa=round(q_Pa, 1),
            accel_g=round(net_a_g, 3),
            phase=phase_str,
        ))

    # ------------------------------------------------------------------ #
    # Orbit check
    # ------------------------------------------------------------------ #
    final_state  = all_y[:, -1]
    burnout_v    = math.sqrt(final_state[2]**2 + final_state[3]**2)
    burnout_alt  = max(final_state[1], 0.0)

    target_h      = mis.target_altitude_km * 1_000.0
    target_v_circ = math.sqrt(GM_EARTH / (R_EARTH + target_h))

    # With the two-burn profile, SECO-2 occurs at the target apogee (~400 km)
    # where the vehicle is near-circular.  Compare burnout speed against the
    # circular speed at the actual burnout altitude.
    v_circ_at_burnout = math.sqrt(GM_EARTH / (R_EARTH + burnout_alt))
    v_esc_at_burnout  = v_circ_at_burnout * math.sqrt(2.0)

    alt_ok   = burnout_alt >= 80_000.0
    v_ok     = (burnout_v >= v_circ_at_burnout * 0.97 and
                burnout_v <= v_esc_at_burnout)
    orbit_ok = alt_ok and v_ok

    if not orbit_ok:
        if burnout_alt < 80_000.0:
            warnings.append(
                f"Burnout altitude {burnout_alt/1000:.1f} km is below 80 km — "
                f"vehicle did not clear the atmosphere"
            )
        if burnout_v < v_circ_at_burnout * 0.97:
            warnings.append(
                f"Burnout velocity {burnout_v:.0f} m/s is below circular orbit speed "
                f"at burnout altitude ({v_circ_at_burnout:.0f} m/s)"
            )
    if burnout_alt < target_h * 0.85:
        warnings.append(
            f"Burnout altitude {burnout_alt/1000:.1f} km is below target "
            f"{mis.target_altitude_km:.1f} km"
        )

    if max_q_Pa > cfg.max_dynamic_pressure_Pa:
        warnings.append(
            f"Max-Q {max_q_Pa/1000:.1f} kPa exceeds limit {cfg.max_dynamic_pressure_Pa/1000:.1f} kPa"
        )
    if max_accel_g > cfg.max_acceleration_g:
        warnings.append(
            f"Peak acceleration {max_accel_g:.2f} g exceeds limit {cfg.max_acceleration_g:.1f} g"
        )

    return TrajectoryResult(
        timeline              = points,
        max_q_Pa              = round(max_q_Pa, 1),
        max_q_time_s          = round(max_q_time, 1),
        max_q_altitude_m      = round(max_q_alt, 0),
        max_accel_g           = round(max_accel_g, 3),
        burnout_velocity_m_s  = round(burnout_v, 1),
        burnout_altitude_m    = round(burnout_alt, 0),
        target_altitude_m     = target_h,
        target_velocity_m_s   = round(target_v_circ, 1),
        achieved_velocity_m_s = round(burnout_v, 1),
        orbit_achieved        = orbit_ok,
        integrated_delta_v_m_s = round(int_dv, 1),
        warnings              = warnings,
    )
