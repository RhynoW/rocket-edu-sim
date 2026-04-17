#!/usr/bin/env python3
"""
trade_study.py
==============
雙語（英文／繁體中文）引導式設計權衡研究工具
Bilingual (English / Traditional Chinese) guided trade-study CLI
for the Falcon 9-like Rocket Educational Simulator.

執行方式 Run:
    python trade_study.py
    python trade_study.py --url http://127.0.0.1:8000
"""

from __future__ import annotations

import copy
import csv
import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    print("\n[ERROR] 尚未安裝 'requests' 套件。請執行：pip install requests")
    print("[ERROR] 'requests' not installed. Run: pip install requests\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# API & defaults
# ---------------------------------------------------------------------------

API_BASE = "http://127.0.0.1:8000"

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
    "sim_config": {"gravity_loss_estimate_m_s": 1200,
                   "max_q_throttle_fraction": 0.72, "run_trajectory": False},
}

# ---------------------------------------------------------------------------
# Bilingual parameter catalogue
# ---------------------------------------------------------------------------

PARAMETERS: List[Dict[str, Any]] = [
    {
        "id": "payload_mass",
        "label":    "Payload Mass",
        "label_zh": "酬載質量",
        "unit": "kg",
        "dot_path": "payload_mass",
        "default_min": 5000.0, "default_max": 30000.0, "default_steps": 8,
        "desc":    "Mass of the spacecraft or satellite delivered to orbit.",
        "desc_zh": "送入軌道的太空船或衛星質量。",
        "note":    "Heavier payloads consume ΔV budget — watch the margin shrink.",
        "note_zh": "較重的酬載會消耗速度增量預算，隨酬載增加，任務餘量逐漸縮小。",
        "teacher":
            "In the rocket equation Δv = Isp·g₀·ln(m₀/m_f), payload is inside m_f (the denominator of "
            "the mass ratio). Because of the logarithm, the relationship is nonlinear: each extra tonne "
            "of payload costs proportionally more ΔV as the vehicle grows heavier. "
            "Classroom exercise: find the payload mass that reduces ΔV margin to exactly zero.",
        "teacher_zh":
            "在火箭方程式 Δv = Isp × g₀ × ln(m₀/m_f) 中，酬載質量包含於終態質量 m_f 內。"
            "由於對數函數的特性，每增加一噸酬載，所消耗的 ΔV 會隨載具總質量增大而愈來愈多（非線性）。"
            "課堂練習：請學生求出使 ΔV 餘量恰好歸零的最大酬載質量。",
    },
    {
        "id": "stage2_dry_mass",
        "label":    "Stage 2 Dry Mass",
        "label_zh": "第二節乾重",
        "unit": "kg",
        "dot_path": "stage2.dry_mass",
        "default_min": 2000.0, "default_max": 8000.0, "default_steps": 7,
        "desc":    "Upper stage structural mass: tanks, wiring, avionics, engine mount.",
        "desc_zh": "上節結構質量，包括推進劑槽、電路、航電與發動機架。",
        "note":    "S2 dry mass reduces payload ~1-for-1 at constant propellant.",
        "note_zh": "推進劑不變時，第二節乾重每增加 1 kg，酬載大約減少 1 kg。",
        "teacher":
            "The upper stage structure fraction (dry/gross) targets 3–6% for high-performance vehicles. "
            "Falcon 9 S2 achieves ~3.6% through aluminium-lithium alloy tanks and composite structures. "
            "Ask: if S2 dry mass were halved, how much payload would be gained? "
            "Compare this 'structural sensitivity' with the payload sensitivity from the sweep.",
        "teacher_zh":
            "高性能上節的結構分率（乾重／總重）目標為 3–6%。"
            "獵鷹 9 號第二節達到約 3.6%，得益於鋁鋰合金推進劑槽與複合材料結構。"
            "討論：若第二節乾重減半，可多攜帶多少酬載？"
            "將此「結構靈敏度」與酬載掃描結果相比較，有助於學生建立量化直覺。",
    },
    {
        "id": "stage2_prop_mass",
        "label":    "Stage 2 Propellant Mass",
        "label_zh": "第二節推進劑質量",
        "unit": "kg",
        "dot_path": "stage2.prop_mass",
        "default_min": 60000.0, "default_max": 150000.0, "default_steps": 7,
        "desc":    "Propellant loaded in the upper stage for orbit insertion.",
        "desc_zh": "上節用於軌道插入燃燒的推進劑質量。",
        "note":    "More S2 propellant → more orbit-insertion ΔV but also heavier liftoff.",
        "note_zh": "第二節推進劑愈多，軌道插入 ΔV 愈充裕，但同時增加起飛總質量。",
        "teacher":
            "Classic staging trade-off: adding S2 propellant increases liftoff mass, which reduces S1's "
            "mass ratio and therefore S1's ΔV contribution. "
            "The Lagrange condition for optimal two-stage rockets states that, when structure fractions "
            "are equal, both stages should have the same mass ratio. "
            "In practice, different Isp and structure fractions shift the optimum toward a heavier Stage 1 "
            "(Falcon 9: ~80% of propellant in S1).",
        "teacher_zh":
            "這是經典的分節取捨問題：增加第二節推進劑會使起飛質量增大，進而降低第一節的質量比，"
            "減少第一節對 ΔV 的貢獻。"
            "兩節火箭的拉格朗日最佳化條件指出：當結構分率相等時，兩節最佳質量比相同。"
            "實際上，不同的比衝與結構分率使最佳解偏向較重的第一節"
            "（獵鷹 9 號：約 80% 推進劑在第一節）。",
    },
    {
        "id": "stage1_prop_mass",
        "label":    "Stage 1 Propellant Mass",
        "label_zh": "第一節推進劑質量",
        "unit": "kg",
        "dot_path": "stage1.prop_mass",
        "default_min": 280000.0, "default_max": 520000.0, "default_steps": 6,
        "desc":    "Booster propellant — dominant ΔV contributor (~80% of total).",
        "desc_zh": "推進器推進劑，是總速度增量最主要的來源（約占 80%）。",
        "note":    "Gains follow the log curve — each extra tonne buys less ΔV than the last.",
        "note_zh": "增益遵循對數曲線——每多加一噸推進劑，獲得的 ΔV 愈來愈少。",
        "teacher":
            "Δv = Isp·g₀·ln(m₀/m_f). Doubling propellant does NOT double ΔV. "
            "For Falcon 9 S1, going from 400 t to 500 t propellant adds only ~240 m/s ΔV "
            "while increasing liftoff mass by 100 t — a poor trade for payload. "
            "This diminishing return is exactly why staging was invented: discard the empty tank "
            "so subsequent burns start with a much lower initial mass.",
        "teacher_zh":
            "火箭方程式：Δv = Isp × g₀ × ln(m₀/m_f)。推進劑加倍並不能使 ΔV 加倍。"
            "以獵鷹 9 號第一節為例，推進劑從 400 噸增至 500 噸，ΔV 僅增加約 240 m/s，"
            "卻使起飛質量增加 100 噸，對酬載而言並不划算。"
            "正是這種遞減效益促成了多節設計的誕生：拋棄空推進劑槽，"
            "使後續燃燒從較低的初始質量開始，大幅提升整體效率。",
    },
    {
        "id": "stage2_isp_vac",
        "label":    "Stage 2 Vacuum Isp",
        "label_zh": "第二節真空比衝",
        "unit": "s",
        "dot_path": "stage2.engine.isp_vac",
        "default_min": 300.0, "default_max": 380.0, "default_steps": 9,
        "desc":    "Upper stage engine efficiency in vacuum — most impactful single parameter.",
        "desc_zh": "上節發動機在真空中的效率——對酬載影響最大的單一參數。",
        "note":    "Each +10 s Isp adds hundreds of kg payload. Isp is the rocket's fuel economy.",
        "note_zh": "比衝每提升 10 秒，可增加數百公斤酬載。比衝相當於火箭的「燃油效率」。",
        "teacher":
            "Isp (s) = F / (ṁ·g₀) = effective exhaust velocity / g₀. Key benchmarks:\n"
            "  RP-1/LOX (Merlin 1D vac): 311 s\n"
            "  Merlin 1D Vacuum (extended nozzle): 348 s  (+37 s = +~1,000 kg payload)\n"
            "  LH₂/LOX (Space Shuttle SSME): 453 s\n"
            "  CH₄/LOX (Raptor vac): ~380 s\n"
            "The upper stage operates entirely in vacuum, so vacuum Isp applies for the full burn. "
            "The improvement from 311→348 s (nozzle extension) is worth ~1,000+ kg to LEO.",
        "teacher_zh":
            "比衝（s）= F / (ṁ × g₀) = 有效排氣速度 / g₀。主要參考值：\n"
            "  RP-1/液氧（Merlin 1D 真空）：311 秒\n"
            "  Merlin 1D 真空延伸噴嘴：348 秒（+37 秒 ≈ 多 1,000 公斤酬載）\n"
            "  液氫/液氧（太空梭 SSME）：453 秒\n"
            "  甲烷/液氧（Raptor 真空）：約 380 秒\n"
            "上節整個燃燒過程均在真空中進行，故真空比衝全程有效。"
            "從 311 秒提升至 348 秒（延伸噴嘴）約可增加 1,000 公斤以上的 LEO 酬載。",
    },
    {
        "id": "stage1_isp_vac",
        "label":    "Stage 1 Vacuum Isp",
        "label_zh": "第一節真空比衝",
        "unit": "s",
        "dot_path": "stage1.engine.isp_vac",
        "default_min": 290.0, "default_max": 340.0, "default_steps": 6,
        "desc":    "Booster engine vacuum efficiency — applies at high altitude.",
        "desc_zh": "推進器在真空中的發動機效率，適用於高空飛行段。",
        "note":    "Booster Isp matters most at altitude where the nozzle approaches vacuum.",
        "note_zh": "第一節在高空接近真空環境，此時真空比衝最具影響力。",
        "teacher":
            "Stage 1 starts at sea-level Isp (~282 s for Merlin) and transitions to vacuum Isp (~311 s) "
            "as altitude increases. The effective average Isp over S1's burn lies between the two. "
            "Nozzle expansion ratio determines the gap: larger bells improve vacuum performance "
            "but risk flow separation at sea level (typically avoided by throttling or engine-out).",
        "teacher_zh":
            "第一節在發射時使用海平面比衝（Merlin 約 282 秒），隨高度上升逐漸過渡至真空比衝（約 311 秒）。"
            "整個第一節燃燒的有效平均比衝介於兩者之間。"
            "噴嘴膨脹比決定兩者差距：較大的噴嘴喉部比可提升真空性能，"
            "但可能在海平面引起氣流分離（通常藉由節流或關閉發動機避免）。",
    },
    {
        "id": "target_altitude_km",
        "label":    "Target Orbit Altitude",
        "label_zh": "目標軌道高度",
        "unit": "km",
        "dot_path": "mission.target_altitude_km",
        "default_min": 200.0, "default_max": 1200.0, "default_steps": 6,
        "desc":    "Desired circular orbit altitude above Earth's surface.",
        "desc_zh": "相對於地球表面的目標圓形軌道高度。",
        "note":    "Higher orbits need more ΔV: roughly +200 m/s per +200 km in LEO.",
        "note_zh": "軌道愈高所需 ΔV 愈多：低地球軌道範圍約每升高 200 km 需多 200 m/s。",
        "teacher":
            "Circular orbital velocity: v_c = √(GM/r), r = R_earth + altitude.\n"
            "  400 km → v_c ≈ 7,669 m/s     800 km → v_c ≈ 7,452 m/s\n"
            "Higher orbits have lower orbital speed but require more energy to climb. "
            "Total ΔV to orbit ≈ orbital velocity + gravity losses (~1,200 m/s) + drag (~100 m/s). "
            "Ask students to calculate orbital velocity at 400, 600, 800 km using the formula.",
        "teacher_zh":
            "圓形軌道速度：v_c = √(GM/r)，其中 r = 地球半徑 + 軌道高度。\n"
            "  400 km → v_c ≈ 7,669 m/s     800 km → v_c ≈ 7,452 m/s\n"
            "軌道愈高，軌道速度愈小，但爬升所需能量更多，總 ΔV 仍增加。"
            "到達軌道所需總 ΔV ≈ 軌道速度 + 重力損失（≈ 1,200 m/s）+ 阻力損失（≈ 100 m/s）。"
            "建議請學生代入公式，分別計算 400、600、800 km 的軌道速度。",
    },
    {
        "id": "fairing_mass",
        "label":    "Fairing Mass",
        "label_zh": "整流罩質量",
        "unit": "kg",
        "dot_path": "fairing_mass",
        "default_min": 500.0, "default_max": 3500.0, "default_steps": 7,
        "desc":    "Payload fairing (nose cone) mass — jettisoned during ascent.",
        "desc_zh": "酬載整流罩（鼻錐）質量，於上升途中拋棄。",
        "note":    "Dead weight for most of ascent. Lighter composite fairings improve payload.",
        "note_zh": "大部分飛行期間是無用的額外質量。輕量整流罩可提升酬載餘量。",
        "teacher":
            "The fairing protects the payload during max-Q (peak dynamic pressure, ~30–80 km altitude). "
            "It is jettisoned at ~110–120 km (~3 min after liftoff) once aeroheating is safe. "
            "Falcon 9's composite fairing weighs ~1,900 kg, costs ~$6M; SpaceX catches it by boat. "
            "Discussion: the fairing is carried as dead weight from liftoff to jettison — "
            "how does its mass cost compare to the same mass of propellant loaded in S2?",
        "teacher_zh":
            "整流罩在最大動壓（Max-Q，約 30–80 公里高度）期間保護酬載。"
            "通常在約 110–120 公里高度（起飛後約 3 分鐘）拋棄，此時氣動加熱已降至安全範圍。"
            "獵鷹 9 號複合材料整流罩重約 1,900 公斤，造價約 600 萬美元；SpaceX 以船隻接住回收。"
            "討論：整流罩從起飛攜帶至拋棄，其質量代價與同等質量的第二節推進劑相比如何？",
    },
    {
        "id": "reusable_penalty_kg",
        "label":    "Reusability Mass Penalty",
        "label_zh": "可回收質量損失",
        "unit": "kg",
        "dot_path": "mission.reusable_penalty_kg",
        "default_min": 0.0, "default_max": 15000.0, "default_steps": 6,
        "desc":    "Extra mass: landing legs, grid fins, reserved landing propellant.",
        "desc_zh": "著陸支架、格柵翼及保留著陸推進劑所增加的額外質量。",
        "note":    "Reuse hardware/propellant reduces payload. This defines the reuse business case.",
        "note_zh": "可回收硬體與保留推進劑會減少酬載，這是可回收設計商業模式的核心取捨。",
        "teacher":
            "SpaceX estimates Falcon 9 reusability penalty at ~7,000–9,000 kg total:\n"
            "  Landing legs: ~2,000 kg   Grid fins: ~700 kg\n"
            "  Reserved propellant (boost-back + entry + landing burns): ~5,000–7,000 kg\n"
            "Expendable F9 → ~22,800 kg LEO; RTLS reusable → ~15,600 kg (~31% reduction). "
            "The business case closes because reuse cuts marginal cost ~$60M → ~$28M per flight. "
            "Discussion: at what launch cadence does reuse break even vs. building new?",
        "teacher_zh":
            "SpaceX 估計獵鷹 9 號的可回收質量損失約為 7,000–9,000 公斤：\n"
            "  著陸支架：約 2,000 公斤   格柵翼：約 700 公斤\n"
            "  保留推進劑（返回/進入/著陸燃燒）：約 5,000–7,000 公斤\n"
            "非可回收版 → 約 22,800 公斤 LEO 酬載；"
            "可回收版（發射場著陸）→ 約 15,600 公斤（減少約 31%）。"
            "商業模式之所以成立，是因為可回收將邊際成本從約 6,000 萬美元降至約 2,800 萬美元。"
            "討論：在什麼發射頻率下，可回收設計的成本效益才能打平？",
    },
    {
        "id": "stage1_dry_mass",
        "label":    "Stage 1 Dry Mass",
        "label_zh": "第一節乾重",
        "unit": "kg",
        "dot_path": "stage1.dry_mass",
        "default_min": 14000.0, "default_max": 36000.0, "default_steps": 6,
        "desc":    "Booster structural mass: tanks, engines, interstage, landing legs.",
        "desc_zh": "推進器結構質量，包括推進劑槽、發動機、節間段與著陸支架。",
        "note":    "Structure fraction (dry/gross) targets 5–8% for competitive boosters.",
        "note_zh": "競爭力強的推進器結構分率（乾重／總重）目標為 5–8%。",
        "teacher":
            "Falcon 9 S1 dry mass ≈ 22,200 kg with gross mass ~433,200 kg → structure fraction ~5.1%. "
            "Achieved via friction-stir welded Al-Li tanks and Merlin engines only 470 kg each. "
            "Compare: early Atlas-D 'balloon tank' achieved ~2.5% but required pressurisation. "
            "Ask students: what happens to total ΔV if structure fraction rises from 5% to 10%? "
            "(Answer: significant reduction — use the Tsiolkovsky equation to calculate.)",
        "teacher_zh":
            "獵鷹 9 號第一節乾重約 22,200 公斤，總重約 433,200 公斤，結構分率約 5.1%。"
            "得益於摩擦攪拌焊接鋁鋰合金推進劑槽，以及每具僅重 470 公斤的 Merlin 發動機。"
            "相比之下，早期 Atlas-D「氣球槽」結構分率達約 2.5%，但必須持續加壓維持結構完整。"
            "課堂討論：若結構分率從 5% 上升至 10%，總 ΔV 如何變化？"
            "（答案：顯著下降——請學生代入齊奧爾科夫斯基方程式計算。）",
    },
]

