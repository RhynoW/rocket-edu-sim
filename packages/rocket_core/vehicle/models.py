"""
rocket_core.vehicle.models
--------------------------
Shared Pydantic v2 data models for Vehicle, Stage, Engine,
Propellant, Mission, and SimulationConfig.

Reference baseline (Falcon 9-like, publicly cited values):
  Total liftoff mass : ~549 054 kg
  Stage 1 thrust (SL): ~7 605 kN  (9 × Merlin 1D)
  Stage 2 thrust (vac): ~981 kN   (1 × Merlin 1D Vacuum)
  LEO payload         : ~22 800 kg
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class OrbitType(str, Enum):
    LEO = "LEO"
    SSO = "SSO"
    GTO = "GTO"


class PropellantType(str, Enum):
    LOX_RP1  = "LOX/RP-1"
    LOX_LH2  = "LOX/LH2"
    LOX_CH4  = "LOX/CH4"
    NTO_MMH  = "NTO/MMH"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class Engine(BaseModel):
    """Single engine definition.  All force values in Newtons, mass in kg."""

    name: str = Field(..., description="Engine designation, e.g. 'Merlin 1D'")

    # Thrust
    thrust_sl:  float = Field(..., gt=0, description="Sea-level thrust per engine [N]")
    thrust_vac: float = Field(..., gt=0, description="Vacuum thrust per engine [N]")

    # Specific impulse
    isp_sl:  float = Field(..., gt=0, description="Sea-level Isp [s]")
    isp_vac: float = Field(..., gt=0, description="Vacuum Isp [s]")

    # Physical
    mass: float = Field(..., gt=0, description="Dry mass of one engine [kg]")
    diameter_m: float = Field(default=1.0, gt=0, description="Engine bell exit diameter [m]")

    # Propellant
    fuel_type:     str   = Field(default="RP-1", description="Fuel name")
    oxidizer_type: str   = Field(default="LOX",  description="Oxidizer name")
    mixture_ratio: float = Field(default=2.36, gt=0, description="O/F mass ratio")

    # Throttle limits
    throttle_min: float = Field(default=0.57, ge=0.0, le=1.0,
                                description="Minimum throttle fraction (e.g. 0.57 = 57%)")
    throttle_max: float = Field(default=1.0,  ge=0.0, le=1.0,
                                description="Maximum throttle fraction")

    can_restart: bool = Field(default=False,
                              description="True for upper-stage engines that support restart")


# ---------------------------------------------------------------------------
# Propellant
# ---------------------------------------------------------------------------

class Propellant(BaseModel):
    """Propellant combination properties."""

    propellant_type: PropellantType = PropellantType.LOX_RP1

    fuel_name:            str   = Field(default="RP-1")
    oxidizer_name:        str   = Field(default="LOX")
    fuel_density_kg_m3:   float = Field(default=820.0,  gt=0,
                                        description="Fuel bulk density [kg/m³]")
    oxidizer_density_kg_m3: float = Field(default=1141.0, gt=0,
                                          description="Oxidizer bulk density [kg/m³]")
    mixture_ratio: float = Field(default=2.36, gt=0, description="O/F mass ratio")

    @property
    def bulk_density_kg_m3(self) -> float:
        """Effective propellant bulk density accounting for O/F ratio."""
        r = self.mixture_ratio
        return (1 + r) / (1 / self.fuel_density_kg_m3 + r / self.oxidizer_density_kg_m3)


# ---------------------------------------------------------------------------
# Dead-weight breakdown (educational detail)
# ---------------------------------------------------------------------------

class DeadWeightBreakdown(BaseModel):
    """Optional itemised dry-mass breakdown for a single stage."""

    structural_shell_kg:    Optional[float] = Field(default=None, ge=0)
    propellant_tanks_kg:    Optional[float] = Field(default=None, ge=0)
    engines_kg:             Optional[float] = Field(default=None, ge=0)
    avionics_kg:            Optional[float] = Field(default=None, ge=0)
    interstage_kg:          Optional[float] = Field(default=None, ge=0)
    fairing_kg:             Optional[float] = Field(default=None, ge=0)
    recovery_hardware_kg:   Optional[float] = Field(default=None, ge=0,
                                                     description="Grid fins, landing legs, etc.")
    reserve_propellant_kg:  Optional[float] = Field(default=None, ge=0,
                                                     description="Unusable / reserve propellant")

    def total(self) -> float:
        return sum(
            v for v in [
                self.structural_shell_kg, self.propellant_tanks_kg,
                self.engines_kg, self.avionics_kg, self.interstage_kg,
                self.fairing_kg, self.recovery_hardware_kg, self.reserve_propellant_kg,
            ] if v is not None
        )


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------

class Stage(BaseModel):
    """Single rocket stage definition."""

    # Mass
    dry_mass:  float = Field(..., gt=0, description="Dry mass of stage (excl. engine mass) [kg]")
    prop_mass: float = Field(..., gt=0, description="Total propellant mass [kg]")

    # Engine
    engine:       Engine = Field(..., description="Engine model for this stage")
    engine_count: int    = Field(..., ge=1, description="Number of engines")

    # Geometry
    diameter_m: float = Field(default=3.7, gt=0, description="Stage outer diameter [m]")

    # Structural
    structural_limit_factor: float = Field(default=1.25, ge=1.0,
                                           description="Structural safety factor")

    # Burn profile
    burn_time: Optional[float] = Field(default=None, gt=0,
                                       description="Burn time [s]; auto-computed if None")
    throttle_schedule: List[float] = Field(
        default=[1.0],
        description="Throttle fractions at equal-time steps during burn"
    )

    # Optional dead-weight detail
    dead_weight: Optional[DeadWeightBreakdown] = None

    # Derived convenience
    @property
    def total_engine_mass_kg(self) -> float:
        return self.engine.mass * self.engine_count

    @property
    def gross_mass_kg(self) -> float:
        return self.dry_mass + self.prop_mass

    @property
    def thrust_sl_total_N(self) -> float:
        return self.engine.thrust_sl * self.engine_count

    @property
    def thrust_vac_total_N(self) -> float:
        return self.engine.thrust_vac * self.engine_count

    @property
    def structure_fraction(self) -> float:
        """dry_mass / (dry_mass + prop_mass) — lower is better."""
        return self.dry_mass / (self.dry_mass + self.prop_mass)


# ---------------------------------------------------------------------------
# Mission
# ---------------------------------------------------------------------------

class Mission(BaseModel):
    """Target mission parameters."""

    orbit_type:            OrbitType = OrbitType.LEO
    target_altitude_km:    float     = Field(default=550.0, gt=0,
                                             description="Target orbit altitude [km]")
    target_inclination_deg: float    = Field(default=53.0, ge=0.0, le=180.0,
                                             description="Target orbit inclination [deg]")
    reusable_booster:      bool      = Field(default=True,
                                             description="True = Stage 1 performs landing burn")
    reusable_penalty_kg:   float     = Field(default=0.0, ge=0,
                                             description="Extra dry mass for recovery hardware [kg]")

    # Required delta-v to reach target orbit (used by payload estimator).
    # Will be auto-filled by payload solver if left None.
    required_delta_v_m_s: Optional[float] = Field(default=None, gt=0)


# ---------------------------------------------------------------------------
# SimulationConfig
# ---------------------------------------------------------------------------

class SimulationConfig(BaseModel):
    """Numerical integration and atmospheric model settings."""

    dt_s:                     float = Field(default=0.5,   gt=0,  description="Integration timestep [s]")
    pitch_over_altitude_m:    float = Field(default=200.0, gt=0,  description="Altitude to begin gravity turn [m]")
    pitch_over_kick_deg:      float = Field(default=3.0,   gt=0,  description="Initial pitch kick off vertical [deg]")
    max_dynamic_pressure_Pa:  float = Field(default=50_000.0, gt=0,
                                            description="Max-Q design limit [Pa]")
    max_acceleration_g:       float = Field(default=5.0,   gt=0,
                                            description="Max structural g-load limit")
    drag_coefficient:         float = Field(default=0.3,   gt=0,  description="Vehicle Cd")
    gravity_loss_estimate_m_s: float = Field(default=1_500.0, ge=0,
                                              description="Estimated gravity+drag losses [m/s]")


# ---------------------------------------------------------------------------
# Vehicle (top-level assembly)
# ---------------------------------------------------------------------------

class Vehicle(BaseModel):
    """Complete two-stage launch vehicle assembly."""

    name:         str    = Field(default="Two-Stage Vehicle")
    stage1:       Stage  = Field(..., description="First stage (booster)")
    stage2:       Stage  = Field(..., description="Second stage (upper stage)")
    payload_mass: float  = Field(..., ge=0, description="Payload mass [kg]")
    fairing_mass: float  = Field(default=1_900.0, ge=0, description="Payload fairing mass [kg]")
    propellant:   Propellant = Field(default_factory=Propellant)
    mission:      Mission    = Field(default_factory=Mission)
    sim_config:   SimulationConfig = Field(default_factory=SimulationConfig)

    @property
    def liftoff_mass_kg(self) -> float:
        return (
            self.stage1.gross_mass_kg
            + self.stage2.gross_mass_kg
            + self.payload_mass
            + self.fairing_mass
        )

    @property
    def liftoff_twr(self) -> float:
        """Liftoff thrust-to-weight ratio."""
        return self.stage1.thrust_sl_total_N / (self.liftoff_mass_kg * 9.80665)

    @model_validator(mode="after")
    def _check_liftoff_twr(self) -> "Vehicle":
        if self.liftoff_twr < 1.0:
            raise ValueError(
                f"Liftoff T/W = {self.liftoff_twr:.3f} < 1.0 — vehicle cannot lift off."
            )
        return self


# ---------------------------------------------------------------------------
# SimulationInput  (what the API receives)
# ---------------------------------------------------------------------------

class SimulationInput(BaseModel):
    """Flat API request payload — mirrors Vehicle but allows partial overrides."""

    vehicle: Vehicle
    run_label: Optional[str] = Field(default=None,
                                     description="Optional label for this simulation run")
