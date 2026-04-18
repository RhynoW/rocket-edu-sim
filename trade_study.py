#!/usr/bin/env python3
"""
trade_study.py
==============
雙語（英文／繁體中文）引導式設計權衡研究工具
Bilingual (English / Traditional Chinese) guided trade-study CLI
for the Falcon 9-like Rocket Educational Simulator.

執行方式 Run:
    python trade_study.py
"""

from __future__ import annotations

import copy
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# rocket_core imports
# ---------------------------------------------------------------------------

try:
    from rocket_core.vehicle.models import (
        Engine, Stage, Mission, Propellant, SimulationConfig, Vehicle,
    )
    from rocket_core.mass_budget.solver   import solve_mass_budget
    from rocket_core.staging.solver       import solve_staging
    from rocket_core.payload.solver       import estimate_payload
    from rocket_core.constraints.checker  import check_constraints
except ImportError:
    print("\n[ERROR] rocket_core 未安裝。請執行：pip install -e packages/rocket_core")
    print("[ERROR] rocket_core not installed. Run: pip install -e packages/rocket_core\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Baseline vehicle
# ---------------------------------------------------------------------------

BASELINE: Dict[str, Any] = {
    "stage1": {
        "dry_mass": 22200, "prop_mass": 411000,
        "engine_count": 9, "diameter_m": 3.7,
        "engine": {"name": "Merlin 1D", "thrust_sl": 845000,
                   "thrust_vac": 934000, "isp_sl": 282, "isp_vac": 311, "mass": 470},
    },
    "stage2": {
        "dry_mass": 4000, "prop_mass": 107500,
        "engine_count": 1, "diameter_m": 3.7,
        "engine": {"name": "Merlin 1D Vacuum", "thrust_sl": 0.001,
                   "thrust_vac": 981000, "isp_sl": 100, "isp_vac": 348, "mass": 490},
    },
    "payload_mass": 22800, "fairing_mass": 1900,
    "propellant": {"oxidiser": "LOX", "fuel": "RP1", "mixture_ratio": 2.56},
    "mission": {"target_altitude_km": 400, "reusable_booster": False,
                "reusable_penalty_kg": 0, "required_delta_v_m_s": None},
    "sim_config": {"gravity_loss_estimate_m_s": 1200, "max_q_throttle_fraction": 0.72},
}

# ---------------------------------------------------------------------------
# Bilingual parameter catalogue
# ---------------------------------------------------------------------------

PARAMETERS = [
    {"id": "payload_mass",  "dot_path": "payload_mass",
     "label_en": "Payload Mass",       "label_zh": "酬載質量",
     "unit": "kg",  "default_min": 5000,   "default_max": 30000,  "default_steps": 6},
    {"id": "s1_prop",       "dot_path": "stage1.prop_mass",
     "label_en": "S1 Propellant Mass", "label_zh": "第一節推進劑質量",
     "unit": "kg",  "default_min": 300000, "default_max": 500000, "default_steps": 5},
    {"id": "s2_prop",       "dot_path": "stage2.prop_mass",
     "label_en": "S2 Propellant Mass", "label_zh": "第二節推進劑質量",
     "unit": "kg",  "default_min": 70000,  "default_max": 150000, "default_steps": 5},
    {"id": "s1_dry",        "dot_path": "stage1.dry_mass",
     "label_en": "S1 Dry Mass",        "label_zh": "第一節乾重",
     "unit": "kg",  "default_min": 15000,  "default_max": 35000,  "default_steps": 5},
    {"id": "s2_dry",        "dot_path": "stage2.dry_mass",
     "label_en": "S2 Dry Mass",        "label_zh": "第二節乾重",
     "unit": "kg",  "default_min": 2500,   "default_max": 8000,   "default_steps": 5},
    {"id": "s2_isp",        "dot_path": "stage2.engine.isp_vac",
     "label_en": "S2 Vacuum Isp",      "label_zh": "第二節真空比衝",
     "unit": "s",   "default_min": 320,    "default_max": 390,    "default_steps": 8},
    {"id": "target_alt",    "dot_path": "mission.target_altitude_km",
     "label_en": "Target Altitude",    "label_zh": "目標高度",
     "unit": "km",  "default_min": 200,    "default_max": 800,    "default_steps": 7},
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_vehicle(cfg: dict) -> Vehicle:
    def _eng(d):
        e = d["engine"]
        return Engine(name=e["name"], thrust_sl=e["thrust_sl"], thrust_vac=e["thrust_vac"],
                      isp_sl=e["isp_sl"], isp_vac=e["isp_vac"], mass=e["mass"])
    def _stg(d):
        return Stage(dry_mass=d["dry_mass"], prop_mass=d["prop_mass"],
                     engine=_eng(d), engine_count=d["engine_count"], diameter_m=d["diameter_m"])
    p = cfg.get("propellant", {})
    m = cfg.get("mission", {})
    c = cfg.get("sim_config", {})
    return Vehicle(
        stage1=_stg(cfg["stage1"]), stage2=_stg(cfg["stage2"]),
        payload_mass=cfg["payload_mass"], fairing_mass=cfg.get("fairing_mass", 1900),
        propellant=Propellant(fuel_name=str(p.get("fuel", "RP-1")),
                              oxidizer_name=str(p.get("oxidiser", "LOX")),
                              mixture_ratio=float(p.get("mixture_ratio", 2.56))),
        mission=Mission(target_altitude_km=float(m.get("target_altitude_km", 400)),
                        reusable_booster=bool(m.get("reusable_booster", False)),
                        reusable_penalty_kg=float(m.get("reusable_penalty_kg", 0)),
                        required_delta_v_m_s=m.get("required_delta_v_m_s")),
        sim_config=SimulationConfig(
            gravity_loss_estimate_m_s=float(c.get("gravity_loss_estimate_m_s", 1200)),
            max_q_throttle_fraction=float(c.get("max_q_throttle_fraction", 0.72)),
        ),
    )


def run_one(cfg: dict) -> Optional[dict]:
    try:
        v = _build_vehicle(cfg)
        if check_constraints(v).error_messages:
            return None
        mb  = solve_mass_budget(v)
        stg = solve_staging(v)
        pl  = estimate_payload(v, stg)
        return {
            "liftoff_mass_kg":  mb.liftoff_mass_kg,
            "liftoff_twr":      round(mb.liftoff_twr, 3),
            "payload_mass_kg":  pl.payload_mass_kg,
            "payload_fraction": round(pl.payload_fraction, 4),
            "total_dv_m_s":     round(stg.usable_delta_v_m_s, 0),
            "dv_margin_m_s":    round(pl.margin_to_orbit_m_s, 0),
            "mission_feasible": pl.mission_feasible,
            "max_payload_kg":   pl.max_payload_kg,
            "limiting_factor":  pl.limiting_factor,
        }
    except Exception as exc:
        print(f"  [error] {exc}")
        return None


def _deep_get(obj: dict, dot_path: str) -> Any:
    for k in dot_path.split("."):
        obj = obj[k]
    return obj


def _deep_set(obj: dict, dot_path: str, value: Any) -> dict:
    obj = copy.deepcopy(obj)
    node = obj
    for k in dot_path.split(".")[:-1]:
        node = node[k]
    node[dot_path.split(".")[-1]] = value
    return obj


def linspace(lo: float, hi: float, n: int) -> List[float]:
    if n < 2:
        return [lo]
    step = (hi - lo) / (n - 1)
    return [round(lo + i * step, 4) for i in range(n)]

# ---------------------------------------------------------------------------
# CLI actions
# ---------------------------------------------------------------------------

def _print_summary(r: dict) -> None:
    feas = "YES 是" if r["mission_feasible"] else "NO 否"
    print(f"  起飛質量  Liftoff mass:     {r['liftoff_mass_kg']:>12,.0f} kg")
    print(f"  起飛推重比 Liftoff TWR:     {r['liftoff_twr']:>12.3f}")
    print(f"  酬載質量  Payload mass:     {r['payload_mass_kg']:>12,.0f} kg")
    print(f"  酬載分率  Payload fraction: {r['payload_fraction']*100:>11.2f} %")
    print(f"  可用 ΔV   Usable ΔV:       {r['total_dv_m_s']:>12,.0f} m/s")
    print(f"  ΔV 餘量   Margin:          {r['dv_margin_m_s']:>12,.0f} m/s")
    print(f"  任務可行  Feasible:         {feas}")
    if r.get("max_payload_kg") is not None:
        print(f"  最大酬載  Max payload:    {r['max_payload_kg']:>12,.0f} kg")
    print(f"  限制因素  Limiting factor:  {r.get('limiting_factor', 'n/a')}")


def run_baseline() -> None:
    print("\n" + "="*60)
    print("  基準模擬 Baseline Simulation")
    print("="*60)
    r = run_one(BASELINE)
    if r:
        _print_summary(r)
    else:
        print("  Baseline simulation failed.")


def run_sweep() -> None:
    print("\n" + "="*60)
    print("  單參數掃描 Single-Parameter Sweep")
    print("="*60)
    for i, p in enumerate(PARAMETERS):
        print(f"  {i+1:2d}. {p['label_en']} / {p['label_zh']}  [{p['unit']}]")
    try:
        idx   = int(input("\n  選擇參數編號 Select number: ").strip()) - 1
        param = PARAMETERS[idx]
    except (ValueError, IndexError):
        print("  Invalid selection.")
        return

    bval = _deep_get(BASELINE, param["dot_path"])
    print(f"\n  基準值 Baseline: {bval} {param['unit']}")
    print(f"  建議範圍 Suggested: {param['default_min']} – {param['default_max']}")
    try:
        lo    = float(input(f"  Min [{param['unit']}] (Enter={param['default_min']}): ").strip() or param["default_min"])
        hi    = float(input(f"  Max [{param['unit']}] (Enter={param['default_max']}): ").strip() or param["default_max"])
        steps = int(input(f"  Steps (Enter={param['default_steps']}): ").strip() or param["default_steps"])
    except ValueError:
        print("  Invalid input.")
        return

    values = linspace(lo, hi, steps)
    print(f"\n  {'Value':>12}  {'Payload (kg)':>14}  {'Margin (m/s)':>14}  {'Feasible':>10}")
    print("  " + "-"*56)

    rows: List[dict] = []
    for val in values:
        cfg = _deep_set(BASELINE, param["dot_path"], val)
        res = run_one(cfg)
        if res:
            f = "YES" if res["mission_feasible"] else "NO"
            print(f"  {val:>12,.1f}  {res['payload_mass_kg']:>14,.0f}  {res['dv_margin_m_s']:>14,.0f}  {f:>10}")
            rows.append({"value": val, **res})
        else:
            print(f"  {val:>12,.1f}  {'ERROR':>14}")
            rows.append({"value": val})

    if rows and input("\n  Save to CSV? [y/N]: ").strip().lower() == "y":
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path("results") / f"sweep_{param['id']}_{ts}.csv"
        path.parent.mkdir(exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        print(f"  Saved → {path}")


def main() -> None:
    print("\n🚀 Falcon 9-like Rocket Educational Simulator — CLI Mode")
    print("   (calls rocket_core directly — no server required)\n")

    while True:
        print("\n  1. Baseline simulation  基準模擬")
        print("  2. Single-parameter sweep  單參數掃描")
        print("  3. Quit  離開")
        choice = input("\n  Choose [1/2/3]: ").strip()
        if choice == "1":
            run_baseline()
        elif choice == "2":
            run_sweep()
        elif choice == "3":
            print("\n  Goodbye! 再見！\n")
            break
        else:
            print("  Please enter 1, 2, or 3.")


if __name__ == "__main__":
    main()