PARAM_BY_ID = {p["id"]: p for p in PARAMETERS}

# ---------------------------------------------------------------------------
# Terminal formatting
# ---------------------------------------------------------------------------

W = 74  # line width

def banner(en: str, zh: str) -> None:
    print("\n" + "=" * W)
    print(f"  {en}")
    print(f"  {zh}")
    print("=" * W)

def section(en: str, zh: str) -> None:
    print(f"\n--- {en} / {zh} " + "-" * max(0, W - len(en) - len(zh) - 7))

def info(en: str, zh: str) -> None:
    print(f"  [EN] {en}")
    print(f"  [中] {zh}")

def teacher_note(param: dict) -> None:
    print(f"\n  {'─'*68}")
    print("  📖 教師備注 Teacher's Note:")
    print(f"  {'─'*68}")
    for line in param["teacher"].splitlines():
        print(f"    {line.strip()}")
    print()
    for line in param["teacher_zh"].splitlines():
        print(f"    {line.strip()}")
    print(f"  {'─'*68}")

def prompt(en_msg: str, zh_msg: str, default: Any = None) -> str:
    hint = f" [{default}]" if default is not None else ""
    try:
        val = input(f"\n  {en_msg} / {zh_msg}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n\n已中止 Aborted.")
        sys.exit(0)
    return val if val else (str(default) if default is not None else "")

def prompt_float(en: str, zh: str, default: float) -> float:
    while True:
        raw = prompt(en, zh, default)
        try:
            return float(raw)
        except ValueError:
            print("  [!] 請輸入數字 Please enter a number.")

def prompt_int(en: str, zh: str, default: int, lo=1, hi=200) -> int:
    while True:
        raw = prompt(en, zh, default)
        try:
            v = int(raw)
            if lo <= v <= hi:
                return v
            print(f"  [!] 請輸入 {lo}–{hi} 之間的整數 Enter integer between {lo} and {hi}.")
        except ValueError:
            print("  [!] 請輸入整數 Please enter a whole number.")

def choose(options: List[str], en_title: str, zh_title: str) -> int:
    print(f"\n  {en_title} / {zh_title}:")
    for i, opt in enumerate(options, 1):
        print(f"    {i:2d}. {opt}")
    while True:
        raw = prompt("Enter number", "輸入編號")
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
            print(f"  [!] 請輸入 1–{len(options)} Enter 1–{len(options)}.")
        except ValueError:
            print("  [!] 請輸入數字 Enter a number.")

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def deep_set(d: dict, dot_path: str, value: Any) -> dict:
    d = copy.deepcopy(d)
    keys = dot_path.split(".")
    node = d
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value
    return d

def deep_get(d: dict, dot_path: str) -> Any:
    node = d
    for k in dot_path.split("."):
        node = node[k]
    return node

def linspace(lo: float, hi: float, n: int) -> List[float]:
    if n < 2:
        return [lo]
    step = (hi - lo) / (n - 1)
    return [round(lo + i * step, 4) for i in range(n)]

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def check_health(url: str) -> bool:
    try:
        return requests.get(f"{url}/health", timeout=5).status_code == 200
    except Exception:
        return False

def api_sensitivity(url: str, base: dict, dot_path: str,
                    values: List[float]) -> Optional[dict]:
    try:
        r = requests.post(f"{url}/api/sensitivity",
                          json={"base": base, "parameter": dot_path, "values": values},
                          timeout=120)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        print("\n  [ERROR] 無法連線 API — 請先啟動 uvicorn Cannot reach API.")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"\n  [ERROR] API {e.response.status_code}: {e.response.text[:300]}")
        return None

def api_simulate(url: str, vehicle: dict) -> Optional[dict]:
    try:
        r = requests.post(f"{url}/api/simulate", json=vehicle, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        return None

def api_batch(url: str, runs: List[dict]) -> Optional[List[dict]]:
    try:
        r = requests.post(f"{url}/api/simulate/batch",
                          json={"runs": runs}, timeout=180)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        return None

# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_baseline(result: dict) -> None:
    mb = result.get("mass_budget", {})
    st = result.get("staging", {})
    pl = result.get("payload", {})
    section("Baseline Summary", "基準摘要")
    rows = [
        ("Liftoff Mass 起飛質量",          f"{mb.get('liftoff_mass_kg',0):>12,.0f} kg"),
        ("Payload Mass 酬載質量",           f"{mb.get('payload_mass_kg',0):>12,.0f} kg"),
        ("Payload Fraction 酬載分率",       f"{mb.get('payload_fraction',0)*100:>11.2f} %"),
        ("Liftoff TWR 起飛推重比",          f"{mb.get('liftoff_twr',0):>12.3f}"),
        ("Total Ideal ΔV 理想速度增量",     f"{st.get('total_ideal_delta_v_m_s',0):>12,.0f} m/s"),
        ("Usable ΔV 可用速度增量",          f"{st.get('usable_delta_v_m_s',0):>12,.0f} m/s"),
        ("Required ΔV 所需速度增量",        f"{st.get('required_delta_v_m_s',0):>12,.0f} m/s"),
        ("ΔV Margin 速度增量餘量",          f"{st.get('delta_v_margin_m_s',0):>+12,.0f} m/s"),
        ("Mission Feasible 任務可行",       f"{'YES 是' if pl.get('mission_feasible') else 'NO 否':>12}"),
    ]
    if pl.get("max_payload_kg"):
        rows.append(("Max Payload 最大酬載", f"{pl.get('max_payload_kg',0):>12,.0f} kg"))
    for label, val in rows:
        print(f"  {label:<38} {val}")

def print_sweep_table(param: dict, values: List[float], points: List[dict]) -> None:
    w1, w2, w3, w4, w5, w6 = 20, 14, 16, 15, 10, 20
    header_items = [
        f"{param['label']} ({param['unit']})", "Payload 酬載",
        "Max Payload 最大", "ΔV Margin 餘量", "Feasible 可行", "Limiting Factor 限制"
    ]
    widths = [w1, w2, w3, w4, w5, w6]
    section("Trade Study Results", "權衡研究結果")
    print(f"  參數 Parameter : {param['label']} {param['label_zh']} ({param['unit']})")
    print()
    print("  " + "".join(h.ljust(w) for h, w in zip(header_items, widths)))
    print("  " + "-" * sum(widths))
    for val, pt in zip(values, points):
        mp  = pt.get("max_payload_kg")
        row = [
            f"{val:,.1f}",
            f"{pt.get('payload_mass_kg',0):,.0f}",
            f"{mp:,.0f}" if mp else "N/A",
            f"{pt.get('delta_v_margin_m_s',0):+,.0f}",
            "YES 是" if pt.get("mission_feasible") else "NO 否",
            pt.get("limiting_factor", ""),
        ]
        print("  " + "".join(r.ljust(w) for r, w in zip(row, widths)))

def print_comparison_table(sweep_param: dict, compare_param: dict,
                            sweep_values: List[float], compare_values: List[float],
                            grid: List[List[Optional[dict]]], metric: str,
                            metric_label: str) -> None:
    col_w = 14
    section(f"Two-Parameter Comparison: {metric_label}",
            f"雙參數比較：{metric_label}")
    print(f"  X（掃描 Sweep）: {sweep_param['label']} {sweep_param['label_zh']}")
    print(f"  Y（固定 Fixed）: {compare_param['label']} {compare_param['label_zh']}")
    print()
    header = "  " + f"{'':15}" + "".join(
        f"{sweep_param['label_zh'][:5]}={v:,.0f}".ljust(col_w) for v in sweep_values
    )
    print(header)
    print("  " + "-" * (15 + col_w * len(sweep_values)))
    for j, cv in enumerate(compare_values):
        row_label = f"{compare_param['label_zh'][:6]}={cv:,.0f}"[:14].ljust(15)
        cells = []
        for i in range(len(sweep_values)):
            pt = grid[i][j]
            if pt is None:
                cells.append("  ERR".ljust(col_w))
            elif metric == "payload_mass_kg":
                cells.append(f"{pt.get('payload_mass_kg',0):>10,.0f}".ljust(col_w))
            elif metric == "delta_v_margin_m_s":
                cells.append(f"{pt.get('delta_v_margin_m_s',0):>+10,.0f}".ljust(col_w))
            elif metric == "feasible":
                cells.append(("  YES 是" if pt.get("mission_feasible") else "  NO 否").ljust(col_w))
        print(f"  {row_label}" + "".join(cells))

# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def export_single(param, values, points, baseline, out_dir: Path) -> Path:
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = out_dir / f"trade_{param['id']}_{ts}.csv"
    with fname.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["# 獵鷹9號式火箭模擬器 — 單參數權衡研究"])
        w.writerow(["# Falcon 9-like Rocket Simulator — Single-Parameter Trade Study"])
        w.writerow(["# 產生時間 Generated", datetime.now().isoformat()])
        w.writerow(["# 參數 Parameter", param["label"], param["label_zh"],
                    param["unit"], param["dot_path"]])
        w.writerow(["# 基準值 Baseline", deep_get(baseline, param["dot_path"])])
        w.writerow([])
        w.writerow([
            f"{param['label']} {param['label_zh']} ({param['unit']})",
            "Payload Mass 酬載質量 (kg)",
            "Max Payload 最大酬載 (kg)",
            "ΔV Margin 速度增量餘量 (m/s)",
            "Feasible 可行",
            "Limiting Factor 限制因素",
        ])
        for val, pt in zip(values, points):
            w.writerow([val,
                        pt.get("payload_mass_kg",""),
                        pt.get("max_payload_kg",""),
                        pt.get("delta_v_margin_m_s",""),
                        "YES 是" if pt.get("mission_feasible") else "NO 否",
                        pt.get("limiting_factor","")])
    return fname

def export_comparison(sweep_param, compare_param, sweep_values,
                      compare_values, grid, out_dir: Path) -> Path:
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = out_dir / f"trade_{sweep_param['id']}_vs_{compare_param['id']}_{ts}.csv"
    with fname.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["# 獵鷹9號式火箭模擬器 — 雙參數權衡研究"])
        w.writerow(["# Falcon 9-like Rocket Simulator — Two-Parameter Trade Study"])
        w.writerow(["# 產生時間 Generated", datetime.now().isoformat()])
        w.writerow(["# X 軸 X-axis", sweep_param["label"], sweep_param["label_zh"]])
        w.writerow(["# Y 軸 Y-axis", compare_param["label"], compare_param["label_zh"]])
        w.writerow([])
        w.writerow([
            f"{sweep_param['label']} {sweep_param['label_zh']} ({sweep_param['unit']})",
            f"{compare_param['label']} {compare_param['label_zh']} ({compare_param['unit']})",
            "Payload Mass 酬載質量 (kg)",
            "Max Payload 最大酬載 (kg)",
            "ΔV Margin 速度增量餘量 (m/s)",
            "Feasible 可行",
            "Limiting Factor 限制因素",
        ])
        for i, sv in enumerate(sweep_values):
            for j, cv in enumerate(compare_values):
                pt = grid[i][j]
                if pt is None:
                    w.writerow([sv, cv, "ERROR","","","",""])
                else:
                    w.writerow([sv, cv,
                                pt.get("payload_mass_kg",""),
                                pt.get("max_payload_kg",""),
                                pt.get("delta_v_margin_m_s",""),
                                "YES 是" if pt.get("mission_feasible") else "NO 否",
                                pt.get("limiting_factor","")])
    return fname

# ---------------------------------------------------------------------------
# Mode 1: Single-parameter sweep
# ---------------------------------------------------------------------------

def mode_single(url: str, baseline: dict) -> None:
    section("Mode 1 — Single-Parameter Sweep", "模式一 — 單參數掃描")
    info(
        "Choose ONE design variable to sweep. The simulator computes payload at each point.",
        "選擇一個設計變數進行掃描，模擬器將計算每個點的酬載性能。"
    )

    labels = [
        f"{p['label']} {p['label_zh']} ({p['unit']})  —  {p['desc_zh']}"
        for p in PARAMETERS
    ]
    idx   = choose(labels, "Select parameter to sweep", "選擇掃描參數")
    param = PARAMETERS[idx]

    baseline_val = deep_get(baseline, param["dot_path"])
    print(f"\n  基準值 Baseline: {param['label']} {param['label_zh']} = {baseline_val:,} {param['unit']}")
    info(param["note"], param["note_zh"])

    # Show teacher note (optional)
    show_tn = prompt("Show teacher's note? 顯示教師備注？", "", "n")
    if show_tn.lower() == "y":
        teacher_note(param)

    section("Define Sweep Range", "設定掃描範圍")
    lo    = prompt_float(f"Minimum 最小值 ({param['unit']})", "", param["default_min"])
    hi    = prompt_float(f"Maximum 最大值 ({param['unit']})", "", param["default_max"])
    steps = prompt_int("Number of steps 步數", "", int(param["default_steps"]), lo=2, hi=50)

    if hi <= lo:
        print("  [!] 最大值必須大於最小值 Maximum must be greater than minimum.")
        return

    values = linspace(lo, hi, steps)
    step_size = (hi - lo) / (steps - 1)
    print(f"\n  掃描 Sweep: {lo:,} → {hi:,}，共 {steps} 步，步長 step = {step_size:,.2f} {param['unit']}")

    if prompt("Run trade study? 執行權衡研究？", "", "y").lower() != "y":
        return

    print(f"\n  執行 {steps} 次模擬 Running {steps} simulations...", end="", flush=True)
    resp = api_sensitivity(url, baseline, param["dot_path"], values)
    if resp is None:
        return
    points = resp.get("points", [])
    print(" 完成 done.")

    print_sweep_table(param, values, points)

    # Interpretation
    feasible   = [pt for pt in points if pt.get("mission_feasible")]
    infeasible = [pt for pt in points if not pt.get("mission_feasible")]
    section("Interpretation", "結果解讀")
    print(f"  可行配置 Feasible configs : {len(feasible)} / {len(points)}")
    if feasible:
        best      = max(feasible, key=lambda p: p.get("payload_mass_kg", 0))
        best_val  = values[points.index(best)]
        print(f"  最佳酬載 Best payload     : {best.get('payload_mass_kg',0):,.0f} kg  "
              f"at {param['label_zh']} = {best_val:,.1f} {param['unit']}")
    if infeasible:
        fi_val = values[points.index(infeasible[0])]
        print(f"  任務失敗點 Mission fails  : {param['label_zh']} = {fi_val:,.1f} {param['unit']}")

    # Export
    section("Export CSV", "匯出 CSV")
    out_dir = Path("results")
    out_dir.mkdir(exist_ok=True)
    fname = export_single(param, values, points, baseline, out_dir)
    print(f"  已儲存 Saved: {fname.resolve()}")
    print(f"  （CSV 標題使用 UTF-8-BOM 格式，可直接以 Excel 開啟）")
    print(f"  (UTF-8-BOM encoding for direct Excel compatibility)")

# ---------------------------------------------------------------------------
# Mode 2: Two-parameter comparison
# ---------------------------------------------------------------------------

def mode_comparison(url: str, baseline: dict) -> None:
    section("Mode 2 — Two-Parameter Comparison", "模式二 — 雙參數比較")
    info(
        "Sweep a PRIMARY parameter while comparing at discrete values of a SECONDARY parameter.",
        "掃描主要參數，同時在次要參數的數個固定值下比較，揭示兩個設計變數的交互關係。"
    )

    labels = [
        f"{p['label']} {p['label_zh']} ({p['unit']})" for p in PARAMETERS
    ]

    idx1        = choose(labels, "Select PRIMARY parameter (X-axis sweep)", "選擇主要參數（X 軸掃描）")
    sweep_param = PARAMETERS[idx1]

    show_tn = prompt("Show teacher's note for primary parameter? 顯示主要參數的教師備注？", "", "n")
    if show_tn.lower() == "y":
        teacher_note(sweep_param)

    remaining        = [l for i, l in enumerate(labels) if i != idx1]
    remaining_params = [p for i, p in enumerate(PARAMETERS) if i != idx1]
    idx2             = choose(remaining, "Select SECONDARY parameter (Y-axis discrete)", "選擇次要參數（Y 軸離散值）")
    compare_param    = remaining_params[idx2]

    show_tn2 = prompt("Show teacher's note for secondary parameter? 顯示次要參數的教師備注？", "", "n")
    if show_tn2.lower() == "y":
        teacher_note(compare_param)

    # Primary sweep range
    section(f"Primary Sweep: {sweep_param['label']}", f"主要掃描：{sweep_param['label_zh']}")
    info(sweep_param["note"], sweep_param["note_zh"])
    lo    = prompt_float(f"Min 最小值 ({sweep_param['unit']})", "", sweep_param["default_min"])
    hi    = prompt_float(f"Max 最大值 ({sweep_param['unit']})", "", sweep_param["default_max"])
    steps = prompt_int("Steps 步數", "", min(int(sweep_param["default_steps"]), 6), lo=2, hi=10)
    sweep_values = linspace(lo, hi, steps)
    print(f"  掃描 Sweep: {lo:,} → {hi:,}，{steps} 步")

    # Secondary discrete values
    section(f"Secondary Values: {compare_param['label']}", f"次要參數：{compare_param['label_zh']}")
    info(compare_param["note"], compare_param["note_zh"])
    n_compare = prompt_int("How many discrete values? 幾個離散值？", "", 3, lo=2, hi=6)
    compare_values = []
    for i in range(n_compare):
        default_v = compare_param["default_min"] + (
            (compare_param["default_max"] - compare_param["default_min"])
            * i / max(n_compare - 1, 1)
        )
        v = prompt_float(f"Value {i+1} 數值 {i+1} ({compare_param['unit']})", "", round(default_v, 1))
        compare_values.append(v)

    total_runs = steps * n_compare
    if total_runs > 50:
        print(f"\n  [!] {total_runs} 次超過批次上限 50 Exceeds batch limit of 50.")
        print("      請減少步數或離散值 Reduce steps or discrete values.")
        return

    # Metric
    metric_opts = [
        ("payload_mass_kg",    "Payload Mass 酬載質量 (kg)"),
        ("delta_v_margin_m_s", "ΔV Margin 速度增量餘量 (m/s)"),
        ("feasible",           "Mission Feasible 任務可行性"),
    ]
    mi = choose([m for _, m in metric_opts], "Select display metric", "選擇顯示指標")
    metric, metric_label = metric_opts[mi]

    if prompt(f"\n執行 Run {total_runs} simulations? 次模擬？", "", "y").lower() != "y":
        return

    print(f"\n  執行 {total_runs} 次模擬 Running {total_runs} simulations...", end="", flush=True)
    runs: List[dict] = []
    for sv in sweep_values:
        for cv in compare_values:
            veh = deep_set(baseline, sweep_param["dot_path"], sv)
            veh = deep_set(veh, compare_param["dot_path"], cv)
            veh["sim_config"]["run_trajectory"] = False
            runs.append(veh)

    batch = api_batch(url, runs)
    if batch is None:
        return
    print(" 完成 done.")

    grid: List[List[Optional[dict]]] = []
    idx = 0
    for i in range(len(sweep_values)):
        col = []
        for j in range(len(compare_values)):
            res = batch[idx] if idx < len(batch) else None
            col.append(res["payload"] if res and res.get("ok") and res.get("payload") else None)
            idx += 1
        grid.append(col)

    print_comparison_table(sweep_param, compare_param,
                           sweep_values, compare_values,
                           grid, metric, metric_label)

    section("Export CSV", "匯出 CSV")
    out_dir = Path("results")
    out_dir.mkdir(exist_ok=True)
    fname = export_comparison(sweep_param, compare_param,
                              sweep_values, compare_values, grid, out_dir)
    print(f"  已儲存 Saved: {fname.resolve()}")

# ---------------------------------------------------------------------------
# Baseline override
# ---------------------------------------------------------------------------

def configure_baseline(baseline: dict) -> dict:
    section("Adjust Baseline Vehicle", "調整基準載具")
    info(
        "Press Enter to keep the default value for each parameter.",
        "直接按 Enter 保留各參數的預設值。"
    )
    overrides = [
        ("payload_mass",               "Payload mass 酬載質量 (kg)"),
        ("mission.target_altitude_km", "Target altitude 目標軌道高度 (km)"),
        ("stage1.prop_mass",           "S1 propellant 第一節推進劑 (kg)"),
        ("stage2.prop_mass",           "S2 propellant 第二節推進劑 (kg)"),
        ("stage2.dry_mass",            "S2 dry mass 第二節乾重 (kg)"),
        ("stage2.engine.isp_vac",      "S2 vacuum Isp 第二節真空比衝 (s)"),
    ]
    for dot_path, label in overrides:
        current = deep_get(baseline, dot_path)
        raw = prompt(label, "", current)
        try:
            new_val = float(raw)
            if new_val != current:
                baseline = deep_set(baseline, dot_path, new_val)
                print(f"    → {dot_path} = {new_val}")
        except ValueError:
            pass
    return baseline

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Falcon 9-like Rocket Trade Study Tool / 火箭設計權衡研究工具")
    parser.add_argument("--url", default=API_BASE, help="API base URL")
    args    = parser.parse_args()
    base_url = args.url.rstrip("/")

    banner(
        "Falcon 9-like Rocket Educational Simulator — Trade Study Tool",
        "獵鷹 9 號式火箭教育模擬器 — 設計權衡研究工具"
    )
    info(
        "This tool guides you through rocket design trade studies.",
        "本工具引導您完成火箭設計的參數權衡研究。"
    )
    info(
        "Sweep design variables and discover their effect on payload and mission feasibility.",
        "透過掃描設計變數，探索各參數對酬載能力與任務可行性的影響。"
    )

    # Health check
    print(f"\n  連線中 Connecting to {base_url} ...", end="", flush=True)
    if not check_health(base_url):
        print(" 失敗 FAILED")
        print(f"\n  [ERROR] 無法連線 Cannot reach {base_url}/health")
        print("  請先啟動 API / Start the API:\n")
        print("    uvicorn apps.api.app.main:app --reload\n")
        sys.exit(1)
    print(" OK ✓")

    # Baseline
    baseline = copy.deepcopy(BASELINE)
    print("\n  執行基準模擬 Running baseline simulation...", end="", flush=True)
    base_result = api_simulate(base_url, baseline)
    if base_result and base_result.get("ok"):
        print(" OK ✓")
        print_baseline(base_result)
    else:
        errs = base_result.get("errors", []) if base_result else ["No response"]
        print(f" 失敗 FAILED: {errs}")

    # Optional baseline override
    if prompt("Adjust baseline values? 調整基準數值？", "", "n").lower() == "y":
        baseline = configure_baseline(baseline)
        print("\n  重新執行基準模擬 Re-running baseline...", end="", flush=True)
        base_result = api_simulate(base_url, baseline)
        if base_result and base_result.get("ok"):
            print(" OK ✓")
            print_baseline(base_result)

    # Mode selection
    mode = choose(
        [
            "Single-parameter sweep 單參數掃描  —  一個變數對酬載的影響",
            "Two-parameter comparison 雙參數比較  —  兩個變數的交互關係",
        ],
        "Select trade study mode",
        "選擇研究模式",
    )

    if mode == 0:
        mode_single(base_url, baseline)
    else:
        mode_comparison(base_url, baseline)

    print("\n" + "=" * W)
    print("  研究完成 Trade study complete.")
    print("  結果已儲存於 results/ 資料夾 Results saved in the 'results/' folder.")
    print("=" * W + "\n")


if __name__ == "__main__":
    main()
