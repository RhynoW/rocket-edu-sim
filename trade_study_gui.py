"""
trade_study_gui.py
==================
Bilingual (English / Traditional Chinese) Streamlit GUI for the
Falcon 9-like Rocket Educational Simulator Trade Studies.

Run:
    streamlit run trade_study_gui.py
"""

from __future__ import annotations

import copy
import csv
import io
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import plotly.graph_objects as go
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Rocket Trade Study 火箭設計權衡研究",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_API = "http://127.0.0.1:8000"

BASELINE_DEFAULT: Dict[str, Any] = {
    "stage1": {
        "dry_mass": 22200,
        "prop_mass": 411000,
        "engine_count": 9,
        "diameter_m": 3.7,
        "engine": {
            "name": "Merlin 1D",
            "thrust_sl": 845000,
            "thrust_vac": 934000,
            "isp_sl": 282,
            "isp_vac": 311,
            "mass": 470,
        },
    },
    "stage2": {
        "dry_mass": 4000,
        "prop_mass": 107500,
        "engine_count": 1,
        "diameter_m": 3.7,
        "engine": {
            "name": "Merlin 1D Vacuum",
            "thrust_sl": 0.001,
            "thrust_vac": 981000,
            "isp_sl": 100,
            "isp_vac": 348,
            "mass": 490,
        },
    },
    "payload_mass": 22800,
    "fairing_mass": 1900,
    "propellant": {"oxidiser": "LOX", "fuel": "RP1", "mixture_ratio": 2.56},
    "mission": {
        "target_altitude_km": 400,
        "reusable_booster": False,
        "reusable_penalty_kg": 0,
        "required_delta_v_m_s": None,
    },
    "sim_config": {
        "gravity_loss_estimate_m_s": 1200,
        "max_q_throttle_fraction": 0.72,
        "run_trajectory": False,
    },
}

# ---------------------------------------------------------------------------
# Bilingual parameter catalogue
# Each entry carries English + Traditional Chinese text plus a teacher note.
# ---------------------------------------------------------------------------

PARAMETERS: List[Dict[str, Any]] = [
    {
        "id": "payload_mass",
        "label":    "Payload Mass",
        "label_zh": "酬載質量",
        "unit": "kg",
        "description":    "Mass of the spacecraft or satellite delivered to orbit.",
        "description_zh": "送入軌道的太空船或衛星質量。",
        "dot_path": "payload_mass",
        "default_min": 5000.0, "default_max": 30000.0, "default_steps": 8,
        "note":    "Heavier payloads consume the delta-v budget. Watch the margin shrink as payload grows.",
        "note_zh": "較重的酬載會消耗速度增量（ΔV）預算。隨著酬載增加，任務可行性餘量將逐漸縮小。",
        "teacher_note": (
            "In the Tsiolkovsky equation, payload is embedded in the final mass m_f. "
            "Since m_f appears inside the logarithm, the relationship is nonlinear — "
            "adding 1 t of payload costs proportionally more ΔV as the vehicle grows heavier. "
            "A useful classroom exercise: ask students to find the payload that reduces ΔV margin to exactly zero (maximum payload)."
        ),
        "teacher_note_zh": (
            "在齊奧爾科夫斯基方程式中，酬載質量包含於終態質量 m_f 之內。"
            "由於 m_f 在對數函數內，兩者關係為非線性——當整體質量愈大時，每增加 1 噸酬載所消耗的 ΔV 也愈多。"
            "課堂練習建議：請學生找出使 ΔV 餘量恰好歸零的最大酬載質量。"
        ),
    },
    {
        "id": "stage2_dry_mass",
        "label":    "Stage 2 Dry Mass",
        "label_zh": "第二節乾重",
        "unit": "kg",
        "description":    "Upper stage structural mass: tanks, wiring, avionics, engine mount.",
        "description_zh": "上節結構質量，包括推進劑槽、電路系統、航電設備與發動機架。",
        "dot_path": "stage2.dry_mass",
        "default_min": 2000.0, "default_max": 8000.0, "default_steps": 7,
        "note":    "Stage 2 dry mass reduces payload roughly 1-for-1 at constant propellant.",
        "note_zh": "在推進劑不變的情況下，第二節乾重每增加 1 kg，酬載大約減少 1 kg。",
        "teacher_note": (
            "The upper stage structure fraction (dry_mass / gross_mass) targets 3–6% for high-performance vehicles. "
            "The Falcon 9 upper stage achieves ~3.6%, enabled by aluminium-lithium alloy tanks and composite structures. "
            "Ask students: if we could halve S2 dry mass, how much more payload could we carry? "
            "This reveals the 'structural sensitivity' — compare the answer with the payload sensitivity from the sweep."
        ),
        "teacher_note_zh": (
            "高性能上節的結構分率（乾重／總重）目標為 3–6%。"
            "獵鷹 9 號上節達到約 3.6%，得益於鋁鋰合金推進劑槽與複合材料結構。"
            "課堂討論：若第二節乾重減半，可以多攜帶多少酬載？"
            "這有助於學生理解「結構靈敏度」——可與酬載掃描的結果對比。"
        ),
    },
    {
        "id": "stage2_prop_mass",
        "label":    "Stage 2 Propellant Mass",
        "label_zh": "第二節推進劑質量",
        "unit": "kg",
        "description":    "Propellant loaded in the upper stage for orbit insertion.",
        "description_zh": "上節用於軌道插入的推進劑質量。",
        "dot_path": "stage2.prop_mass",
        "default_min": 60000.0, "default_max": 150000.0, "default_steps": 7,
        "note":    "More S2 propellant gives more orbit-insertion ΔV but also increases Stage 1's required lift.",
        "note_zh": "第二節推進劑愈多，軌道插入 ΔV 愈充裕，但同時也增加了第一節需要承載的質量。",
        "teacher_note": (
            "This is the classic staging trade-off. Adding propellant to S2 increases the liftoff mass, "
            "which in turn reduces S1's mass ratio and therefore S1's ΔV contribution. "
            "There is an optimal split — the Lagrange condition for two-stage rockets states that "
            "the optimal mass ratio is identical for both stages when structure fractions are equal. "
            "In practice, differing Isp and structure fractions shift the optimum toward a heavier Stage 1."
        ),
        "teacher_note_zh": (
            "這是經典的分節取捨問題。增加第二節推進劑會使起飛質量增大，"
            "進而降低第一節的質量比，減少第一節對 ΔV 的貢獻。"
            "存在一個最佳分配比例——對於兩節式火箭，拉格朗日最佳化條件指出："
            "當結構分率相等時，兩節的最佳質量比相同。"
            "實際上，不同的比衝與結構分率使最佳解偏向較重的第一節。"
        ),
    },
    {
        "id": "stage1_prop_mass",
        "label":    "Stage 1 Propellant Mass",
        "label_zh": "第一節推進劑質量",
        "unit": "kg",
        "description":    "Booster propellant load — the dominant ΔV contributor.",
        "description_zh": "推進器的推進劑質量，是總速度增量的最主要來源。",
        "dot_path": "stage1.prop_mass",
        "default_min": 280000.0, "default_max": 520000.0, "default_steps": 6,
        "note":    "Stage 1 carries ~80% of total propellant. Gains follow a logarithmic curve — diminishing returns apply.",
        "note_zh": "第一節承載約 80% 的總推進劑。由於對數關係，推進劑增益呈遞減趨勢。",
        "teacher_note": (
            "The rocket equation is Δv = Isp·g₀·ln(m₀/m_f). Doubling propellant does NOT double ΔV. "
            "For Falcon 9 S1, going from 400 t to 500 t propellant adds only ~240 m/s ΔV "
            "while increasing liftoff mass by 100 t — a poor trade for payload. "
            "This is why the industry moved to staging: split the vehicle and discard the empty S1 tank."
        ),
        "teacher_note_zh": (
            "火箭方程式為 Δv = Isp × g₀ × ln(m₀/m_f)。推進劑加倍並不能使 ΔV 加倍。"
            "以獵鷹 9 號第一節為例，推進劑從 400 噸增至 500 噸，ΔV 僅增加約 240 m/s，"
            "卻使起飛質量增加 100 噸——對酬載而言並不划算。"
            "這正是業界採用多節設計的原因：分節後可拋棄空推進劑槽，大幅提升效率。"
        ),
    },
    {
        "id": "stage2_isp_vac",
        "label":    "Stage 2 Vacuum Isp",
        "label_zh": "第二節真空比衝",
        "unit": "s",
        "description":    "Upper stage engine efficiency in vacuum — the single most impactful parameter.",
        "description_zh": "上節發動機在真空中的效率，是對酬載影響最大的單一參數。",
        "dot_path": "stage2.engine.isp_vac",
        "default_min": 300.0, "default_max": 380.0, "default_steps": 9,
        "note":    "Each +10 s Isp improvement adds hundreds of kg to payload. Isp is the rocket's fuel economy.",
        "note_zh": "比衝每提升 10 秒，可增加數百公斤的酬載能力。比衝相當於火箭的「燃油效率」。",
        "teacher_note": (
            "Isp (specific impulse, unit: seconds) is defined as thrust per unit weight flow: Isp = F / (ṁ·g₀). "
            "It is fuel-type and engine-design dependent. Key benchmarks:\n"
            "  • RP-1/LOX (Merlin): ~311 s vac\n"
            "  • LH2/LOX (Space Shuttle SSME): ~453 s vac\n"
            "  • CH4/LOX (Raptor): ~380 s vac\n"
            "  • Ion thruster (Hall effect): ~1500–3000 s (but tiny thrust)\n"
            "The upper stage operates entirely in vacuum so vacuum Isp applies for its full burn. "
            "Improving Isp from 311 s to 348 s (Merlin Vacuum nozzle extension) is worth ~1000+ kg payload."
        ),
        "teacher_note_zh": (
            "比衝（Isp，單位：秒）定義為每單位推進劑重量流率所產生的推力：Isp = F / (ṁ × g₀)。"
            "其值取決於推進劑種類與發動機設計。主要參考值：\n"
            "  • RP-1/液氧（Merlin）：真空約 311 秒\n"
            "  • 液氫/液氧（太空梭 SSME）：真空約 453 秒\n"
            "  • 甲烷/液氧（Raptor）：真空約 380 秒\n"
            "  • 離子推進器（霍爾效應）：約 1500–3000 秒（推力極小）\n"
            "上節整個燃燒過程均在真空中進行，故真空比衝全程有效。"
            "將比衝從 311 秒提升至 348 秒（Merlin 真空延伸噴嘴），可增加超過 1000 公斤的酬載。"
        ),
    },
    {
        "id": "stage1_isp_vac",
        "label":    "Stage 1 Vacuum Isp",
        "label_zh": "第一節真空比衝",
        "unit": "s",
        "description":    "Booster engine vacuum efficiency — applies during high-altitude flight.",
        "description_zh": "推進器發動機的真空效率，適用於高空飛行段。",
        "dot_path": "stage1.engine.isp_vac",
        "default_min": 290.0, "default_max": 340.0, "default_steps": 6,
        "note":    "Booster Isp matters most at altitude where the nozzle operates near vacuum.",
        "note_zh": "第一節在高空時接近真空環境，此時真空比衝最具影響力。",
        "teacher_note": (
            "Stage 1 uses sea-level Isp at launch (~282 s for Merlin) but transitions to vacuum Isp (~311 s) "
            "as altitude increases. The effective average Isp over S1's burn lies between the two. "
            "The nozzle expansion ratio determines the gap between sea-level and vacuum Isp — "
            "larger nozzle bells improve vacuum performance but may cause flow separation at sea level."
        ),
        "teacher_note_zh": (
            "第一節在發射時使用海平面比衝（Merlin 約 282 秒），隨高度上升逐漸過渡至真空比衝（約 311 秒）。"
            "第一節燃燒過程的有效平均比衝介於兩者之間。"
            "噴嘴膨脹比決定了海平面與真空比衝之間的差距——"
            "較大的噴嘴喉部面積比可提升真空性能，但可能在海平面引起氣流分離。"
        ),
    },
    {
        "id": "target_altitude_km",
        "label":    "Target Orbit Altitude",
        "label_zh": "目標軌道高度",
        "unit": "km",
        "description":    "Desired circular orbit altitude above Earth's surface.",
        "description_zh": "相對於地球表面的目標圓形軌道高度。",
        "dot_path": "mission.target_altitude_km",
        "default_min": 200.0, "default_max": 1200.0, "default_steps": 6,
        "note":    "Higher orbits need more ΔV. Roughly +200 m/s per +200 km in LEO.",
        "note_zh": "軌道愈高所需 ΔV 愈多。在低地球軌道範圍，約每升高 200 公里需多 200 m/s。",
        "teacher_note": (
            "Circular orbital velocity: v_c = √(GM/r), where r = R_earth + altitude.\n"
            "At 400 km: v_c ≈ 7,669 m/s\n"
            "At 800 km: v_c ≈ 7,452 m/s (less velocity, but more ΔV needed because you must also climb higher)\n"
            "Total ΔV to orbit ≈ orbital velocity + gravity losses (~1200 m/s) + drag losses (~100 m/s).\n"
            "Key insight: higher orbits reduce orbital speed but the energy cost of climbing dominates. "
            "Ask students to calculate the orbital velocity at several altitudes using the formula."
        ),
        "teacher_note_zh": (
            "圓形軌道速度公式：v_c = √(GM/r)，其中 r = 地球半徑 + 軌道高度。\n"
            "400 km 時：v_c ≈ 7,669 m/s\n"
            "800 km 時：v_c ≈ 7,452 m/s（軌道速度較小，但需克服更高重力位能）\n"
            "到達軌道所需總 ΔV ≈ 軌道速度 + 重力損失（≈ 1200 m/s） + 阻力損失（≈ 100 m/s）。\n"
            "關鍵概念：軌道愈高，軌道速度愈小，但爬升所需能量更多，總 ΔV 仍增加。"
            "建議請學生代入公式，自行計算不同高度的軌道速度。"
        ),
    },
    {
        "id": "fairing_mass",
        "label":    "Fairing Mass",
        "label_zh": "整流罩質量",
        "unit": "kg",
        "description":    "Payload fairing (nose cone) mass — jettisoned during ascent.",
        "description_zh": "整流罩（鼻錐）質量，於上升途中拋棄。",
        "dot_path": "fairing_mass",
        "default_min": 500.0, "default_max": 3500.0, "default_steps": 7,
        "note":    "The fairing is dead weight for most of the ascent. Lighter fairings improve payload margin.",
        "note_zh": "整流罩在大部分飛行期間是無用的額外質量。輕量整流罩可提升酬載餘量。",
        "teacher_note": (
            "The fairing protects the payload during max-Q (maximum dynamic pressure, typically 30–80 km). "
            "It is typically jettisoned around 110–120 km altitude (~3 min after liftoff) "
            "once aerodynamic heating and pressure drop to safe levels. "
            "Falcon 9's composite fairing weighs ~1,900 kg and costs ~$6M. SpaceX recovers it via parachute + boat catch. "
            "Ask students: how much payload mass does the fairing cost over the entire ascent vs. just post-jettison?"
        ),
        "teacher_note_zh": (
            "整流罩在最大動壓（Max-Q，通常發生於 30–80 公里高度）期間保護酬載。"
            "通常在約 110–120 公里高度（起飛後約 3 分鐘）拋棄，"
            "此時氣動加熱與大氣壓力已降至安全範圍。"
            "獵鷹 9 號複合材料整流罩重約 1,900 公斤，造價約 600 萬美元。SpaceX 以降落傘加船隻接住的方式回收。"
            "課堂討論：整流罩在整個飛行過程（對比僅在拋棄後）對酬載質量的消耗有何不同？"
        ),
    },
    {
        "id": "reusable_penalty_kg",
        "label":    "Reusability Mass Penalty",
        "label_zh": "可回收質量損失",
        "unit": "kg",
        "description":    "Extra mass for landing legs, grid fins, and reserved landing propellant.",
        "description_zh": "著陸支架、格柵翼及保留著陸推進劑所增加的額外質量。",
        "dot_path": "mission.reusable_penalty_kg",
        "default_min": 0.0, "default_max": 15000.0, "default_steps": 6,
        "note":    "Reuse hardware and reserved propellant reduce payload. This trade-off defines the reuse business case.",
        "note_zh": "可回收硬體與保留推進劑會減少酬載。此取捨關係是可回收設計商業模式的核心。",
        "teacher_note": (
            "SpaceX estimates the Falcon 9 reusability penalty at ~7,000–9,000 kg (landing legs ~2 t, "
            "grid fins ~700 kg, reserved propellant ~5–7 t for boost-back + entry + landing burns). "
            "Expendable F9 delivers ~22,800 kg to LEO; reusable (RTLS) delivers ~15,600 kg (~-31%). "
            "The business case closes because reuse reduces marginal cost from ~$60M to ~$28M per flight. "
            "Discussion: at what launch cadence does reuse break even versus building a new vehicle?"
        ),
        "teacher_note_zh": (
            "SpaceX 估計獵鷹 9 號的可回收質量損失約為 7,000–9,000 公斤，"
            "其中著陸支架約 2 噸、格柵翼約 700 公斤、返回/進入/著陸燃燒保留推進劑約 5–7 噸。"
            "非可回收版獵鷹 9 可送 22,800 公斤到 LEO；可回收版（發射場著陸）僅約 15,600 公斤（減少約 31%）。"
            "商業模式之所以成立，是因為可回收將每次任務邊際成本從約 6,000 萬美元降至約 2,800 萬美元。"
            "課堂討論：在什麼發射頻率下，可回收設計的成本效益才能打平？"
        ),
    },
    {
        "id": "stage1_dry_mass",
        "label":    "Stage 1 Dry Mass",
        "label_zh": "第一節乾重",
        "unit": "kg",
        "description":    "Booster structural mass: tanks, engines, interstage, landing legs.",
        "description_zh": "推進器結構質量，包括推進劑槽、發動機、節間段與著陸支架。",
        "dot_path": "stage1.dry_mass",
        "default_min": 14000.0, "default_max": 36000.0, "default_steps": 6,
        "note":    "Structure fraction (dry/gross) targets 5–8% for competitive boosters.",
        "note_zh": "競爭力強的推進器結構分率（乾重／總重）目標為 5–8%。",
        "teacher_note": (
            "Falcon 9 S1 dry mass ≈ 22,200 kg with a gross mass of ~433,200 kg, giving a structure fraction of ~5.1%. "
            "This is an extraordinary achievement driven by friction-stir welded aluminium-lithium tanks "
            "and Merlin engines only weighing 470 kg each. "
            "Compare with early rockets: Atlas-D had a paper-thin 'balloon tank' achieving ~2.5%, "
            "but required pressurisation to maintain structural integrity. "
            "Ask students: what happens to ΔV if structure fraction rises from 5% to 10%?"
        ),
        "teacher_note_zh": (
            "獵鷹 9 號第一節乾重約 22,200 公斤，總重約 433,200 公斤，結構分率約 5.1%。"
            "這一優異表現得益於摩擦攪拌焊接鋁鋰合金推進劑槽，以及每具僅重 470 公斤的 Merlin 發動機。"
            "相比之下，早期的 Atlas-D 火箭採用超薄「氣球槽」，結構分率達約 2.5%，"
            "但必須維持加壓才能保持結構完整性。"
            "課堂討論：若結構分率從 5% 上升至 10%，ΔV 會如何變化？"
        ),
    },
]

PARAM_BY_ID = {p["id"]: p for p in PARAMETERS}


def param_label_bilingual(pid: str) -> str:
    p = PARAM_BY_ID[pid]
    return f"{p['label']} {p['label_zh']} ({p['unit']})"


# ---------------------------------------------------------------------------
# Utility
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
# API helpers
# ---------------------------------------------------------------------------

def api_health(base_url: str) -> bool:
    try:
        r = requests.get(f"{base_url}/health", timeout=4)
        return r.status_code == 200
    except Exception:
        return False


def api_simulate(base_url: str, vehicle: dict) -> Optional[dict]:
    try:
        r = requests.post(f"{base_url}/api/simulate", json=vehicle, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error / API 錯誤: {e}")
        return None


def api_sensitivity(base_url: str, base: dict, dot_path: str, values: List[float]) -> Optional[dict]:
    payload = {"base": base, "parameter": dot_path, "values": values}
    try:
        r = requests.post(f"{base_url}/api/sensitivity", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error / API 錯誤: {e}")
        return None


def api_batch(base_url: str, runs: List[dict]) -> Optional[List[dict]]:
    try:
        r = requests.post(f"{base_url}/api/simulate/batch", json={"runs": runs}, timeout=180)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        st.error(f"API error / API 錯誤: {e}")
        return None


# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

COLORS = {
    "s1_prop": "#4C78A8", "s1_dry": "#1a3a5c",
    "s2_prop": "#F58518", "s2_dry": "#7a3a00",
    "payload": "#54A24B", "fairing": "#B279A2",
    "green": "#2ECC71",   "red": "#E74C3C",
    "amber": "#F39C12",   "blue": "#3498DB",
}

# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def chart_mass_budget(result: dict) -> go.Figure:
    mb = result.get("mass_budget", {})
    total_prop = mb.get("total_prop_mass_kg", 0)
    total_dry  = mb.get("total_dry_mass_kg", 0)
    payload    = mb.get("payload_mass_kg", 0)
    fairing    = mb.get("fairing_mass_kg", 0)

    segments = [
        ("Stage 1 Propellant 第一節推進劑", total_prop * 0.79, COLORS["s1_prop"]),
        ("Stage 1 Dry 第一節乾重",          total_dry  * 0.85, COLORS["s1_dry"]),
        ("Stage 2 Propellant 第二節推進劑", total_prop * 0.21, COLORS["s2_prop"]),
        ("Stage 2 Dry 第二節乾重",          total_dry  * 0.15, COLORS["s2_dry"]),
        ("Payload 酬載",                    payload,           COLORS["payload"]),
        ("Fairing 整流罩",                  fairing,           COLORS["fairing"]),
    ]

    fig = go.Figure()
    for name, value, color in segments:
        fig.add_trace(go.Bar(
            x=[value], y=["Vehicle 載具"],
            orientation="h", name=name,
            marker_color=color,
            text=[f"{value/1000:.1f} t"],
            textposition="inside",
            hovertemplate=f"{name}: %{{x:,.0f}} kg<extra></extra>",
        ))

    fig.update_layout(
        title="Liftoff Mass Budget 起飛質量預算",
        barmode="stack", height=210,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=-0.5, font=dict(size=11)),
        xaxis=dict(title="Mass (kg)", gridcolor="#333"),
        yaxis=dict(showticklabels=False),
        font=dict(color="#ccc"),
    )
    return fig


def chart_delta_v(result: dict) -> go.Figure:
    s = result.get("staging", {})
    total  = s.get("total_ideal_delta_v_m_s", 0)
    g_loss = s.get("gravity_loss_m_s", 0)
    d_loss = s.get("drag_loss_m_s", 0)
    s_loss = s.get("steering_loss_m_s", 0)
    usable = s.get("usable_delta_v_m_s", 0)
    req    = s.get("required_delta_v_m_s", 0)
    margin = s.get("delta_v_margin_m_s", 0)

    labels = [
        "Ideal ΔV\n理想速度增量",
        "−Gravity Loss\n−重力損失",
        "−Drag Loss\n−阻力損失",
        "−Steering\n−轉向損失",
        "Usable ΔV\n可用速度增量",
        "Margin\n餘量",
    ]
    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute","relative","relative","relative","total","relative"],
        x=labels,
        y=[total, -g_loss, -d_loss, -s_loss, 0, margin],
        text=[f"{total:,.0f}", f"-{g_loss:,.0f}", f"-{d_loss:,.0f}",
              f"-{s_loss:,.0f}", f"{usable:,.0f}", f"{margin:+,.0f}"],
        textposition="outside",
        connector=dict(line=dict(color="#555")),
        increasing=dict(marker_color=COLORS["green"]),
        decreasing=dict(marker_color=COLORS["red"]),
        totals=dict(marker_color=COLORS["blue"]),
    ))
    fig.add_hline(
        y=req, line_dash="dash", line_color=COLORS["amber"],
        annotation_text=f"Required 需求: {req:,.0f} m/s",
        annotation_font_color=COLORS["amber"],
    )
    fig.update_layout(
        title="Delta-V Budget 速度增量預算",
        height=380, margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(title="Δv (m/s)", gridcolor="#333"),
        font=dict(color="#ccc"),
    )
    return fig


def chart_single_sweep(param: dict, values: List[float],
                        points: List[dict], baseline_val: float) -> go.Figure:
    feasible   = [p.get("mission_feasible", False) for p in points]
    payloads   = [p.get("payload_mass_kg", 0) for p in points]
    max_pl     = [p.get("max_payload_kg") for p in points]
    dv_margins = [p.get("delta_v_margin_m_s", 0) for p in points]
    pt_colors  = [COLORS["green"] if f else COLORS["red"] for f in feasible]

    fig = go.Figure()

    feasible_x = [v for v, f in zip(values, feasible) if f]
    if feasible_x:
        fig.add_vrect(
            x0=min(feasible_x), x1=max(feasible_x),
            fillcolor="rgba(46,204,113,0.07)", layer="below", line_width=0,
            annotation_text="Feasible Region 可行區域",
            annotation_font_color=COLORS["green"],
            annotation_position="top left",
        )

    fig.add_trace(go.Scatter(
        x=values, y=payloads, mode="lines+markers",
        name="Payload Mass 酬載質量 (kg)",
        line=dict(color=COLORS["blue"], width=2),
        marker=dict(color=pt_colors, size=10, line=dict(width=1, color="#fff")),
        yaxis="y1",
        hovertemplate=(
            f"{param['label']} {param['label_zh']}: %{{x:,.1f}} {param['unit']}<br>"
            "Payload 酬載: %{y:,.0f} kg<extra></extra>"
        ),
    ))

    if any(v is not None for v in max_pl):
        fig.add_trace(go.Scatter(
            x=values, y=[v if v else None for v in max_pl],
            mode="lines", name="Max Payload 最大酬載 (kg)",
            line=dict(color=COLORS["blue"], width=1, dash="dot"),
            yaxis="y1",
        ))

    fig.add_trace(go.Scatter(
        x=values, y=dv_margins, mode="lines+markers",
        name="ΔV Margin 速度增量餘量 (m/s)",
        line=dict(color=COLORS["amber"], width=2, dash="dash"),
        marker=dict(color=COLORS["amber"], size=7),
        yaxis="y2",
        hovertemplate="ΔV Margin 餘量: %{y:+,.0f} m/s<extra></extra>",
    ))

    fig.add_hline(y=0, line_dash="dot", line_color="#777", yref="y2",
                  annotation_text="ΔV=0 min viable 最低可行",
                  annotation_font_color="#888", annotation_position="bottom right")
    fig.add_vline(x=baseline_val, line_dash="dash", line_color="#aaa",
                  annotation_text="Baseline 基準值", annotation_font_color="#aaa")

    fig.update_layout(
        title=f"Trade Study 權衡研究: {param['label']} {param['label_zh']}",
        xaxis=dict(title=f"{param['label']} {param['label_zh']} ({param['unit']})",
                   gridcolor="#333"),
        yaxis=dict(title="Payload Mass 酬載質量 (kg)", gridcolor="#333", side="left"),
        yaxis2=dict(title="ΔV Margin 餘量 (m/s)", overlaying="y", side="right",
                    zeroline=True, zerolinecolor="#555",
                    gridcolor="rgba(0,0,0,0)"),
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(0,0,0,0.4)"),
        height=430, margin=dict(l=10, r=70, t=50, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccc"), hovermode="x unified",
    )
    return fig


def chart_heatmap(sweep_param: dict, compare_param: dict,
                  sweep_values: List[float], compare_values: List[float],
                  results_grid: List[List[Optional[dict]]],
                  metric: str, metric_label: str) -> go.Figure:

    def extract(pt):
        if pt is None:
            return None
        if metric == "mission_feasible":
            return 1.0 if pt.get("mission_feasible") else 0.0
        return pt.get(metric)

    z    = [[extract(results_grid[i][j]) for i in range(len(sweep_values))]
             for j in range(len(compare_values))]
    text = [[f"{extract(results_grid[i][j]):,.0f}"
             if extract(results_grid[i][j]) is not None else "ERR"
             for i in range(len(sweep_values))]
            for j in range(len(compare_values))]

    colorscale = "RdYlGn" if metric != "mission_feasible" else [
        [0.0, COLORS["red"]], [1.0, COLORS["green"]]
    ]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[f"{v:,.0f}" for v in sweep_values],
        y=[f"{v:,.0f}" for v in compare_values],
        text=text, texttemplate="%{text}",
        colorscale=colorscale,
        hovertemplate=(
            f"{sweep_param['label']}: %{{x}}<br>"
            f"{compare_param['label']}: %{{y}}<br>"
            f"{metric_label}: %{{z:,.0f}}<extra></extra>"
        ),
        colorbar=dict(title=metric_label, tickfont=dict(color="#ccc")),
    ))

    fig.update_layout(
        title=(f"{metric_label} — "
               f"{sweep_param['label']} {sweep_param['label_zh']} × "
               f"{compare_param['label']} {compare_param['label_zh']}"),
        xaxis=dict(title=f"{sweep_param['label']} {sweep_param['label_zh']} ({sweep_param['unit']})",
                   tickfont=dict(color="#ccc")),
        yaxis=dict(title=f"{compare_param['label']} {compare_param['label_zh']} ({compare_param['unit']})",
                   tickfont=dict(color="#ccc")),
        height=430, margin=dict(l=10, r=10, t=50, b=60),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccc"),
    )
    return fig


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def csv_single(param, values, points, baseline) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["# Falcon 9-like Rocket Simulator — Single-Parameter Trade Study"])
    w.writerow(["# Generated / 產生時間", datetime.now().isoformat()])
    w.writerow(["# Parameter / 參數", param["label"], param["label_zh"], param["dot_path"]])
    w.writerow(["# Baseline / 基準值", deep_get(baseline, param["dot_path"])])
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
    return buf.getvalue()


def csv_comparison(sweep_param, compare_param, sweep_values,
                   compare_values, results_grid) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["# Falcon 9-like Rocket Simulator — Two-Parameter Trade Study"])
    w.writerow(["# Generated / 產生時間", datetime.now().isoformat()])
    w.writerow(["# X-axis / X 軸", sweep_param["label"], sweep_param["label_zh"]])
    w.writerow(["# Y-axis / Y 軸", compare_param["label"], compare_param["label_zh"]])
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
            pt = results_grid[i][j]
            if pt is None:
                w.writerow([sv, cv, "ERROR","","","",""])
            else:
                w.writerow([sv, cv,
                            pt.get("payload_mass_kg",""),
                            pt.get("max_payload_kg",""),
                            pt.get("delta_v_margin_m_s",""),
                            "YES 是" if pt.get("mission_feasible") else "NO 否",
                            pt.get("limiting_factor","")])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def build_sidebar() -> Tuple[str, dict, bool]:
    st.sidebar.title("🚀 設定 Configuration")

    base_url = st.sidebar.text_input("API URL", DEFAULT_API)

    if st.sidebar.button("🔌 檢查連線 Check Connection"):
        st.session_state["api_ok"] = api_health(base_url)

    api_ok = st.session_state.get("api_ok")
    if api_ok is True:
        st.sidebar.success("✅ API 已連線 Connected")
    elif api_ok is False:
        st.sidebar.error("❌ 無法連線 — 請先啟動 uvicorn")
    else:
        st.sidebar.info("點擊上方按鈕確認連線 / Click above to verify.")

    st.sidebar.divider()
    st.sidebar.subheader("基準載具 Baseline Vehicle")
    st.sidebar.caption("以下數值為所有權衡研究的起始點。\nThese values define the starting point for all trade studies.")

    baseline = copy.deepcopy(BASELINE_DEFAULT)

    with st.sidebar.expander("📦 酬載與任務 Payload & Mission", expanded=True):
        baseline["payload_mass"] = st.slider(
            "酬載質量 Payload Mass (kg)", 1000, 35000,
            int(BASELINE_DEFAULT["payload_mass"]), 500)
        baseline["mission"]["target_altitude_km"] = st.slider(
            "目標高度 Target Altitude (km)", 200, 1500,
            int(BASELINE_DEFAULT["mission"]["target_altitude_km"]), 50)
        baseline["fairing_mass"] = st.slider(
            "整流罩質量 Fairing Mass (kg)", 500, 4000,
            int(BASELINE_DEFAULT["fairing_mass"]), 100)
        baseline["mission"]["reusable_booster"] = st.checkbox(
            "可回收推進器 Reusable Booster",
            BASELINE_DEFAULT["mission"]["reusable_booster"])
        if baseline["mission"]["reusable_booster"]:
            baseline["mission"]["reusable_penalty_kg"] = st.slider(
                "回收質量損失 Reuse Penalty (kg)", 0, 20000, 5000, 500)

    with st.sidebar.expander("🔵 第一節 Stage 1 (Booster)"):
        baseline["stage1"]["prop_mass"] = st.slider(
            "推進劑 Propellant (kg)", 200000, 550000,
            int(BASELINE_DEFAULT["stage1"]["prop_mass"]), 5000)
        baseline["stage1"]["dry_mass"] = st.slider(
            "乾重 Dry Mass (kg)", 10000, 40000,
            int(BASELINE_DEFAULT["stage1"]["dry_mass"]), 500)
        baseline["stage1"]["engine"]["isp_vac"] = st.slider(
            "真空比衝 Vacuum Isp (s)", 280, 340,
            int(BASELINE_DEFAULT["stage1"]["engine"]["isp_vac"]), 1)
        baseline["stage1"]["engine_count"] = st.slider(
            "發動機數量 Engine Count", 1, 9,
            int(BASELINE_DEFAULT["stage1"]["engine_count"]), 1)

    with st.sidebar.expander("🟠 第二節 Stage 2 (Upper Stage)"):
        baseline["stage2"]["prop_mass"] = st.slider(
            "推進劑 Propellant (kg)", 50000, 160000,
            int(BASELINE_DEFAULT["stage2"]["prop_mass"]), 2500)
        baseline["stage2"]["dry_mass"] = st.slider(
            "乾重 Dry Mass (kg)", 1500, 10000,
            int(BASELINE_DEFAULT["stage2"]["dry_mass"]), 250)
        baseline["stage2"]["engine"]["isp_vac"] = st.slider(
            "真空比衝 Vacuum Isp (s)", 300, 390,
            int(BASELINE_DEFAULT["stage2"]["engine"]["isp_vac"]), 1)

    st.sidebar.divider()
    run_btn = st.sidebar.button(
        "▶ 執行基準模擬 Run Baseline Simulation",
        type="primary", use_container_width=True)

    return base_url, baseline, run_btn


# ---------------------------------------------------------------------------
# Tab 1: Dashboard
# ---------------------------------------------------------------------------

def tab_dashboard(base_url: str, baseline: dict, run_baseline: bool) -> None:
    st.header("📊 儀表板 Dashboard")

    if run_baseline or "baseline_result" not in st.session_state:
        with st.spinner("執行基準模擬中… Running baseline simulation…"):
            result = api_simulate(base_url, baseline)
        if result:
            st.session_state["baseline_result"] = result
            st.session_state["baseline_cfg"]    = copy.deepcopy(baseline)

    result = st.session_state.get("baseline_result")
    if not result:
        st.info("👈 在側邊欄設定載具後，點擊「執行基準模擬」。\n\nConfigure the vehicle in the sidebar, then click **Run Baseline Simulation**.")
        return

    if not result.get("ok"):
        errs = result.get("errors", [])
        st.error("模擬失敗 Simulation failed:\n" + "\n".join(f"• {e}" for e in errs))
        for c in result.get("constraints", []):
            icon = "✅" if c["passed"] else ("⚠️" if c["severity"] == "warning" else "❌")
            st.write(f"{icon} **{c['name']}** — {c['message']}")
        return

    mb   = result.get("mass_budget", {})
    stg  = result.get("staging", {})
    pl   = result.get("payload", {})

    # KPI cards
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("酬載 Payload",
              f"{mb.get('payload_mass_kg',0):,.0f} kg",
              delta=f"{mb.get('payload_fraction',0)*100:.2f}% of liftoff")
    c2.metric("起飛質量 Liftoff",
              f"{mb.get('liftoff_mass_kg',0)/1000:,.1f} t")
    twr = mb.get("liftoff_twr", 0)
    c3.metric("推重比 TWR", f"{twr:.3f}",
              delta="OK ✓" if twr >= 1.2 else "Low 偏低",
              delta_color="normal" if twr >= 1.2 else "inverse")
    margin = stg.get("delta_v_margin_m_s", 0)
    c4.metric("ΔV 餘量 Margin", f"{margin:+,.0f} m/s",
              delta="可行 Feasible" if pl.get("mission_feasible") else "不可行 Infeasible",
              delta_color="normal" if pl.get("mission_feasible") else "inverse")
    max_pl = pl.get("max_payload_kg")
    c5.metric("最大酬載 Max Payload",
              f"{max_pl:,.0f} kg" if max_pl else "N/A")

    st.divider()
    col_l, col_r = st.columns(2)
    with col_l:
        st.plotly_chart(chart_mass_budget(result), use_container_width=True)
    with col_r:
        st.plotly_chart(chart_delta_v(result), use_container_width=True)

    # Stage detail table
    st.divider()
    st.subheader("各節性能 Stage Performance")
    s1r = stg.get("stage1", {})
    s2r = stg.get("stage2", {})
    ca, cb = st.columns(2)
    for col, sr, title in [(ca, s1r, "🔵 第一節 Stage 1 (Booster)"),
                            (cb, s2r, "🟠 第二節 Stage 2 (Upper Stage)")]:
        with col:
            st.markdown(f"**{title}**")
            st.dataframe({
                "指標 Metric": ["初始質量 Initial Mass", "終態質量 Final Mass",
                                 "質量比 Mass Ratio", "有效比衝 Eff. Isp",
                                 "理想ΔV Ideal ΔV", "燃燒時間 Burn Time"],
                "數值 Value": [
                    f"{sr.get('m0_kg',0):,.0f} kg",
                    f"{sr.get('mf_kg',0):,.0f} kg",
                    f"{sr.get('mass_ratio',0):.3f}",
                    f"{sr.get('isp_effective_s',0):.1f} s",
                    f"{sr.get('ideal_delta_v_m_s',0):,.0f} m/s",
                    f"{sr.get('burn_time_s',0):.0f} s",
                ],
            }, hide_index=True, use_container_width=True)

    # Constraints
    constraints = result.get("constraints", [])
    if constraints:
        st.divider()
        st.subheader("設計限制檢查 Constraint Checks")
        for c in constraints:
            icon  = "✅" if c["passed"] else ("⚠️" if c["severity"] == "warning" else "❌")
            color = "green" if c["passed"] else ("orange" if c["severity"] == "warning" else "red")
            st.markdown(f":{color}[{icon} **{c['name']}**] — {c['message']}")


# ---------------------------------------------------------------------------
# Tab 2: Single-Parameter Sweep
# ---------------------------------------------------------------------------

def tab_single_sweep(base_url: str, baseline: dict) -> None:
    st.header("📈 單參數掃描 Single-Parameter Sweep")
    st.caption(
        "選擇一個設計變數並設定掃描範圍，觀察酬載性能與任務可行性的變化。\n"
        "Choose one design variable, set a sweep range, and observe how payload performance changes."
    )

    col_cfg, col_info = st.columns([2, 1])

    with col_cfg:
        param_id = st.selectbox(
            "選擇掃描參數 Parameter to sweep",
            [p["id"] for p in PARAMETERS],
            format_func=param_label_bilingual,
        )
        param = PARAM_BY_ID[param_id]
        baseline_val = deep_get(baseline, param["dot_path"])

        c1, c2, c3 = st.columns(3)
        step_hint = float(max(1, (param["default_max"] - param["default_min"]) / 20))
        lo    = c1.number_input(f"最小值 Min ({param['unit']})",
                                value=float(param["default_min"]), step=step_hint)
        hi    = c2.number_input(f"最大值 Max ({param['unit']})",
                                value=float(param["default_max"]), step=step_hint)
        steps = c3.number_input("步數 Steps", min_value=2, max_value=50,
                                value=int(param["default_steps"]))

    with col_info:
        st.info(
            f"**{param['label']}**\n\n"
            f"**{param['label_zh']}**\n\n"
            f"{param['description']}\n\n"
            f"{param['description_zh']}\n\n"
            f"💡 {param['note']}\n\n"
            f"💡 {param['note_zh']}"
        )
        st.metric("基準值 Baseline", f"{baseline_val:,.1f} {param['unit']}")

    with st.expander("📖 教師備注 Teacher's Note", expanded=False):
        st.markdown(
            f"**English:**\n\n{param['teacher_note']}\n\n"
            f"---\n\n**中文說明：**\n\n{param['teacher_note_zh']}"
        )

    if lo >= hi:
        st.warning("最小值必須小於最大值。 Min must be less than Max.")
        return

    values = linspace(float(lo), float(hi), int(steps))
    st.caption(
        f"掃描範圍 Sweep: {lo:,.1f} → {hi:,.1f}，共 {steps} 步，"
        f"步長 step = {(hi-lo)/(steps-1):,.2f} {param['unit']}"
    )

    if st.button("▶ 執行掃描 Run Sweep", type="primary"):
        with st.spinner(f"執行 {steps} 次模擬… Running {steps} simulations…"):
            resp = api_sensitivity(base_url, baseline, param["dot_path"], values)
        if resp:
            st.session_state["sweep_result"]      = resp.get("points", [])
            st.session_state["sweep_param"]       = param
            st.session_state["sweep_values"]      = values
            st.session_state["sweep_baseline_val"] = baseline_val

    points   = st.session_state.get("sweep_result")
    s_param  = st.session_state.get("sweep_param")
    s_values = st.session_state.get("sweep_values", [])
    s_bval   = st.session_state.get("sweep_baseline_val", baseline_val)

    if not points or not s_param:
        st.info("設定掃描參數後點擊「執行掃描」。\nConfigure the sweep above and click **Run Sweep**.")
        return

    st.plotly_chart(chart_single_sweep(s_param, s_values, points, s_bval),
                    use_container_width=True)

    feasible   = [p for p in points if p.get("mission_feasible")]
    infeasible = [p for p in points if not p.get("mission_feasible")]

    ca, cb, cc = st.columns(3)
    ca.metric("可行配置 Feasible Configs", f"{len(feasible)} / {len(points)}")
    if feasible:
        best     = max(feasible, key=lambda p: p.get("payload_mass_kg", 0))
        best_idx = points.index(best)
        cb.metric("最佳酬載 Best Payload",
                  f"{best.get('payload_mass_kg',0):,.0f} kg",
                  delta=f"at {s_param['label_zh']} = {s_values[best_idx]:,.1f} {s_param['unit']}")
    if infeasible:
        fi_idx = points.index(infeasible[0])
        cc.metric("任務失敗點 Mission Fails At",
                  f"{s_values[fi_idx]:,.1f} {s_param['unit']}")

    with st.expander("📋 完整結果表 Full Results Table"):
        rows = []
        for val, pt in zip(s_values, points):
            rows.append({
                f"{s_param['label']} {s_param['label_zh']} ({s_param['unit']})": round(val, 2),
                "酬載 Payload (kg)":       round(pt.get("payload_mass_kg", 0), 0),
                "最大酬載 Max Payload (kg)":
                    round(pt.get("max_payload_kg", 0), 0) if pt.get("max_payload_kg") else None,
                "ΔV 餘量 Margin (m/s)":    round(pt.get("delta_v_margin_m_s", 0), 0),
                "可行 Feasible":           "✅ 是 YES" if pt.get("mission_feasible") else "❌ 否 NO",
                "限制因素 Limiting Factor": pt.get("limiting_factor", ""),
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label="⬇ 下載 CSV Download CSV",
        data=csv_single(s_param, s_values, points, baseline),
        file_name=f"trade_{s_param['id']}_{ts}.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Tab 3: Two-Parameter Study
# ---------------------------------------------------------------------------

def tab_two_param(base_url: str, baseline: dict) -> None:
    st.header("🗺️ 雙參數比較 Two-Parameter Comparison")
    st.caption(
        "掃描主要參數，同時固定次要參數於數個離散值，熱圖揭示兩個設計變數的交互關係。\n"
        "Sweep a primary parameter while holding a secondary parameter at discrete values. "
        "The heatmap reveals how the two variables interact."
    )

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("主要參數 Primary (X-axis sweep)")
        sweep_id = st.selectbox(
            "掃描參數 Sweep parameter",
            [p["id"] for p in PARAMETERS],
            format_func=param_label_bilingual,
            key="sweep_id_2p",
        )
        sweep_param = PARAM_BY_ID[sweep_id]
        sh = float(max(1, (sweep_param["default_max"] - sweep_param["default_min"]) / 20))
        c1, c2, c3 = st.columns(3)
        sweep_lo    = c1.number_input(f"Min ({sweep_param['unit']})",
                                      value=float(sweep_param["default_min"]), step=sh, key="slo")
        sweep_hi    = c2.number_input(f"Max ({sweep_param['unit']})",
                                      value=float(sweep_param["default_max"]), step=sh, key="shi")
        sweep_steps = c3.number_input("Steps 步數", min_value=2, max_value=10,
                                      value=min(int(sweep_param["default_steps"]), 6),
                                      key="ssteps")
        with st.expander("📖 教師備注 Teacher's Note"):
            st.markdown(
                f"**English:** {sweep_param['teacher_note']}\n\n"
                f"**中文：** {sweep_param['teacher_note_zh']}"
            )

    with col_r:
        st.subheader("次要參數 Secondary (Y-axis discrete)")
        avail = [p for p in PARAMETERS if p["id"] != sweep_id]
        compare_id = st.selectbox(
            "比較參數 Comparison parameter",
            [p["id"] for p in avail],
            format_func=param_label_bilingual,
            key="cmp_id",
        )
        compare_param = PARAM_BY_ID[compare_id]
        n_disc = st.number_input("離散值數量 Discrete values", min_value=2,
                                 max_value=6, value=3, key="ndisc")
        compare_values = []
        for i in range(int(n_disc)):
            dv = compare_param["default_min"] + (
                (compare_param["default_max"] - compare_param["default_min"])
                * i / max(n_disc - 1, 1)
            )
            v = st.number_input(
                f"值 Value {i+1} ({compare_param['unit']})",
                value=round(float(dv), 1), key=f"cv_{i}",
            )
            compare_values.append(v)
        with st.expander("📖 教師備注 Teacher's Note"):
            st.markdown(
                f"**English:** {compare_param['teacher_note']}\n\n"
                f"**中文：** {compare_param['teacher_note_zh']}"
            )

    metric_options = {
        "payload_mass_kg":    "酬載質量 Payload Mass (kg)",
        "delta_v_margin_m_s": "ΔV 餘量 Margin (m/s)",
        "mission_feasible":   "任務可行性 Mission Feasible",
        "max_payload_kg":     "最大酬載 Max Payload (kg)",
    }
    metric_key = st.selectbox(
        "熱圖指標 Heatmap metric",
        list(metric_options.keys()),
        format_func=lambda k: metric_options[k],
    )
    metric_label = metric_options[metric_key]

    sweep_values = linspace(float(sweep_lo), float(sweep_hi), int(sweep_steps))
    total_runs   = len(sweep_values) * len(compare_values)

    ok_runs = total_runs <= 50
    st.caption(
        f"總模擬次數 Total runs: **{total_runs}** "
        f"{'✅ OK' if ok_runs else '❌ 超過上限 50，請減少步數或離散值 — reduce steps or values'}"
    )

    if not ok_runs:
        st.error("請減少掃描步數或離散值數量，使總次數 ≤ 50。\nReduce sweep steps or discrete values to ≤ 50 total runs.")
        return
    if sweep_lo >= sweep_hi:
        st.warning("最小值必須小於最大值。 Min must be less than Max.")
        return

    if st.button("▶ 執行比較 Run Comparison", type="primary"):
        runs = []
        for sv in sweep_values:
            for cv in compare_values:
                veh = deep_set(baseline, sweep_param["dot_path"], sv)
                veh = deep_set(veh, compare_param["dot_path"], cv)
                veh["sim_config"]["run_trajectory"] = False
                runs.append(veh)

        with st.spinner(f"執行 {total_runs} 次模擬… Running {total_runs} simulations…"):
            batch = api_batch(base_url, runs)

        if batch:
            grid: List[List[Optional[dict]]] = []
            idx = 0
            for i in range(len(sweep_values)):
                col = []
                for j in range(len(compare_values)):
                    res = batch[idx] if idx < len(batch) else None
                    col.append(res["payload"] if res and res.get("ok") and res.get("payload") else None)
                    idx += 1
                grid.append(col)

            st.session_state.update({
                "cmp_grid": grid,
                "cmp_sweep_param": sweep_param,
                "cmp_compare_param": compare_param,
                "cmp_sweep_values": sweep_values,
                "cmp_compare_values": compare_values,
            })

    grid  = st.session_state.get("cmp_grid")
    s_sp  = st.session_state.get("cmp_sweep_param")
    s_cp  = st.session_state.get("cmp_compare_param")
    s_sv  = st.session_state.get("cmp_sweep_values", [])
    s_cv  = st.session_state.get("cmp_compare_values", [])

    if not grid or not s_sp:
        st.info("設定參數後點擊「執行比較」。\nConfigure parameters above and click **Run Comparison**.")
        return

    st.plotly_chart(
        chart_heatmap(s_sp, s_cp, s_sv, s_cv, grid, metric_key, metric_label),
        use_container_width=True,
    )

    with st.expander("📋 完整結果表 Full Results Table"):
        rows = []
        for i, sv in enumerate(s_sv):
            for j, cv in enumerate(s_cv):
                pt = grid[i][j]
                rows.append({
                    f"{s_sp['label']} {s_sp['label_zh']} ({s_sp['unit']})": round(sv, 2),
                    f"{s_cp['label']} {s_cp['label_zh']} ({s_cp['unit']})": round(cv, 2),
                    "酬載 Payload (kg)": round(pt.get("payload_mass_kg",0),0) if pt else "ERR",
                    "ΔV 餘量 Margin (m/s)": round(pt.get("delta_v_margin_m_s",0),0) if pt else "ERR",
                    "可行 Feasible": ("✅ 是" if pt.get("mission_feasible") else "❌ 否") if pt else "ERR",
                })
        st.dataframe(rows, use_container_width=True, hide_index=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label="⬇ 下載 CSV Download CSV",
        data=csv_comparison(s_sp, s_cp, s_sv, s_cv, grid),
        file_name=f"trade_{s_sp['id']}_vs_{s_cp['id']}_{ts}.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Tab 4: Student Guide / Teacher Reference
# ---------------------------------------------------------------------------

def tab_guide() -> None:
    st.header("📚 學習指南與教師參考 Student Guide & Teacher Reference")

    tab_s, tab_t = st.tabs(["🎓 學生版 Student Version", "👩‍🏫 教師版 Teacher Edition"])

    # ── Student version ──────────────────────────────────────────────────────
    with tab_s:
        st.markdown("""
## 什麼是設計權衡研究？ What is a Design Trade Study?

**中文：** 權衡研究是比較多個可行設計方案，根據性能、成本、風險等多項指標加權評分，找出最平衡的方案。
透過系統地改變設計變數，可以觀察系統性能的變化。在火箭設計中，核心問題永遠是：**我們能把多少酬載送入軌道？**

**English:** A trade study compares multiple viable design options against weighted criteria
(performance, cost, risk, etc.) to identify the most balanced solution. By systematically
varying design variables we observe how system performance responds. In rocket design,
the core question is always: **how much payload can we deliver to orbit?**

> The single-parameter sweeps and two-parameter comparisons in this simulator are common numerical methods used within a trade study.

---

## 火箭方程式 The Rocket Equation (Tsiolkovsky / 齊奧爾科夫斯基)

$$\\Delta v = I_{sp} \\times g_0 \\times \\ln\\left(\\frac{m_0}{m_f}\\right)$$

| 符號 Symbol | 意義 Meaning |
|-------------|-------------|
| Δv | 速度增量（火箭可達到的速度變化）Velocity change the rocket can achieve |
| Isp | 比衝——發動機「燃油效率」Specific impulse — engine fuel economy |
| g₀ | 標準重力 9.80665 m/s² |
| m₀ | 初始（濕）質量：推進劑＋結構＋酬載 Initial (wet) mass |
| mf | 終態（乾）質量：結構＋酬載 Final (dry) mass |

> 💡 **關鍵洞察 Key insight:** 關係是**對數型**，推進劑加倍並不能使 Δv 加倍，效益遞減。
> The relationship is **logarithmic** — doubling propellant does NOT double Δv.

---

## 到達軌道需要多少 Δv？ How Much Δv to Reach Orbit?

| 目標軌道 Mission | Δv 需求 Required |
|----------------|----------------|
| 低地球軌道 LEO (400 km) | ~9,300 m/s |
| 太陽同步軌道 SSO (600 km) | ~9,700 m/s |
| 地球同步轉移軌道 GTO | ~11,400 m/s |

其中包含約 1,500–2,000 m/s 的重力與氣動損失（視 TWR 與軌跡而定）。
(Including ~1,500–2,000 m/s of gravity and aerodynamic losses, depending on TWR and trajectory.)

---

## 模擬器運算流程 Simulation Pipeline

```
載具設定 Vehicle Config
    │
    ▼
推進計算 Propulsion Solver  →  推力、比衝、質量流率
    │
    ▼
質量預算 Mass Budget        →  起飛質量、酬載分率、推重比
    │
    ▼
分節計算 Staging Solver     →  各節 Δv、重力/阻力/轉向損失
    │
    ▼
酬載估算 Payload Estimator  →  最大酬載、任務可行性
    │
    ▼
限制檢查 Constraint Checker →  推重比、燃燒時間、結構分率
```

---

## 如何解讀結果 How to Read Results

| 指標 Metric | 好的範圍 Good Range | 說明 Note |
|------------|-------------------|----------|
| 推重比 TWR | ≥ 1.2 | 低於 1.0 無法離開發射台 Below 1.0 = can't lift off |
| ΔV 餘量 Margin | > 200 m/s | 正值代表可行，愈大愈有裕度 Positive = feasible |
| 結構分率 S1 Structure | 5–8% | 乾重/總重，愈低愈好 Lower is better |
| 結構分率 S2 Structure | 3–6% | 上節結構效率 Upper stage efficiency |
| 酬載分率 Payload Fraction | 2–5% | 典型兩節式火箭的範圍（For orbital rockets, payload fractions are typically 1–5% of liftoff mass; 1–2% is not unusual for real launchers） |

---

## 建議課堂練習 Suggested Class Exercises

| 探索問題 Question | 使用功能 Mode | 掃描參數 Parameter |
|-----------------|-------------|-----------------|
| 最多能攜帶多少酬載？ | 單參數掃描 | 酬載質量 Payload Mass |
| 軌道高度如何影響性能？ | 單參數掃描 | 目標高度 Target Altitude |
| 第二節比衝有多重要？ | 單參數掃描 | S2 Vacuum Isp |
| 可回收的代價是什麼？ | 單參數掃描 | 回收質量損失 Reuse Penalty |
| 兩節推進劑最佳分配？ | 雙參數比較 | S1 Prop × S2 Prop |
| 乾重與比衝如何交互？ | 雙參數比較 | S2 Dry Mass × S2 Isp |
""")

    # ── Teacher version ───────────────────────────────────────────────────────
    with tab_t:
        st.markdown("""
## 教師版：深入概念說明 Teacher Edition: In-Depth Concepts

---

### 1. 分節最佳化理論 Staging Optimization Theory

對於兩節火箭，在總推進劑質量固定的條件下，最大化酬載的分配條件（Lagrange 乘數法）：

For a two-stage rocket with fixed total propellant, the optimal propellant split (via Lagrange multipliers) occurs when:

$$\\frac{\\partial \\Delta v_1}{\\partial \\epsilon_1} = \\frac{\\partial \\Delta v_2}{\\partial \\epsilon_2}$$

其中 ε 為各節結構分率 (where ε = structure fraction per stage).

> **注意：** 上式為概念性最優條件（邊際效益相等），而非完整推導。完整求解需代入各節的 Isp 與結構約束。
> **Note:** The equation above is a conceptual optimality condition (equal marginal benefit), not a closed-form derivation. A full solution requires substituting each stage's Isp and structural constraints.

**實際意義：** 在結構分率**相同**的理想情況下，兩節的質量比應相等（此為簡化結論）。
實際上，由於第一節與第二節的 Isp 和結構分率不同，最佳解通常偏向較重的第一節。
以獵鷹 9 號為例，約 80% 的推進劑集中在第一節。

**Practical implication:** With *identical* structure fractions, optimal mass ratios are equal for both stages (simplified ideal case).
In practice, differing Isp and structure fractions skew the optimum toward a heavier Stage 1 — Falcon 9 places ~80% of propellant in S1.

---

### 2. 比衝的物理意義 Physical Meaning of Specific Impulse

$$I_{sp} = \\frac{F}{\\dot{m} \\cdot g_0} = \\frac{v_e}{g_0}$$

- $v_e$ = 噴氣有效排氣速度 (effective exhaust velocity)
- 比衝可視為「每公斤推進劑提供的衝量（以秒計）」

**推進劑比較 Propellant Comparison:**

| 推進劑組合 Combination | 真空 Isp (s)¹ | 用途 Application |
|----------------------|-------------|----------------|
| RP-1 / LOX | ~310–340 | 一節推進器 (Merlin, RD-180) |
| LH₂ / LOX | 420–453 | 上節、太空梭主發動機 |
| CH₄ / LOX | 363–380 | Raptor (Starship)（真空型） |
| N₂O₄ / UDMH | 311–316 | 可儲存推進劑，衛星推進 |
| Xe (離子 Ion) | 1500–3000 | 深空探測，推力極低 |

¹ 表中數值均為**真空比衝**（Vacuum Isp）；海平面比衝因背壓損失通常低 5–15%。
¹ All values are **vacuum Isp**; sea-level Isp is typically 5–15% lower due to back-pressure losses.

---

### 3. 重力損失的來源 Origin of Gravity Losses

重力損失發生在火箭**垂直（或接近垂直）飛行**時，部分推力用於對抗重力而非加速：

Gravity losses occur when the rocket burns thrust to fight gravity rather than accelerate:

$$\\Delta v_{grav} = \\int_0^{t_{burn}} g(h) \\cdot \\sin(\\gamma) \\, dt$$

其中 γ 為飛行路徑角。完美水平飛行時損失為零，垂直飛行時損失最大。

(where γ = flight path angle. Zero loss for horizontal flight, maximum for vertical ascent.)

依火箭配置不同，重力損失大約 **1,000–2,000 m/s**，拖曳損失約 **50–300 m/s**，轉向損失 20–100 m/s。

Depending on rocket configuration, gravity losses ~1,000–2,000 m/s, drag losses ~50–300 m/s, steering losses 20–100 m/s.

---

### 4. 最大動壓（Max-Q）的重要性 Significance of Max-Q

$$q = \\frac{1}{2} \\rho(h) v^2$$

Max-Q 是飛行過程中動壓最大的時刻（獵鷹 9 號約在 13 公里高、飛行 80 秒時），
此時結構承受最大氣動載荷。火箭在 Max-Q 附近節流（throttle down）以降低結構應力。

Max-Q is the moment of maximum dynamic pressure (~13 km, ~80 s into flight for Falcon 9),
when structural aerodynamic loads peak. Rockets throttle down near Max-Q to reduce stress.

**F9 Max-Q:** 約 30–60 kPa（約 30–60% 海平面壓力，視任務與氣象而變）

---

### 5. 推重比（TWR）設計考量 TWR Design Considerations

| 情境 Scenario | 推薦 TWR |
|-------------|---------|
| 最低起飛條件 Minimum liftoff | ≥ 1.0 |
| 安全離台 Safe tower clearance | ≥ 1.2 |
| 典型一節 Typical first stage | 1.3–1.5 |
| 上節軌道插入 S2 orbit insertion | ≥ 0.3 |

> 獵鷹 9 號的起飛推重比約 **1.4**，是典型兩節液體火箭的代表值。
> Falcon 9 liftoff TWR ~1.4 is a representative value for typical two-stage liquid rockets.

TWR 過高：加速度過大，結構超載，乘員超 G；推進劑效率降低（高推力 = 高質量流率 = 短燃燒時間）。
TWR 過低：重力損失急劇增加，甚至無法離台。

Too high: structural overload, crew G-force, propellant efficiency loss.
Too low: gravity losses increase dramatically; below 1.0 = won't lift off.

---

### 6. 課堂討論題庫 Discussion Questions for Class

1. 為何增加推進劑的效益是遞減的？請用火箭方程式推導。
   *(Why do propellant additions yield diminishing ΔV returns? Derive from the equation.)*

2. 比較 RP-1/LOX 與 LH₂/LOX：比衝高但密度低，哪個更適合第一節？為什麼？
   *(Compare RP-1/LOX vs LH₂/LOX: higher Isp but lower density — which is better for Stage 1?)*

3. 如果你是獵鷹 9 號工程師，會如何分配 30 噸的「減重預算」來最大化酬載？
   *(If you were a Falcon 9 engineer with a 30-tonne weight reduction budget, how would you allocate it?)*

4. 在什麼條件下，可回收設計比一次性設計更具商業優勢？
   *(Under what conditions does reusability offer a commercial advantage over expendable designs?)*

5. 試解釋為何第二節的 Isp 對酬載的影響比第一節的 Isp 更大。
   *(Explain why Stage 2 Isp has a larger payload impact than Stage 1 Isp.)*

---

### 7. 獵鷹 9 號 Block 5 參考數據 Falcon 9 Block 5 Reference Data

| 參數 Parameter | 數值 Value |
|-------------|----------|
| 起飛質量 Liftoff mass | 549,054 kg |
| 第一節推進劑 S1 propellant | 411,000 kg (LOX/RP-1) |
| 第二節推進劑 S2 propellant | 107,500 kg |
| 第一節乾重 S1 dry mass | 22,200 kg |
| 第二節乾重 S2 dry mass | ~4,000 kg |
| S1 Merlin 1D (×9) 真空比衝 | 311 s |
| S2 Merlin 1D 真空比衝 | 348 s |
| S1 結構分率 Structure fraction | ~5.1% |
| S2 結構分率 Structure fraction | ~3.6% |
| LEO 酬載（非可回收）Payload exp. | 22,800 kg |
| LEO 酬載（返場著陸）Payload RTLS | ~15,600 kg |
| 起飛推重比 Liftoff TWR | ~1.40 |
""")


# ---------------------------------------------------------------------------
# Tab 7: Solver Reference
# ---------------------------------------------------------------------------

def _solver_phase_timeline() -> go.Figure:
    """
    Horizontal Gantt chart showing the 6 ascent phases with approximate
    timing from the Falcon 9-like baseline mission (T+0 to orbit insertion).
    The coast-2 (Hohmann coast) bar is truncated visually with a break marker
    so the chart remains readable despite the 44-minute coast.
    """
    # Approximate phase boundaries from the baseline simulation
    phases = [
        ("垂直上升\nVertical",       0,    30,   "#FFD700", "T+0 → T+30 s\nVertical rise to ~1.5 km"),
        ("重力轉向\nGravity Turn",   30,   159,  "#FF8C00", "T+30 → T+159 s\nPitch-over & gravity turn to MECO"),
        ("滑行段\nCoast (S1→S2)",    159,  175,  "#A0C8FF", "T+159 → T+175 s\nStaging & fairing sep."),
        ("S2 燃燒 1\nS2 Burn 1",     175,  560,  "#FF4500", "T+175 → T+560 s\nTransfer-orbit insertion"),
        ("霍曼滑行\nHohmann Coast",   560,  3200, "#7EC8E3", "T+560 → T+3200 s\n~44 min coast to apogee"),
        ("圓化燃燒\nCircularisation", 3200, 3202, "#FF6347", "T+3200 → T+3202 s\nCircularisation burn"),
    ]

    # Use a compressed x-axis: linear up to 600 s, then log-like for coast
    # Simpler: just display with actual time but clip at 700 for readability,
    # showing the coast bar with a capped width and an annotation.
    DISPLAY_MAX = 700   # seconds shown on axis
    annotations = []
    fig = go.Figure()

    for i, (label, t0, t1, color, note) in enumerate(phases):
        x0_d = min(t0, DISPLAY_MAX)
        x1_d = min(t1, DISPLAY_MAX)
        width_d = max(x1_d - x0_d, 2)   # ensure at least 2 s wide for thin bars

        fig.add_trace(go.Bar(
            x=[width_d],
            y=[label],
            base=[x0_d],
            orientation="h",
            marker=dict(color=color, line=dict(color="rgba(255,255,255,0.3)", width=1)),
            text=[f"  {t0:,}–{t1:,} s"],
            textposition="inside",
            insidetextanchor="middle",
            hovertemplate=f"<b>{label}</b><br>{note}<extra></extra>",
            showlegend=False,
            name=label,
        ))

        # Annotation for coast bar (extends far beyond display)
        if t1 > DISPLAY_MAX:
            annotations.append(dict(
                x=DISPLAY_MAX - 5, y=label,
                text=f"→ ends T+{t1:,} s",
                showarrow=False,
                font=dict(color="white", size=9),
                xanchor="right",
            ))

    # Key event markers
    events = [(159, "MECO"), (175, "SES-1"), (560, "SECO-1"), (3200, "Apogee"), (3202, "SECO-2")]
    for t_ev, ev_name in events:
        t_d = min(t_ev, DISPLAY_MAX - 5)
        fig.add_vline(x=t_d, line=dict(color="rgba(255,255,255,0.35)", dash="dot", width=1))
        fig.add_annotation(
            x=t_d, y=len(phases) - 0.5,
            text=ev_name,
            showarrow=False,
            font=dict(color="rgba(255,255,255,0.7)", size=9),
            textangle=-45,
            yanchor="bottom",
        )

    fig.update_layout(
        title=dict(
            text="飛行階段時序圖  Ascent Phase Timeline  (Falcon 9-like baseline)",
            font=dict(size=13, color="#ddd"),
        ),
        xaxis=dict(
            title="任務時間 Mission Elapsed Time (s)",
            range=[0, DISPLAY_MAX],
            gridcolor="#2a2a3a", tickcolor="#555",
            title_font=dict(color="#aaa"), tickfont=dict(color="#aaa"),
        ),
        yaxis=dict(
            gridcolor="#2a2a3a", tickcolor="#555",
            tickfont=dict(color="#ccc", size=10),
        ),
        barmode="overlay",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        height=320,
        margin=dict(l=10, r=10, t=50, b=50),
        annotations=annotations,
        font=dict(color="#ccc"),
    )
    return fig


def tab_solver_reference() -> None:
    """Tab 7: solver.py Reference — conceptual guide to the trajectory solver."""
    st.header("⚙️ 軌跡求解器參考文件  Trajectory Solver Reference")
    st.caption(
        "本頁說明 `solver.py` 的核心設計：狀態向量、受力模型、各飛行段導引律、"
        "事件驅動積分、軌道力學工具及輸出格式。\n\n"
        "This page documents the key design choices and physics embodied in `solver.py`, "
        "organised conceptually rather than line-by-line."
    )

    st.info(
        "**原始碼位置 Source file:** "
        "`packages/rocket_core/trajectory/solver.py`  ·  "
        "語言 Language: Python 3  ·  "
        "積分器 Integrator: `scipy.integrate.solve_ivp` (RK45)"
    )

    # ── Phase timeline visual ─────────────────────────────────────────────
    st.plotly_chart(_solver_phase_timeline(), use_container_width=True)
    st.caption(
        "X 軸截斷於 700 s 以保持可讀性；霍曼滑行段實際延伸至 T+3200 s（約 44 分鐘）。\n"
        "X-axis truncated at 700 s for readability; Hohmann coast actually extends to T+3200 s (~44 min)."
    )
    st.divider()

    # ── 8 section sub-tabs ────────────────────────────────────────────────
    (s_overview, s_forces, s_guidance, s_integration,
     s_orbital, s_outputs, s_design) = st.tabs([
        "🗺️ 1 · Model & State",
        "⚗️ 2 · Forces",
        "🧭 3 · Guidance",
        "🔗 4 · Integration",
        "🪐 5 · Orbital Mechanics",
        "📊 6 · Outputs",
        "🎯 7 · Design Themes",
    ])

    # ── Section 1: Overall model & state ──────────────────────────────────
    with s_overview:
        st.markdown("""
## 1. Overall Model & State  ·  總體模型與狀態向量

---

### Coordinate frame  座標系

The solver uses a **2-D point-mass ascent model** in a *local vertical frame*
attached to the launch site and propagating along the trajectory:

| Coordinate | Symbol | Description |
|---|---|---|
| Downrange | `x` | Arc length along the spherical-Earth surface (m) |
| Altitude | `y` | Height above the reference sphere (m) |
| Tangential velocity | `vx` | Horizontal component, positive downrange (m/s) |
| Radial velocity | `vy` | Vertical component, positive up (m/s) |
| Propellant mass | `mass` | Total vehicle mass at current time (kg) |

The complete **state vector** is therefore:

```
state = [x, y, vx, vy, mass]
```

> No attitude dynamics are integrated. Vehicle orientation is *prescribed* by the
> guidance law at each instant — the solver trusts the guidance to command
> achievable pitch angles.

---

### Spherical Earth geometry  球形地球幾何

The local radius at any point is `r = R_EARTH + y`, where
`R_EARTH = 6 371 000 m`.  All gravity and centrifugal/Coriolis terms use this
live radius, so the model correctly captures the weakening of gravity with altitude
and the geometry of circular orbits at different heights.

> **Why not a flat Earth?**
> For altitude changes of hundreds of km, the flat-Earth approximation introduces
> significant errors in orbital energy and angular momentum.  Using the spherical
> radius `r` costs almost nothing computationally and keeps the physics exact.

---

### References

- [AI Solutions — Hohmann transfer overview](https://ai-solutions.com/_freeflyeruniversityguide/hohmann_transfer.htm)
- [NASA TM-2003-000844 — Ascent trajectory fundamentals](https://ntrs.nasa.gov/api/citations/20030000844/downloads/20030000844.pdf)
- [Wikipedia — Hohmann transfer orbit](https://en.wikipedia.org/wiki/Hohmann_transfer_orbit)
""")

    # ── Section 2: Forces & environment ───────────────────────────────────
    with s_forces:
        st.markdown("""
## 2. Forces & Environment  ·  受力與環境模型

---

### 2a. Gravity and frame effects

**Gravity** uses the inverse-square law:

$$g = \\frac{GM_{\\oplus}}{r^2}, \\quad r = R_{\\oplus} + \\text{alt}$$

In the 2-D local frame the correct equations of motion are:

$$\\frac{dv_x}{dt} = \\frac{F_x}{m} - \\frac{v_y v_x}{r}$$

$$\\frac{dv_y}{dt} = \\frac{F_y}{m} - \\frac{GM}{r^2} + \\frac{v_x^2}{r}$$

The two non-thrust terms on the right are:

| Term | Equation | Physical meaning |
|---|---|---|
| **Centrifugal** (radial) | `+vx²/r` in `ay` | At `vx = v_circ = √(GM/r)` this exactly cancels gravity — circular orbit is self-sustaining |
| **Coriolis coupling** (tangential) | `−vy·vx/r` in `ax` | Enforces `d(r·vx)/dt = 0` during coasting — conserves specific angular momentum `h = r·vx` |

> **Why the Coriolis term matters:**
> Without `−vy·vx/r`, `vx` stays constant while altitude rises during a coast arc.
> Angular momentum would grow linearly with `r`, pumping energy into the orbit for free.
> In practice this caused the simulated Hohmann coast to reach **18 150 km** (escape trajectory)
> instead of the correct **260 km** apogee — a factor of 70 error.

---

### 2b. Atmosphere and drag

**Exponential atmosphere** with a single scale height `H`:

$$\\rho(h) = \\rho_0 \\, e^{-h / H}$$

**Drag force** along the velocity vector:

$$F_D = \\tfrac{1}{2} \\rho v^2 C_D A_{\\text{ref}}$$

where `A_ref = π (d/2)²` from the current stage's diameter `d`.

**Dynamic pressure** is tracked explicitly:

$$q = \\tfrac{1}{2} \\rho v^2$$

Max-Q (the peak of `q`) drives structural load constraints and the Stage 1
throttle-down window.

---

### 2c. Thrust and mass flow

Thrust is blended between sea-level and vacuum values as a function of altitude,
using a smooth exponential transition.  Mass flow rate follows from the blended Isp:

$$\\dot{m} = \\frac{F_{\\text{thrust}}}{I_{sp} \\cdot g_0}$$

**Throttle logic:**
- Stage 1 throttles to **72%** during the Max-Q window (~T+60 s to T+80 s)
- All other phases run at **100%**

**Propellant guard:**
When `mass ≤ mass_minimum` (dry mass + upper stack or payload), thrust and `ṁ` are
set to zero.  This prevents negative propellant mass or over-burn if the integrator
overshoots the nominal cutoff.

**Stage mass reset at separation:**
At staging the state mass is *explicitly* set to
`m_s2_dry + m_s2_prop + m_payload + m_fairing`,
not derived by subtracting Stage 1 dry mass.  This avoids carrying any S1 residual
propellant into the S2 burn budget.

---

### References

- [NASA — Ascent trajectory modelling](https://ntrs.nasa.gov/api/citations/20030000844/downloads/20030000844.pdf)
- [NASA — Atmospheric properties](https://ntrs.nasa.gov/api/citations/20090032036/downloads/20090032036.pdf)
- [Wikipedia — Max Q](https://en.wikipedia.org/wiki/Max_q)
- [DAMTP Cambridge — Rotating frame mechanics](https://www.damtp.cam.ac.uk/user/tong/relativity/six.pdf)
""")

    # ── Section 3: Guidance laws by phase ─────────────────────────────────
    with s_guidance:
        st.markdown("""
## 3. Guidance Laws by Phase  ·  各飛行段導引律

Attitude is **not integrated**; thrust direction is prescribed at each instant by a
guidance law — a function of time and current state.

---

### Phase 0 — Vertical rise  垂直上升

Thrust vector aligned with `+y` (straight up).
Runs from liftoff to `t_pitch_over`, estimated from a kinematic formula:

$$t_{\\text{pitch}} \\approx \\sqrt{ \\frac{2 \\, h_{\\text{pitch}}}{a_0} }$$

where `h_pitch` is the pitch-over altitude and `a₀` is the liftoff acceleration.

---

### Phase 1 — Gravity turn  重力轉向

A **cosine pitch program** transitions smoothly from 90° (vertical) at `t_pitch_over`
to a fixed "MECO pitch" of 30° at `t_meco`:

$$\\theta(t) = \\theta_{\\text{MECO}} + (90° - \\theta_{\\text{MECO}}) \\cdot \\cos\\!\\left(\\frac{\\pi}{2} \\cdot \\frac{t - t_{\\text{pitch}}}{t_{\\text{MECO}} - t_{\\text{pitch}}}\\right)$$

At MECO the vehicle retains significant upward velocity (~1.1 km/s), so Stage 2
continues on a rising trajectory reaching 170–200 km before the Hohmann burn.

---

### Phase 2 — Coast (staging)  滑行段（分節）

No thrust.  Only gravity + drag in the spherical-Earth equations.
Mass is reset to the Stage 2 stack at the start of this phase.

---

### Phase 3 — Stage 2 Burn 1 (transfer-orbit insertion)  霍曼轉移插入

A **ZEV-style (Zero-Effort-Velocity) guidance** with average centrifugal correction:

1. Compute the **transfer-orbit speed** at current radius using vis-viva:

$$v_{\\text{tgt}} = \\sqrt{ GM \\left(\\frac{2}{r} - \\frac{1}{a_{\\text{tr}}}\\right)}, \\quad a_{\\text{tr}} = \\frac{r + r_{\\text{target}}}{2}$$

2. Estimate remaining burn time `T_go = t_MECO - t`.

3. Compute net gravity minus centrifugal (averaged over the burn):

$$g_{\\text{net,avg}} = \\max\\!\\left(\\frac{GM}{r^2} - \\frac{\\bar{v}_x^2}{r},\\; 0\\right)$$

4. Desired pitch to null residual `vy` and reach `v_tgt` in `T_go`:

$$\\theta = \\arctan\\!\\left(\\frac{-v_y + g_{\\text{net,avg}} \\cdot T_{\\text{go}}}{v_{\\text{tgt}} - v_x}\\right), \\quad \\theta \\in [0°, 70°]$$

Burn 1 is split at **fairing separation** (`t_fair = t_ses1 + Δt_fair`):
the fairing mass is dropped mid-burn, resetting the state mass.

---

### Phase 4 — Hohmann coast to apogee  霍曼滑行至遠地點

No thrust.  Integrates until `vy` crosses zero **going negative** (apogee event).
A coarser timestep is used for efficiency over the 44-minute coast.

---

### Phase 5 — Stage 2 Burn 2 (circularisation)  圓化燃燒

**Prograde guidance:** thrust along the instantaneous velocity vector
`(vx, vy) / |v|`.  This handles any small residual `vy` at apogee.

Terminates when `vx = v_circ(r) = √(GM/r)` — the circularisation event.

---

### References

- [NASA — Ascent trajectory guidance](https://ntrs.nasa.gov/api/citations/20030000844/downloads/20030000844.pdf)
- [USU — Vis-viva and orbital manoeuvres](http://mae-nas.eng.usu.edu/MAE_5540_Web/propulsion_systems/section2/section2.4.pdf)
- [AI Solutions — Hohmann transfer](https://ai-solutions.com/_freeflyeruniversityguide/hohmann_transfer.htm)
""")

    # ── Section 4: Event-driven integration ───────────────────────────────
    with s_integration:
        st.markdown("""
## 4. Event-Driven Integration & Phase Stitching  ·  事件驅動積分與飛行段縫合

---

### Integrator

`scipy.integrate.solve_ivp` with the **RK45** (explicit Runge-Kutta 4/5) method.
Tolerances and maximum step size are moderate to balance accuracy against speed:

```python
solve_ivp(odes, [t0, t_end], state0,
          method="RK45",
          max_step=2 * dt,
          events=event_list,
          dense_output=False)
```

Each call to `_integrate_phase` runs one phase and returns the time history for
that phase; phases are concatenated into a single trajectory.

---

### Terminal events

Instead of fixed burn-end times, phases end on **orbital conditions**:

| Phase | Terminal event | Trigger |
|---|---|---|
| Burn 1 | `_make_apogee_target_event(h_target)` | Instantaneous apogee altitude reaches target |
| Hohmann coast | `_make_apogee_reached_event()` | `vy` crosses zero going **negative** (top of arc) |
| Burn 2 | `_make_circular_event()` | `vx` reaches local circular speed `√(GM/r)` |

Upper-bound time limits are always set as well, so the integrator terminates
even if an event never fires (e.g., insufficient propellant to reach the target).

---

### Phase stitching

Each phase's output arrays are appended to running lists:
```
t_full   = [phase0_t, phase1_t, phase2_t, ...]
state_full = [phase0_y, phase1_y, ...]
phase_map  = {t_i: "vertical" | "gravity_turn" | "coast" | ...}
```

At each stage boundary the **state is explicitly corrected**:
- Mass is reset to the correct stage stack mass
- Fairing mass is subtracted at the jettison event

This prevents rounding errors or solver drift from mis-counting propellant.

---

### References

- [SciPy — `solve_ivp` documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html)
- [NASA — Numerical integration for trajectories](https://ntrs.nasa.gov/api/citations/20030000844/downloads/20030000844.pdf)
""")

    # ── Section 5: Orbital mechanics helpers ──────────────────────────────
    with s_orbital:
        st.markdown("""
## 5. Orbital Mechanics Helpers  ·  軌道力學輔助函式

---

### `_instantaneous_apogee_alt_m(state)`

Computes the apogee altitude of the **instantaneous Keplerian orbit** that matches
the current position and velocity.  Used as the trigger function for the Burn 1
terminal event.

**Algorithm:**

1. Specific orbital energy:
$$E = \\frac{v^2}{2} - \\frac{GM}{r}$$

2. If `E ≥ 0` → hyperbolic / escape trajectory → return large sentinel value.

3. Semi-major axis:
$$a = -\\frac{GM}{2E}$$

4. Specific angular momentum (using only the horizontal component, since `vx`
   is tangential in the local frame):
$$h = r \\cdot v_x$$

5. Eccentricity:
$$e = \\sqrt{\\max\\!\\left(0,\\; 1 - \\frac{h^2}{a \\cdot GM}\\right)}$$

6. Apogee altitude:
$$r_{\\text{apo}} = a(1 + e) - R_{\\oplus}$$

> This function is called *inside* `solve_ivp`'s event callbacks, so it must be
> fast — pure Python / NumPy arithmetic, no iterative solvers.

---

### Event factory functions

| Function | Returns event that fires when… | Direction |
|---|---|---|
| `_make_apogee_target_event(h_target_m)` | `apogee_alt − h_target` crosses **zero upward** | +1 (rising) |
| `_make_apogee_reached_event()` | `vy` crosses **zero going negative** | −1 (falling) |
| `_make_circular_event()` | `vx − v_circ(r)` crosses **zero going positive** | +1 (rising) |

All three are **terminal** (`event.terminal = True`), so the integrator stops
immediately when they fire rather than continuing to the time bound.

---

### Vis-viva equation used in guidance

The target tangential speed at the **perigee** of the Hohmann transfer ellipse:

$$v_{\\text{perigee}} = \\sqrt{GM \\left(\\frac{2}{r_{\\text{perigee}}} - \\frac{1}{a_{\\text{transfer}}}\\right)},
\\quad a_{\\text{transfer}} = \\frac{r_{\\text{perigee}} + r_{\\text{apogee}}}{2}$$

This is the speed `vx` must reach at the end of Burn 1 to place the apogee
exactly at the target altitude.

---

### References

- [Orbital Mechanics Space — Hohmann transfer](https://orbital-mechanics.space/orbital-maneuvers/hohmann-transfer.html)
- [Wikipedia — Hohmann transfer orbit](https://en.wikipedia.org/wiki/Hohmann_transfer_orbit)
- [Wikipedia — Vis-viva equation](https://en.wikipedia.org/wiki/Vis-viva_equation)
- [DAMTP Cambridge — Two-body orbital mechanics](https://www.damtp.cam.ac.uk/user/tong/relativity/six.pdf)
""")

    # ── Section 6: Outputs & diagnostics ──────────────────────────────────
    with s_outputs:
        st.markdown("""
## 6. Outputs, Diagnostics, and Constraints  ·  輸出、診斷與限制檢查

---

### Per-timestep `TrajectoryPoint`

For each sampled time the solver produces:

| Field | Units | Description |
|---|---|---|
| `t_s` | s | Mission elapsed time |
| `altitude_m` | m | Altitude above Earth reference sphere |
| `downrange_m` | m | Downrange arc distance |
| `velocity_m_s` | m/s | Total speed `√(vx²+vy²)` |
| `vx_m_s`, `vy_m_s` | m/s | Tangential and radial velocity components |
| `mass_kg` | kg | Vehicle mass at this instant |
| `thrust_N` | N | Total thrust magnitude |
| `drag_N` | N | Total drag magnitude |
| `dynamic_pressure_Pa` | Pa | `½ρv²` |
| `accel_g` | g | Scalar net acceleration `|T−D−mg|/(m g₀)` |
| `phase` | string | Phase label (see colour legend) |

---

### Global `TrajectoryResult`

Scalar summary fields:

| Field | Description |
|---|---|
| `max_q_Pa`, `max_q_time_s`, `max_q_altitude_m` | Peak dynamic pressure and its location |
| `max_accel_g` | Peak g-loading (structural / crew limit) |
| `burnout_velocity_m_s`, `burnout_altitude_m` | Final state after Burn 2 |
| `target_velocity_m_s` | Circular-orbit speed at mission target altitude: `√(GM/r_target)` |
| `achieved_velocity_m_s` | Actual final speed |
| `orbit_achieved` | Boolean — see criteria below |
| `integrated_delta_v_m_s` | Cumulative `|Δv|` via trapezoidal speed-change integration |
| `warnings` | List of human-readable warning strings |

---

### `orbit_achieved` criteria

```
orbit_achieved = (
    burnout_altitude_m  ≥  80 000 m                  # cleared atmosphere
    AND
    0.97 × v_circ(r_burnout)  ≤  v_burnout  ≤  v_esc(r_burnout)
)
```

The 3% tolerance on `v_circ` accounts for realistic GNC residuals; a real vehicle
would correct the error with a trim burn.

---

### Warning strings emitted

| Condition | Warning text |
|---|---|
| `alt_burnout < 80 km` | "Final altitude below atmosphere — orbit not achieved" |
| `v_burnout < 0.97 v_circ` | "Burnout velocity X m/s below circular speed Y m/s at burnout altitude" |
| `alt_burnout < 0.85 × target` | "Burnout altitude Z km is below 85% of target A km" |
| `max_q > q_limit` | "Max-Q B kPa exceeds configured limit C kPa" |
| `peak_g > g_limit` | "Peak acceleration D g exceeds limit E g" |

---

### References

- [Wikipedia — Max Q](https://en.wikipedia.org/wiki/Max_q)
- [Mars Society — Max-Q explainer](https://www.marssociety.ca/2021/05/13/max-q-and-bernoullis-principle/)
- [NASA — Trajectory outputs](https://ntrs.nasa.gov/api/citations/20030000844/downloads/20030000844.pdf)
""")

    # ── Section 7: Key design themes ──────────────────────────────────────
    with s_design:
        st.markdown("""
## 7. Key Design Themes  ·  核心設計理念

---

### Theme 1 — Physically consistent 2-D dynamics  物理自洽的二維動力學

The equations of motion include **both** the centrifugal term (`+vx²/r` in `ay`)
**and** the Coriolis coupling term (`−vy·vx/r` in `ax`).

Together they ensure:
- Circular orbital speed is self-sustaining (no thrust needed to maintain altitude)
- Angular momentum `h = r·vx` is exactly conserved during unthrusted arcs
- Hohmann transfer ellipses close correctly after a 44-minute coast

> Without these terms the simulation is valid only for short, near-vertical burns.
> For multi-orbit manoeuvres they are essential.

---

### Theme 2 — Event-driven staging & burns  事件驅動的分節與燃燒

Phases end on **orbital conditions**, not preset times:

```
Burn 1 ends  →  when instantaneous apogee reaches target altitude
Coast ends   →  when vy passes through zero (apogee)
Burn 2 ends  →  when vx reaches local v_circ
```

Time-based upper bounds act as safeguards against propellant exhaustion or
off-nominal trajectories.  This makes the simulation **self-correcting**: a vehicle
with more or less propellant naturally burns for the right duration.

---

### Theme 3 — Practical launch-vehicle features  實用發射載具特性

The solver models three operational features seen on real vehicles:

| Feature | Implementation |
|---|---|
| **Max-Q throttle-down** | Stage 1 throttles to 72% between T+60 s and T+80 s |
| **Fairing jettison** | Fairing mass subtracted at `t_ses1 + Δt_fair` (mid Burn 1) |
| **Propellant bookkeeping** | Explicit mass resets at staging; propellant guards prevent over-burn |

---

### Theme 4 — Diagnostic-friendly output  診斷友善的輸出格式

Full time history + key scalar metrics (max-Q, peak g, burnout state, integrated Δv,
warnings) enable rapid validation of any configuration:

```
orbit=True  burnout alt=260.4 km  v=7752 m/s  (v_circ=7753 m/s, delta=-1 m/s)
Max-Q: 30.2 kPa at T+60 s / 9.6 km
stage2_burn1:  T+159 → T+560 s  alt 86→127 km  vx 1972→7854 m/s
coast2:        T+561 → T+3201 s  alt 127→260 km
stage2_burn2:  T+3211 → T+3212 s  alt 260 km  vx 7714→7752 m/s
Warnings: []
```

The `orbit_achieved` boolean plus the `warnings` list provide immediate pass/fail
feedback without manual inspection of the time history.

---

### Theme 5 — Real-world calibration  真實世界校驗

The baseline template (`template_falcon9_like.json`) was calibrated against
**NG-24 Cygnus** launch telemetry: satellite deployment was observed at **256 km**
altitude (T+14:47) in public launch footage.  With `payload=20 000 kg` and
`target=280 km`, the solver predicts a **260.4 km** parking orbit — a 1.7% error,
well within the modelling uncertainty of a two-degree-of-freedom simulation.

---

### References

- [DAMTP Cambridge — Rotating frame EOM](https://www.damtp.cam.ac.uk/user/tong/relativity/six.pdf)
- [Wikipedia — Hohmann transfer orbit](https://en.wikipedia.org/wiki/Hohmann_transfer_orbit)
- [NASA — Guidance, navigation, control](https://ntrs.nasa.gov/api/citations/20030000844/downloads/20030000844.pdf)
- [Reddit — Max-Q throttle-down](https://www.reddit.com/r/space/comments/jx6j6r/question_about_rockets_throttling_down_around_max/)
""")


# ---------------------------------------------------------------------------
# 3-D Globe — coordinate helpers
# ---------------------------------------------------------------------------

R_EARTH_KM = 6371.0

LAUNCH_SITES = {
    "🇺🇸 卡納維爾角 Cape Canaveral, FL":  (28.5,  -80.6,  90.0,  "Falcon 9 / Atlas V"),
    "🇺🇸 范登堡 Vandenberg SFB, CA":       (34.7, -120.6,  195.0, "Falcon 9 SSO"),
    "🇹🇼 旭海 Xuhai, Pingtung, Taiwan":    (22.0,  120.8,  98.0,  "Taiwan proposed site"),
    "🇯🇵 種子島 Tanegashima, Japan":        (30.4,  130.9,  90.0,  "H-IIA / H3"),
    "🇫🇷 庫魯 Kourou, French Guiana":      ( 5.2,  -52.8,  90.0,  "Ariane 6"),
    "🇨🇳 酒泉 Jiuquan, China":             (40.9,  100.3,  97.0,  "Long March"),
    "🇷🇺 拜科努爾 Baikonur, Kazakhstan":   (45.6,   63.3,  51.6,  "Soyuz / Proton"),
    "自訂 Custom …":                        (28.5,  -80.6,  90.0,  ""),
}

PHASE_COLORS = {
    "vertical":      "#FFD700",  # gold
    "gravity_turn":  "#FF8C00",  # orange
    "coast":         "#A0C8FF",  # light blue
    # Hohmann two-burn phases (physics solver)
    "stage2_burn1":  "#FF4500",  # red-orange  (same family as stage2)
    "coast2":        "#7EC8E3",  # sky blue    (Hohmann coast)
    "stage2_burn2":  "#FF6347",  # tomato      (circularisation burn)
    # Legacy single-burn label
    "stage2":        "#FF4500",  # red-orange
    "unknown":       "#CCCCCC",
}

PHASE_LABELS_ZH = {
    "vertical":      "垂直上升 Vertical",
    "gravity_turn":  "重力轉向 Gravity Turn",
    "coast":         "滑行段 Coast",
    "stage2_burn1":  "第二節燃燒1 S2 Burn 1",
    "coast2":        "霍曼滑行 Hohmann Coast",
    "stage2_burn2":  "第二節燃燒2 S2 Burn 2",
    "stage2":        "第二節燃燒 Stage 2 Burn",
}


def _latlon_to_xyz(lat_deg: float, lon_deg: float,
                   alt_km: float = 0.0) -> tuple:
    """Geodetic (lat, lon, alt) → Cartesian (x, y, z) in km."""
    r   = R_EARTH_KM + alt_km
    lat = np.radians(lat_deg)
    lon = np.radians(lon_deg)
    x   = r * np.cos(lat) * np.cos(lon)
    y   = r * np.cos(lat) * np.sin(lon)
    z   = r * np.sin(lat)
    return x, y, z


def _downrange_to_latlon(lat0_deg: float, lon0_deg: float,
                          az_deg: float, d_km: float) -> tuple:
    """
    Great-circle propagation: given launch point, azimuth, and downrange
    distance, return (lat, lon) in degrees.
    """
    d   = d_km / R_EARTH_KM          # angular distance [rad]
    lat0 = np.radians(lat0_deg)
    lon0 = np.radians(lon0_deg)
    az   = np.radians(az_deg)

    lat2 = np.arcsin(np.sin(lat0) * np.cos(d) +
                     np.cos(lat0) * np.sin(d) * np.cos(az))
    lon2 = lon0 + np.arctan2(np.sin(az) * np.sin(d) * np.cos(lat0),
                              np.cos(d) - np.sin(lat0) * np.sin(lat2))
    return np.degrees(lat2), np.degrees(lon2)


def _raan_from_launch(lat0_deg: float, lon0_deg: float,
                      az_deg: float) -> float:
    """
    Compute the RAAN (Right Ascension of Ascending Node) in degrees for
    an orbit launched from (lat0, lon0) with surface azimuth az_deg.

    Method (exact spherical geometry):
      r̂  = unit position vector of launch site in ECI
      v̂  = unit launch-velocity direction in ECI
            = cos(az)·n̂ + sin(az)·ê   (n̂ = north, ê = east)
      h   = r̂ × v̂   (angular momentum direction, unnormalised)
      N   = ẑ × h    (ascending-node vector)
      RAAN = atan2(N_y, N_x)

    The old approximation  raan ≈ lon - 90°  is only correct for
    due-east (az = 90°) launches.  For other azimuths the error can
    exceed 180°.
    """
    lat0 = np.radians(lat0_deg)
    lon0 = np.radians(lon0_deg)
    az   = np.radians(az_deg)

    r_hat = np.array([np.cos(lat0) * np.cos(lon0),
                      np.cos(lat0) * np.sin(lon0),
                      np.sin(lat0)])
    north = np.array([-np.sin(lat0) * np.cos(lon0),
                      -np.sin(lat0) * np.sin(lon0),
                       np.cos(lat0)])
    east  = np.array([-np.sin(lon0),  np.cos(lon0), 0.0])

    v_hat = np.cos(az) * north + np.sin(az) * east
    h = np.cross(r_hat, v_hat)
    N = np.cross(np.array([0.0, 0.0, 1.0]), h)   # ascending node vector
    return float(np.degrees(np.arctan2(N[1], N[0])))


def _orbit_ring_xyz(alt_km: float, inc_deg: float,
                    raan_deg: float) -> tuple:
    """
    Generate a full circular orbit ring in Cartesian km.
    inc_deg  = inclination from equator
    raan_deg = Right Ascension of Ascending Node (lon of ascending node)
    """
    R      = R_EARTH_KM + alt_km
    theta  = np.linspace(0, 2 * np.pi, 720)
    i      = np.radians(inc_deg)
    omega  = np.radians(raan_deg)

    # Orbit in perifocal frame, then rotate by inclination and RAAN
    xp = R * np.cos(theta)
    yp = R * np.sin(theta)

    # Rotate by inclination (around x-axis)
    xq = xp
    yq = yp * np.cos(i)
    zq = yp * np.sin(i)

    # Rotate by RAAN (around z-axis)
    xr = xq * np.cos(omega) - yq * np.sin(omega)
    yr = xq * np.sin(omega) + yq * np.cos(omega)
    zr = zq

    return xr, yr, zr


_GEO_PATH = os.path.join(os.path.dirname(__file__), "data", "geo", "world_boundaries.geojson")


@st.cache_data(show_spinner=False)
def _load_world_boundaries() -> list | None:
    """
    Load the World Administrative Boundaries GeoJSON.
    Returns the list of features, or None if the file is not found.
    The result is cached by Streamlit so the file is read only once per session.
    """
    if not os.path.isfile(_GEO_PATH):
        return None
    with open(_GEO_PATH, "r", encoding="utf-8") as fh:
        gj = json.load(fh)
    return gj.get("features", [])


def _country_boundary_traces() -> list:
    """
    Convert world-boundary polygons to a single batched Scatter3d trace
    (one trace for all exterior rings, None-separated) placed just above
    the Earth sphere so the lines are always visible.

    Elevation offset: 2 km above surface to clear the ocean mesh.
    """
    features = _load_world_boundaries()
    if not features:
        return []

    ELEV_KM = 2.0   # lift lines slightly above the sphere surface
    xs: list = []
    ys: list = []
    zs: list = []

    def _add_ring(ring):
        """Append one polygon ring (exterior only) to the coordinate lists."""
        for lon, lat in ring:
            x, y, z = _latlon_to_xyz(lat, lon, ELEV_KM)
            xs.append(x)
            ys.append(y)
            zs.append(z)
        # Close the ring visually and add a None break between polygons
        if ring:
            x, y, z = _latlon_to_xyz(ring[0][1], ring[0][0], ELEV_KM)
            xs.append(x)
            ys.append(y)
            zs.append(z)
        xs.append(None)
        ys.append(None)
        zs.append(None)

    for feat in features:
        geom = feat.get("geometry")
        if geom is None:
            continue
        gtype = geom["type"]
        coords = geom["coordinates"]
        if gtype == "Polygon":
            # coords[0] is the exterior ring
            _add_ring(coords[0])
        elif gtype == "MultiPolygon":
            for polygon in coords:
                _add_ring(polygon[0])

    if not xs:
        return []

    return [go.Scatter3d(
        x=xs, y=ys, z=zs,
        mode="lines",
        line=dict(color="rgba(210, 230, 255, 0.55)", width=1),
        showlegend=True,
        legendgroup="boundaries",
        name="國界 Country Borders",
        hoverinfo="skip",
    )]


def _earth_surface_traces() -> list:
    """Return Plotly traces for the Earth sphere + lat/lon grid."""
    traces = []

    # ---- Ocean sphere ----
    N  = 72
    u  = np.linspace(0, 2 * np.pi, N)
    v  = np.linspace(0, np.pi,     N)
    xs = R_EARTH_KM * np.outer(np.cos(u), np.sin(v))
    ys = R_EARTH_KM * np.outer(np.sin(u), np.sin(v))
    zs = R_EARTH_KM * np.outer(np.ones(N), np.cos(v))

    traces.append(go.Surface(
        x=xs, y=ys, z=zs,
        colorscale=[[0.0, "#0a2a5e"],
                    [0.4, "#0d3d7a"],
                    [0.7, "#1565a8"],
                    [1.0, "#1a80d0"]],
        showscale=False,
        opacity=1.0,
        lighting=dict(ambient=0.55, diffuse=0.85,
                      specular=0.15, roughness=0.7),
        lightposition=dict(x=2, y=2, z=2),
        name="Earth 地球",
        hoverinfo="skip",
    ))

    # ---- Latitude circles every 30° ----
    for lat_deg in range(-60, 90, 30):
        lat = np.radians(lat_deg)
        lons = np.linspace(0, 2 * np.pi, 180)
        r    = R_EARTH_KM * np.cos(lat)
        xg   = r * np.cos(lons)
        yg   = r * np.sin(lons)
        zg   = np.full_like(lons, R_EARTH_KM * np.sin(lat))
        traces.append(go.Scatter3d(
            x=xg, y=yg, z=zg,
            mode="lines",
            line=dict(color="rgba(100,160,220,0.30)", width=1),
            showlegend=False,
            hoverinfo="skip",
            name=f"lat{lat_deg}",
        ))

    # ---- Longitude meridians every 30° ----
    for lon_deg in range(0, 360, 30):
        lon  = np.radians(lon_deg)
        lats = np.linspace(-np.pi / 2, np.pi / 2, 90)
        xg   = R_EARTH_KM * np.cos(lats) * np.cos(lon)
        yg   = R_EARTH_KM * np.cos(lats) * np.sin(lon)
        zg   = R_EARTH_KM * np.sin(lats)
        traces.append(go.Scatter3d(
            x=xg, y=yg, z=zg,
            mode="lines",
            line=dict(color="rgba(100,160,220,0.25)", width=1),
            showlegend=False,
            hoverinfo="skip",
            name=f"lon{lon_deg}",
        ))

    # ---- Equator (highlighted) ----
    lons_eq = np.linspace(0, 2 * np.pi, 360)
    traces.append(go.Scatter3d(
        x=R_EARTH_KM * np.cos(lons_eq),
        y=R_EARTH_KM * np.sin(lons_eq),
        z=np.zeros(360),
        mode="lines",
        line=dict(color="rgba(100,200,255,0.45)", width=1.5),
        showlegend=False, hoverinfo="skip",
        name="equator",
    ))

    # ---- World administrative boundaries ----
    traces.extend(_country_boundary_traces())

    return traces


def chart_trajectory_globe(
    traj_points: list,
    target_alt_km: float,
    launch_lat: float,
    launch_lon: float,
    azimuth_deg: float,
    inclination_deg: float,
) -> go.Figure:
    """
    Build the 3-D globe figure with:
      • Earth sphere + grid lines
      • Rocket ascent trajectory (colour-coded by phase)
      • Target orbit ring
      • Launch site, MECO, staging, SECO markers
    """
    fig = go.Figure()

    # ── Earth ─────────────────────────────────────────────────────────────
    for trace in _earth_surface_traces():
        fig.add_trace(trace)

    # ── Launch site ───────────────────────────────────────────────────────
    lx, ly, lz = _latlon_to_xyz(launch_lat, launch_lon, 0)
    fig.add_trace(go.Scatter3d(
        x=[lx], y=[ly], z=[lz],
        mode="markers+text",
        marker=dict(size=7, color="#FF6B35", symbol="circle"),
        text=["🚀 Launch"],
        textposition="top center",
        textfont=dict(color="#FF6B35", size=11),
        name="Launch Site 發射場",
        hovertemplate=(f"Launch Site<br>Lat: {launch_lat:.1f}°  "
                       f"Lon: {launch_lon:.1f}°<extra></extra>"),
    ))

    # ── Ascent trajectory (per-phase colouring) ───────────────────────────
    if traj_points:
        # Group consecutive points by phase
        phase_segments: dict = {}
        for pt in traj_points:
            ph = pt.get("phase", "unknown")
            if ph not in phase_segments:
                phase_segments[ph] = {"dr": [], "alt": [], "t": [], "v": []}
            seg = phase_segments[ph]
            seg["dr"].append(pt.get("downrange_km", 0))
            seg["alt"].append(pt.get("altitude_km", 0))
            seg["t"].append(pt.get("t_s", 0))
            seg["v"].append(pt.get("velocity_m_s", 0))

        for ph, seg in phase_segments.items():
            xs, ys, zs, hovers = [], [], [], []
            for dr, alt, t, v in zip(seg["dr"], seg["alt"], seg["t"], seg["v"]):
                lat, lon = _downrange_to_latlon(
                    launch_lat, launch_lon, azimuth_deg, dr)
                x, y, z = _latlon_to_xyz(lat, lon, alt)
                xs.append(x); ys.append(y); zs.append(z)
                hovers.append(
                    f"Phase: {PHASE_LABELS_ZH.get(ph, ph)}<br>"
                    f"T+{t:.0f} s<br>"
                    f"Alt: {alt:.1f} km<br>"
                    f"Downrange: {dr:.1f} km<br>"
                    f"Velocity: {v:.0f} m/s"
                )

            fig.add_trace(go.Scatter3d(
                x=xs, y=ys, z=zs,
                mode="lines",
                line=dict(color=PHASE_COLORS.get(ph, "#ffffff"), width=4),
                name=PHASE_LABELS_ZH.get(ph, ph),
                hovertemplate="%{customdata}<extra></extra>",
                customdata=hovers,
            ))

        # ── Key event markers ──────────────────────────────────────────────
        def _marker(pt_data: dict, label: str, color: str, symbol: str) -> None:
            dr  = pt_data.get("downrange_km", 0)
            alt = pt_data.get("altitude_km", 0)
            t   = pt_data.get("t_s", 0)
            v   = pt_data.get("velocity_m_s", 0)
            lat, lon = _downrange_to_latlon(launch_lat, launch_lon, azimuth_deg, dr)
            x, y, z = _latlon_to_xyz(lat, lon, alt)
            fig.add_trace(go.Scatter3d(
                x=[x], y=[y], z=[z],
                mode="markers+text",
                marker=dict(size=8, color=color, symbol=symbol,
                            line=dict(width=1.5, color="#fff")),
                text=[label],
                textposition="top center",
                textfont=dict(color=color, size=10),
                name=label,
                hovertemplate=(
                    f"{label}<br>T+{t:.0f} s<br>"
                    f"Alt: {alt:.1f} km<br>V: {v:.0f} m/s<extra></extra>"
                ),
            ))

        # Find phase transition points
        prev_phase = None
        meco_pt = stage_sep_pt = seco_pt = None
        for pt in traj_points:
            ph = pt.get("phase", "unknown")
            if prev_phase == "gravity_turn" and ph == "coast":
                meco_pt = pt
            elif prev_phase == "coast" and ph == "stage2":
                stage_sep_pt = pt
            prev_phase = ph
        if traj_points:
            seco_pt = traj_points[-1]

        if meco_pt:
            _marker(meco_pt, "MECO", "#FFD700", "diamond")
        if stage_sep_pt:
            _marker(stage_sep_pt, "Staging\n分節", "#00CED1", "square")
        if seco_pt:
            _marker(seco_pt, "SECO\n入軌", "#2ECC71", "circle")

    # ── Target orbit ring ─────────────────────────────────────────────────
    # RAAN is derived exactly from the launch site position and azimuth.
    raan = _raan_from_launch(launch_lat, launch_lon, azimuth_deg)
    xo, yo, zo = _orbit_ring_xyz(target_alt_km, inclination_deg, raan)

    fig.add_trace(go.Scatter3d(
        x=xo, y=yo, z=zo,
        mode="lines",
        line=dict(color="#2ECC71", width=2.5, dash="dot"),
        name=f"目標軌道 Target Orbit ({target_alt_km:.0f} km, {inclination_deg:.1f}°)",
        hovertemplate=(f"Target Orbit 目標軌道<br>"
                       f"Alt: {target_alt_km:.0f} km<br>"
                       f"Inclination: {inclination_deg:.1f}°<extra></extra>"),
    ))

    # ── Layout ────────────────────────────────────────────────────────────
    axis_style = dict(
        showbackground=False, showgrid=False,
        zeroline=False, showticklabels=False,
        title="",
    )
    fig.update_layout(
        title=dict(
            text=(f"🌍 火箭軌跡模擬  Rocket Trajectory Simulation<br>"
                  f"<sup>目標軌道 Target: {target_alt_km:.0f} km  "
                  f"傾角 Inclination: {inclination_deg:.1f}°  "
                  f"發射方位角 Azimuth: {azimuth_deg:.1f}°</sup>"),
            font=dict(size=15, color="#ddd"),
        ),
        scene=dict(
            xaxis=axis_style,
            yaxis=axis_style,
            zaxis=axis_style,
            bgcolor="#05070f",
            camera=dict(
                eye=dict(x=1.4, y=1.2, z=0.6),
                up=dict(x=0, y=0, z=1),
            ),
            aspectmode="data",
        ),
        paper_bgcolor="#05070f",
        margin=dict(l=0, r=0, t=70, b=0),
        legend=dict(
            font=dict(size=11, color="#ccc"),
            bgcolor="rgba(5,7,15,0.7)",
            bordercolor="#333",
            borderwidth=1,
            x=0.01, y=0.99,
        ),
        height=680,
        font=dict(color="#ccc"),
    )
    return fig


# ---------------------------------------------------------------------------
# 3-D Globe — animated launch
# ---------------------------------------------------------------------------

def chart_trajectory_globe_animated(
    traj_points: list,
    target_alt_km: float,
    launch_lat: float,
    launch_lon: float,
    azimuth_deg: float,
    inclination_deg: float,
    time_step_s: int = 30,
    frame_duration_ms: int = 80,
) -> go.Figure:
    """
    Build an animated 3-D globe figure that plays back the rocket launch
    frame-by-frame.

    Each Plotly animation frame advances by *time_step_s* seconds of
    simulated flight time.  The browser Play/Pause button controls
    playback; the timeline slider lets the user scrub to any instant.

    Static traces  (built once, never updated by frames):
      • Earth sphere + lat/lon grid + country boundaries
      • Launch-site marker
      • Target orbit ring
      • Ghost full trajectory (dim) — orientation guide

    Animated traces  (two traces, updated every frame):
      • Trail  — growing colour-coded line from launch to current position
      • Rocket — bright marker at the current position with hover info

    Frame data is O(N_frames²/2) coordinates, which stays small even for
    long missions because we sample the trajectory at *time_step_s* intervals
    rather than storing every raw solver point in every frame.
    """
    fig = go.Figure()

    # ── Static: Earth + grid + boundaries ─────────────────────────────────
    for trace in _earth_surface_traces():
        fig.add_trace(trace)

    # ── Static: Launch site ───────────────────────────────────────────────
    lx, ly, lz = _latlon_to_xyz(launch_lat, launch_lon, 0)
    fig.add_trace(go.Scatter3d(
        x=[lx], y=[ly], z=[lz],
        mode="markers+text",
        marker=dict(size=8, color="#FF6B35", symbol="circle"),
        text=["🚀"],
        textposition="top center",
        textfont=dict(color="#FF6B35", size=13),
        name="Launch Site 發射場",
        hovertemplate=(f"Launch Site<br>"
                       f"Lat: {launch_lat:.1f}°  Lon: {launch_lon:.1f}°"
                       "<extra></extra>"),
    ))

    # ── Static: Target orbit ring ─────────────────────────────────────────
    raan = _raan_from_launch(launch_lat, launch_lon, azimuth_deg)
    xo, yo, zo = _orbit_ring_xyz(target_alt_km, inclination_deg, raan)
    fig.add_trace(go.Scatter3d(
        x=xo, y=yo, z=zo,
        mode="lines",
        line=dict(color="#2ECC71", width=2, dash="dot"),
        name=f"目標軌道 Target Orbit ({target_alt_km:.0f} km)",
        hoverinfo="skip",
    ))

    # ── Static: Ghost full trajectory (dim background path) ───────────────
    if traj_points:
        gx, gy, gz = [], [], []
        for pt in traj_points:
            lat, lon = _downrange_to_latlon(
                launch_lat, launch_lon, azimuth_deg, pt.get("downrange_km", 0))
            x, y, z = _latlon_to_xyz(lat, lon, pt.get("altitude_km", 0))
            gx.append(x); gy.append(y); gz.append(z)
        fig.add_trace(go.Scatter3d(
            x=gx, y=gy, z=gz,
            mode="lines",
            line=dict(color="rgba(200,200,200,0.15)", width=1.5),
            showlegend=False,
            hoverinfo="skip",
            name="_ghost",
        ))

    # ── Animated trace placeholders (filled by frames) ────────────────────
    n_static = len(fig.data)   # index of first animated trace

    fig.add_trace(go.Scatter3d(      # index n_static   → trail
        x=[], y=[], z=[],
        mode="lines",
        line=dict(color="#FFD700", width=3),
        name="軌跡 Trail",
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter3d(      # index n_static+1 → rocket marker
        x=[], y=[], z=[],
        mode="markers+text",
        marker=dict(size=11, color="#FFD700", symbol="circle",
                    line=dict(color="white", width=1.5)),
        text=["🚀"],
        textposition="top center",
        textfont=dict(color="white", size=11),
        name="火箭 Rocket",
        hovertemplate=(
            "T+%{customdata[0]:.0f} s<br>"
            "Alt: %{customdata[1]:.1f} km<br>"
            "V: %{customdata[2]:.0f} m/s<br>"
            "Phase: %{customdata[3]}<extra></extra>"
        ),
    ))

    trail_idx  = n_static
    rocket_idx = n_static + 1

    if not traj_points:
        return fig

    # ── Sample trajectory at time_step_s boundaries ───────────────────────
    # Build a sorted list of (t, index) so we can binary-search for nearest
    t_arr = [pt["t_s"] for pt in traj_points]
    t_max = t_arr[-1]

    sample_times = list(range(0, int(t_max) + time_step_s, time_step_s))

    def _nearest_idx(target_t: float) -> int:
        """Return the index of the last point with t_s <= target_t."""
        lo, hi = 0, len(t_arr) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if t_arr[mid] <= target_t:
                lo = mid
            else:
                hi = mid - 1
        return lo

    frame_indices = [_nearest_idx(t) for t in sample_times]

    # Pre-compute XYZ for every sampled point (done once, reused across frames)
    sampled_xyz: list[tuple] = []
    sampled_pts: list[dict]  = []
    for idx in frame_indices:
        pt  = traj_points[idx]
        lat, lon = _downrange_to_latlon(
            launch_lat, launch_lon, azimuth_deg, pt.get("downrange_km", 0))
        x, y, z = _latlon_to_xyz(lat, lon, pt.get("altitude_km", 0))
        sampled_xyz.append((x, y, z))
        sampled_pts.append(pt)

    # ── Build Plotly frames ────────────────────────────────────────────────
    frames: list[go.Frame] = []
    for i, (pt, xyz) in enumerate(zip(sampled_pts, sampled_xyz)):
        phase       = pt.get("phase", "unknown")
        phase_color = PHASE_COLORS.get(phase, PHASE_COLORS["unknown"])
        t_s   = pt.get("t_s", 0)
        alt   = pt.get("altitude_km", 0)
        v     = pt.get("velocity_m_s", 0)
        label = PHASE_LABELS_ZH.get(phase, phase)

        # Trail: all sampled XYZ from frame 0 up to and including frame i
        trail_xs = [p[0] for p in sampled_xyz[:i + 1]]
        trail_ys = [p[1] for p in sampled_xyz[:i + 1]]
        trail_zs = [p[2] for p in sampled_xyz[:i + 1]]

        frames.append(go.Frame(
            name=f"T+{t_s:.0f}s",
            traces=[trail_idx, rocket_idx],
            data=[
                go.Scatter3d(
                    x=trail_xs, y=trail_ys, z=trail_zs,
                    mode="lines",
                    line=dict(color=phase_color, width=3),
                ),
                go.Scatter3d(
                    x=[xyz[0]], y=[xyz[1]], z=[xyz[2]],
                    mode="markers+text",
                    marker=dict(size=11, color=phase_color, symbol="circle",
                                line=dict(color="white", width=1.5)),
                    text=["🚀"],
                    textposition="top center",
                    textfont=dict(color="white", size=11),
                    customdata=[[t_s, alt, v, label]],
                ),
            ],
        ))

    fig.frames = frames

    # ── Plotly animation controls ──────────────────────────────────────────
    frame_names = [f.name for f in frames]
    n_frames    = len(frames)

    # Determine a reasonable label interval so the slider isn't too crowded
    label_every = max(1, n_frames // 20)

    slider_steps = [
        dict(
            args=[[name], dict(
                frame=dict(duration=frame_duration_ms, redraw=True),
                mode="immediate",
                transition=dict(duration=0),
            )],
            label=name if i % label_every == 0 else "",
            method="animate",
        )
        for i, name in enumerate(frame_names)
    ]

    sliders = [dict(
        active=0,
        currentvalue=dict(
            font=dict(size=12, color="#ddd"),
            prefix="  ",
            visible=True,
            xanchor="left",
        ),
        pad=dict(b=10, t=35),
        len=0.90, x=0.05, y=0,
        steps=slider_steps,
        bgcolor="rgba(20,20,50,0.85)",
        bordercolor="#445",
        font=dict(color="#aaa", size=9),
        tickcolor="#555",
    )]

    updatemenus = [dict(
        type="buttons",
        showactive=False,
        y=-0.06, x=0.0,
        xanchor="left", yanchor="bottom",
        pad=dict(l=5, r=5, t=5),
        bgcolor="rgba(20,20,50,0.9)",
        bordercolor="#445",
        font=dict(color="#ddd", size=12),
        buttons=[
            dict(
                label="▶  播放 Play",
                method="animate",
                args=[None, dict(
                    frame=dict(duration=frame_duration_ms, redraw=True),
                    fromcurrent=True,
                    transition=dict(duration=0),
                )],
            ),
            dict(
                label="⏸  暫停 Pause",
                method="animate",
                args=[[None], dict(
                    frame=dict(duration=0, redraw=False),
                    mode="immediate",
                    transition=dict(duration=0),
                )],
            ),
            dict(
                label="⏮  重置 Reset",
                method="animate",
                args=[[frame_names[0]], dict(
                    frame=dict(duration=0, redraw=True),
                    mode="immediate",
                    transition=dict(duration=0),
                )],
            ),
        ],
    )]

    # ── Layout ────────────────────────────────────────────────────────────
    axis_style = dict(showbackground=False, showgrid=False,
                      zeroline=False, showticklabels=False, title="")
    fig.update_layout(
        title=dict(
            text=(f"🚀 火箭升空動畫  Launch Animation<br>"
                  f"<sup>步長 Step: {time_step_s} s / 幀  "
                  f"速度 Speed: {frame_duration_ms} ms/frame  "
                  f"幀數 Frames: {n_frames}  "
                  f"目標 Target: {target_alt_km:.0f} km  "
                  f"方位角 Az: {azimuth_deg:.0f}°</sup>"),
            font=dict(size=13, color="#ddd"),
        ),
        scene=dict(
            xaxis=axis_style, yaxis=axis_style, zaxis=axis_style,
            bgcolor="#05070f",
            camera=dict(eye=dict(x=1.4, y=1.2, z=0.6),
                        up=dict(x=0, y=0, z=1)),
            aspectmode="data",
        ),
        updatemenus=updatemenus,
        sliders=sliders,
        paper_bgcolor="#05070f",
        height=730,
        margin=dict(l=0, r=0, t=70, b=110),
        legend=dict(font=dict(size=11, color="#ccc"),
                    bgcolor="rgba(5,7,15,0.7)",
                    bordercolor="#333", borderwidth=1,
                    x=0.01, y=0.99),
        font=dict(color="#ccc"),
    )

    return fig


# ---------------------------------------------------------------------------
# Local trajectory computation (no API call required)
# ---------------------------------------------------------------------------

def _build_vehicle_from_dict(baseline: dict, target_alt_km: float):
    """
    Construct a rocket_core Vehicle domain model from the API-schema baseline dict.
    """
    from rocket_core.vehicle.models import (
        Engine, Stage, Mission, Propellant, SimulationConfig, Vehicle
    )

    def _eng(d: dict) -> Engine:
        e = d["engine"]
        return Engine(
            name=e["name"],
            thrust_sl=e["thrust_sl"],
            thrust_vac=e["thrust_vac"],
            isp_sl=e["isp_sl"],
            isp_vac=e["isp_vac"],
            mass=e["mass"],
        )

    def _stage(d: dict) -> Stage:
        return Stage(
            dry_mass=d["dry_mass"],
            prop_mass=d["prop_mass"],
            engine=_eng(d),
            engine_count=d["engine_count"],
            diameter_m=d["diameter_m"],
        )

    prop_d = baseline.get("propellant", {})
    mis_d  = baseline.get("mission", {})
    cfg_d  = baseline.get("sim_config", {})

    return Vehicle(
        stage1=_stage(baseline["stage1"]),
        stage2=_stage(baseline["stage2"]),
        payload_mass=baseline["payload_mass"],
        fairing_mass=baseline.get("fairing_mass", 1900),
        propellant=Propellant(
            fuel_name=str(prop_d.get("fuel", "RP-1")),
            oxidizer_name=str(prop_d.get("oxidiser", "LOX")),
            mixture_ratio=float(prop_d.get("mixture_ratio", 2.36)),
        ),
        mission=Mission(
            target_altitude_km=target_alt_km,
            reusable_booster=bool(mis_d.get("reusable_booster", False)),
            reusable_penalty_kg=float(mis_d.get("reusable_penalty_kg", 0)),
            required_delta_v_m_s=mis_d.get("required_delta_v_m_s"),
        ),
        sim_config=SimulationConfig(
            gravity_loss_estimate_m_s=float(cfg_d.get("gravity_loss_estimate_m_s", 1200)),
            dt_s=1.0,   # 1-second steps: fast enough, smooth enough for display
        ),
    )


def _compute_physics_trajectory(
    baseline: dict,
    target_alt_km: float,
    site_lat: float,
    site_lon: float,
    azimuth_deg: float,
):
    """
    Run the real 3-DOF gravity-turn ODE simulation (rocket_core solver, no API).

    Equations of motion integrated:
      - Thrust along velocity vector (gravity-turn guidance)
      - Gravity: inverse-square, Earth-centred
      - Drag: ½ ρ v² Cd A_ref   (exponential atmosphere)
      - Four phases: vertical rise → gravity turn → coast → Stage-2 burn

    Returns (points, stats) compatible with chart_trajectory_globe().
    Falls back to a simplified model if the solver is unavailable.
    """
    try:
        from rocket_core.trajectory.solver import simulate_trajectory
    except ImportError as exc:
        st.warning(f"rocket_core 無法載入，改用簡化模型。Cannot import: {exc}")
        return _compute_fallback_trajectory(baseline, target_alt_km, site_lat, site_lon, azimuth_deg)

    try:
        vehicle = _build_vehicle_from_dict(baseline, target_alt_km)
    except Exception as exc:
        st.warning(f"載具模型建立失敗，改用簡化模型。Vehicle build failed: {exc}")
        return _compute_fallback_trajectory(baseline, target_alt_km, site_lat, site_lon, azimuth_deg)

    try:
        result = simulate_trajectory(vehicle)
    except Exception as exc:
        st.warning(f"軌跡求解失敗，改用簡化模型。Solver error: {exc}")
        return _compute_fallback_trajectory(baseline, target_alt_km, site_lat, site_lon, azimuth_deg)

    # ── Convert TrajectoryPoint list → chart-compatible dicts ─────────────
    points = [
        {
            "t_s":          p.t_s,
            "altitude_km":  round(p.altitude_m  / 1_000.0, 2),
            "downrange_km": round(p.downrange_m / 1_000.0, 1),
            "velocity_m_s": p.velocity_m_s,
            "mass_kg":      p.mass_kg,
            "phase":        p.phase,
        }
        for p in result.timeline
    ]

    # ── Find MECO time (gravity_turn → coast transition) ───────────────────
    t_meco = 0.0
    prev_ph = None
    for p in result.timeline:
        if prev_ph == "gravity_turn" and p.phase == "coast":
            t_meco = p.t_s
            break
        prev_ph = p.phase

    t_seco = result.timeline[-1].t_s if result.timeline else 0.0
    dr_seco = result.timeline[-1].downrange_m / 1_000.0 if result.timeline else 0.0

    stats = {
        "t_meco_s":             round(t_meco, 0),
        "t_seco_s":             round(t_seco, 0),
        "target_alt_km":        target_alt_km,
        "orbital_velocity_m_s": round(result.target_velocity_m_s, 0),
        "downrange_km":         round(dr_seco, 0),
        "max_q_alt_km":         round(result.max_q_altitude_m / 1_000.0, 1),
        "max_q_kPa":            round(result.max_q_Pa / 1_000.0, 1),
        "max_q_time_s":         round(result.max_q_time_s, 0),
        "burnout_velocity_m_s": round(result.burnout_velocity_m_s, 0),
        "burnout_alt_km":       round(result.burnout_altitude_m / 1_000.0, 1),
        "orbit_achieved":       result.orbit_achieved,
        "integrated_dv_m_s":    round(result.integrated_delta_v_m_s, 0),
        "warnings":             result.warnings,
        "physics_based":        True,
    }

    return points, stats


def _compute_fallback_trajectory(
    baseline: dict,
    target_alt_km: float,
    site_lat: float,
    site_lon: float,
    azimuth_deg: float,
):
    """
    Fallback: simplified kinematic profile used only when rocket_core is unavailable.
    NOTE: This is a smooth interpolation for display only — NOT a physics simulation.
    """
    import math as _math

    g0  = 9.80665
    GM  = 3.986_004_418e14
    R_E = R_EARTH_KM * 1_000.0

    s1 = baseline["stage1"]
    s2 = baseline["stage2"]

    thrust1 = s1["engine"]["thrust_sl"] * s1["engine_count"]
    mdot1   = thrust1 / (s1["engine"]["isp_sl"] * g0)
    t_meco  = s1["prop_mass"] / mdot1
    thrust2 = s2["engine"]["thrust_vac"] * s2["engine_count"]
    mdot2   = thrust2 / (s2["engine"]["isp_vac"] * g0)
    t_ses1  = t_meco + 10.0
    t_seco  = t_ses1 + s2["prop_mass"] / mdot2
    v_circ  = _math.sqrt(GM / (R_E + target_alt_km * 1_000.0))
    dr_total = 1_600.0 * _math.sqrt(target_alt_km / 400.0)

    t_vert = 30.0
    alt_vert = 1.5
    alt_meco = target_alt_km * 0.60
    alt_ses1 = alt_meco * 0.98
    dr_meco  = dr_total * 0.22
    dr_ses1  = dr_meco + dr_total * 0.015

    def _ss(x):
        x = max(0.0, min(1.0, x))
        return x * x * (3.0 - 2.0 * x)

    N = 200
    points = []
    for i in range(N + 1):
        t = i * t_seco / N
        if t <= t_vert:
            s = _ss(t / t_vert)
            alt, dr, v, phase = alt_vert * s, 0.02 * s, v_circ * 0.02 * s, "vertical"
        elif t <= t_meco:
            s = _ss((t - t_vert) / (t_meco - t_vert))
            alt  = alt_vert + (alt_meco - alt_vert) * s
            dr   = dr_meco * s
            v    = v_circ * 0.18 * s
            phase = "gravity_turn"
        elif t <= t_ses1:
            frac = (t - t_meco) / (t_ses1 - t_meco)
            alt  = alt_meco - (alt_meco - alt_ses1) * frac
            dr   = dr_meco + (dr_ses1 - dr_meco) * frac
            v    = v_circ * 0.18
            phase = "coast"
        else:
            s = _ss((t - t_ses1) / (t_seco - t_ses1))
            alt  = alt_ses1 + (target_alt_km - alt_ses1) * s
            dr   = dr_ses1  + (dr_total - dr_ses1) * s
            v    = v_circ * (0.18 + 0.82 * s)
            phase = "stage2"
        points.append({"t_s": round(t, 1), "altitude_km": round(alt, 2),
                        "downrange_km": round(dr, 1), "velocity_m_s": round(v, 0),
                        "mass_kg": 0, "phase": phase})

    stats = {
        "t_meco_s": round(t_meco, 0), "t_seco_s": round(t_seco, 0),
        "target_alt_km": target_alt_km,
        "orbital_velocity_m_s": round(v_circ, 0),
        "downrange_km": round(dr_total, 0),
        "max_q_alt_km": 12.0, "max_q_kPa": None,
        "max_q_time_s": None, "burnout_velocity_m_s": round(v_circ, 0),
        "burnout_alt_km": target_alt_km, "orbit_achieved": None,
        "integrated_dv_m_s": None, "warnings": ["⚠️ 使用簡化顯示模型 Using simplified display model — not physics-based"],
        "physics_based": False,
    }

    return points, stats


# ---------------------------------------------------------------------------
# Tab 6: Engine Library — helpers
# ---------------------------------------------------------------------------

_ENGINE_LIB_PATH = os.path.join(
    os.path.dirname(__file__), "data", "engines", "engine_library.json"
)


@st.cache_data(show_spinner=False)
def _load_engine_library() -> dict:
    with open(_ENGINE_LIB_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _engine_to_sim_dict(eng: dict) -> dict:
    """Convert an engine-library entry to the simulator's engine sub-dict."""
    return {
        "name":       eng["name"] + " " + eng["variant"],
        "thrust_sl":  float(eng["thrust_sl_N"]),
        "thrust_vac": float(eng["thrust_vac_N"]),
        "isp_sl":     float(eng["isp_sl_s"]),
        "isp_vac":    float(eng["isp_vac_s"]),
        "mass":       float(eng["mass_kg"]),
    }


def _engine_performance_calc(
    eng: dict,
    stage_dry_kg: float,
    stage_prop_kg: float,
    payload_kg: float,
    engine_count: int,
    use_vac_isp: bool,
) -> dict:
    """
    Compute key performance metrics for a stage fitted with *engine_count*
    copies of *eng*.

    Returns a dict with: dv_m_s, twr_liftoff, burn_time_s, mdot_total,
    total_thrust_N, gross_mass_kg, burnout_mass_kg.
    """
    import math as _math
    G0 = 9.80665

    isp      = eng["isp_vac_s"] if use_vac_isp else eng["isp_sl_s"]
    t_sl     = eng["thrust_sl_N"]  * engine_count
    t_vac    = eng["thrust_vac_N"] * engine_count
    thrust   = t_vac if use_vac_isp else t_sl

    eng_mass_total = eng["mass_kg"] * engine_count
    gross_mass     = stage_dry_kg + eng_mass_total + stage_prop_kg + payload_kg
    burnout_mass   = stage_dry_kg + eng_mass_total + payload_kg

    if burnout_mass <= 0 or gross_mass <= burnout_mass:
        return {}

    dv        = isp * G0 * _math.log(gross_mass / burnout_mass)
    mdot      = thrust / (isp * G0) if isp > 0 else 0.0
    burn_time = stage_prop_kg / mdot if mdot > 0 else 0.0
    twr       = thrust / (gross_mass * G0)

    return {
        "dv_m_s":         dv,
        "twr_liftoff":    twr,
        "burn_time_s":    burn_time,
        "mdot_total_kg_s": mdot,
        "total_thrust_N": thrust,
        "gross_mass_kg":  gross_mass,
        "burnout_mass_kg": burnout_mass,
        "isp_used_s":     isp,
        "engine_count":   engine_count,
    }


def _chart_engine_comparison(engines_flat: list, highlight_id: str) -> go.Figure:
    """
    Three-panel horizontal bar chart comparing all engines on:
      1. Vacuum Isp (s)          — delta-v driver
      2. Sea-Level Thrust (kN)   — liftoff thrust
      3. Thrust-to-Weight ratio  — engine efficiency

    The highlighted engine is shown in its family colour; others are dim.
    """
    G0 = 9.80665

    names   = []
    isp_vac = []
    thr_sl  = []
    twr     = []
    colors  = []

    for e in engines_flat:
        label = f"{e['name']}\n({e['variant']})"
        names.append(label)
        isp_vac.append(e["isp_vac_s"])
        thr_sl.append(e["thrust_sl_N"] / 1_000)   # → kN
        mass_N = e["mass_kg"] * G0
        twr.append(e["thrust_sl_N"] / mass_N if mass_N > 0 else 0)
        colors.append(
            e["_fam_color"] if e["id"] == highlight_id
            else "rgba(150,160,175,0.45)"
        )

    from plotly.subplots import make_subplots
    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=[
            "真空比衝 Vacuum Isp (s)",
            "海平面推力 SL Thrust (kN)",
            "推重比 Thrust-to-Weight",
        ],
        horizontal_spacing=0.10,
    )

    common = dict(orientation="h", marker_color=colors,
                  hovertemplate="%{x:.1f}<extra>%{y}</extra>")

    fig.add_trace(
        go.Bar(x=isp_vac, y=names, name="Isp Vac", **common),
        row=1, col=1,
    )
    fig.add_trace(
        go.Bar(x=thr_sl, y=names, name="Thrust SL", **common),
        row=1, col=2,
    )
    fig.add_trace(
        go.Bar(x=twr,    y=names, name="T/W",       **common),
        row=1, col=3,
    )

    fig.update_layout(
        height=360,
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        showlegend=False,
        margin=dict(l=10, r=10, t=40, b=10),
        font=dict(color="#ccc", size=10),
    )
    for col in [1, 2, 3]:
        fig.update_xaxes(gridcolor="#333", row=1, col=col)
        fig.update_yaxes(gridcolor="#333", row=1, col=col)
    return fig


def tab_engine_library(baseline: dict) -> None:
    """Tab 6: Engine Library — browse, compare, and apply engines."""
    st.header("🔧 發動機資料庫  Engine Library")
    st.caption(
        "瀏覽各大引擎家族的技術規格、性能比較，並將選定引擎載入第一節或第二節進行模擬。\n"
        "Browse engine families, compare performance metrics, and apply any engine "
        "to Stage 1 or Stage 2 of the vehicle for trade studies."
    )

    # ── Show active overrides banner ───────────────────────────────────────
    ov1 = st.session_state.get("eng_override_s1")
    ov2 = st.session_state.get("eng_override_s2")
    if ov1 or ov2:
        parts = []
        if ov1:
            parts.append(f"**S1 →** {ov1['name']}")
        if ov2:
            parts.append(f"**S2 →** {ov2['name']}")
        banner_col, clear_col = st.columns([5, 1])
        banner_col.info(
            "引擎覆蓋已啟用  Engine override active: " + "  |  ".join(parts)
        )
        if clear_col.button("✖ 清除 Clear", use_container_width=True):
            st.session_state.pop("eng_override_s1", None)
            st.session_state.pop("eng_override_s2", None)
            st.rerun()

    # ── Load engine library ────────────────────────────────────────────────
    lib = _load_engine_library()

    # Build a flat list (all engines) for the comparison chart
    engines_flat: list = []
    for fam in lib["families"]:
        for eng in fam["engines"]:
            eng["_fam_color"] = fam["color"]
            eng["_fam_id"]    = fam["id"]
            engines_flat.append(eng)

    # ── Family sub-tabs ────────────────────────────────────────────────────
    fam_names = [f"{f['emoji']} {f['name']}" for f in lib["families"]]
    fam_tabs  = st.tabs(fam_names)

    for fam_tab, family in zip(fam_tabs, lib["families"]):
        with fam_tab:
            # Family intro
            st.markdown(f"**{family['description']}**")
            st.markdown(f"*{family['description_zh']}*")
            st.divider()

            # Engine selector (left) + detail (right)
            sel_col, detail_col = st.columns([1, 2], gap="large")

            with sel_col:
                st.subheader("選擇引擎  Select Engine")
                eng_labels = [
                    f"{e['name']}  ({e['variant']})"
                    for e in family["engines"]
                ]
                sel_idx = st.radio(
                    "引擎 Engine",
                    range(len(eng_labels)),
                    format_func=lambda i: eng_labels[i],
                    key=f"eng_sel_{family['id']}",
                    label_visibility="collapsed",
                )
                eng = family["engines"][sel_idx]

                # Quick-glance metrics
                st.markdown("---")
                g0 = 9.80665
                twr_val = eng["thrust_sl_N"] / (eng["mass_kg"] * g0)
                qa, qb = st.columns(2)
                qa.metric("Isp 海平面 SL", f"{eng['isp_sl_s']} s")
                qb.metric("Isp 真空 Vac",  f"{eng['isp_vac_s']} s")
                qc, qd = st.columns(2)
                qc.metric("推力 SL", f"{eng['thrust_sl_N']/1000:.0f} kN")
                qd.metric("推力 Vac", f"{eng['thrust_vac_N']/1000:.0f} kN")
                qe, qf = st.columns(2)
                qe.metric("T/W 比", f"{twr_val:.0f}")
                qf.metric("質量 Mass", f"{eng['mass_kg']} kg")

                # Status & reuse badge
                st.markdown("---")
                status_icon = "✅" if "Operational" in eng["status"] else "🔬"
                reuse_icon  = "♻️ Reusable" if eng["reusable"] else "🔴 Expendable"
                st.markdown(f"{status_icon} **{eng['status']}**  ·  {reuse_icon}")
                st.caption(
                    f"首飛年份 First flight: **{eng['first_flight_year']}**  ·  "
                    f"典型數量 Typical count: **{eng['typical_count']}**"
                )

                # Apply to Stage buttons
                st.markdown("---")
                st.markdown("**載入載具  Apply to Vehicle**")
                sim_eng = _engine_to_sim_dict(eng)
                a1, a2 = st.columns(2)
                if a1.button(
                    "→ 第一節 S1",
                    key=f"apply_s1_{family['id']}_{sel_idx}",
                    use_container_width=True,
                    type="primary",
                ):
                    st.session_state["eng_override_s1"] = sim_eng
                    st.success(f"S1 已設定為 {sim_eng['name']}")
                if a2.button(
                    "→ 第二節 S2",
                    key=f"apply_s2_{family['id']}_{sel_idx}",
                    use_container_width=True,
                ):
                    st.session_state["eng_override_s2"] = sim_eng
                    st.success(f"S2 已設定為 {sim_eng['name']}")
                st.caption(
                    "套用後，其他分頁（儀表板、掃描）的模擬將使用所選引擎規格。\n"
                    "Once applied, simulations in other tabs (Dashboard, Sweep) "
                    "will use the selected engine specs."
                )

            with detail_col:
                # ── Engine specs card ──────────────────────────────────────
                st.subheader(
                    f"{eng['name']}  —  {eng['variant']}  ·  {eng['rocket']}"
                )
                st.markdown(f"🔗 **推進劑 Propellant:** {eng['propellant']}")
                st.markdown(f"⚙️ **燃燒循環 Cycle:** {eng['cycle']}  *({eng['cycle_zh']})*")

                # Specs table
                rows_spec = [
                    {"參數 Parameter": "海平面推力 Thrust SL",
                     "數值 Value": f"{eng['thrust_sl_N']/1000:.1f} kN",
                     "備注 Note": ""},
                    {"參數 Parameter": "真空推力 Thrust Vac",
                     "數值 Value": f"{eng['thrust_vac_N']/1000:.1f} kN",
                     "備注 Note": ""},
                    {"參數 Parameter": "海平面比衝 Isp SL",
                     "數值 Value": f"{eng['isp_sl_s']} s",
                     "備注 Note": "Higher Isp → more Δv per kg propellant"},
                    {"參數 Parameter": "真空比衝 Isp Vac",
                     "數值 Value": f"{eng['isp_vac_s']} s",
                     "備注 Note": ""},
                    {"參數 Parameter": "引擎質量 Mass",
                     "數值 Value": f"{eng['mass_kg']} kg",
                     "備注 Note": ""},
                    {"參數 Parameter": "燃燒室壓力 Chamber Pressure",
                     "數值 Value": f"{eng['chamber_pressure_bar']} bar",
                     "備注 Note": "Higher → better efficiency & smaller engine"},
                    {"參數 Parameter": "噴嘴膨脹比 Nozzle Ratio",
                     "數值 Value": f"{eng['nozzle_ratio']}:1",
                     "備注 Note": "Higher → better vacuum Isp"},
                    {"參數 Parameter": "推力調節範圍 Throttle",
                     "數值 Value": f"{int(eng['throttle_min']*100)}–{int(eng['throttle_max']*100)}%",
                     "備注 Note": ""},
                    {"參數 Parameter": "推重比 T/W (per engine)",
                     "數值 Value": f"{eng['thrust_sl_N']/(eng['mass_kg']*9.80665):.0f}",
                     "備注 Note": "Ratio of SL thrust to engine weight"},
                ]
                st.dataframe(
                    rows_spec,
                    use_container_width=True,
                    hide_index=True,
                )

                # Key feature
                st.info(f"**Key Feature:** {eng['key_feature']}")
                st.caption(eng['key_feature_zh'])

                # Educational notes
                edu = eng.get("educational", {})
                if edu:
                    with st.expander("📖 教育說明  Educational Notes", expanded=False):
                        for k, v in edu.items():
                            st.markdown(f"**{k.replace('_', ' ').title()}:** {v}")

            # ── Comparison chart (full width below both columns) ───────────
            st.divider()
            st.subheader("📊 全引擎比較圖  All-Engine Comparison")
            st.caption(
                "三項指標橫向比較全部引擎；反白色條為目前選定的引擎。\n"
                "Three key metrics compared across all engines.  "
                "The highlighted bar is the currently selected engine."
            )
            comp_fig = _chart_engine_comparison(engines_flat, eng["id"])
            st.plotly_chart(comp_fig, use_container_width=True)

            # ── Performance Calculator ─────────────────────────────────────
            st.divider()
            with st.expander(
                "🧮 性能計算機  Performance Calculator", expanded=False
            ):
                st.markdown(
                    "根據選定引擎和目前基準載具質量，計算比推、推重比和燃燒時間。\n\n"
                    "Compute stage Δv, T/W and burn time for the selected engine "
                    "given the current baseline vehicle masses."
                )

                pc1, pc2, pc3 = st.columns(3)
                with pc1:
                    stage_choice = st.radio(
                        "套用節次 Stage",
                        ["第一節 Stage 1", "第二節 Stage 2"],
                        key=f"pc_stage_{family['id']}",
                    )
                    use_s1 = stage_choice.startswith("第一")

                with pc2:
                    max_count = 33 if "Raptor" in eng["name"] else 9
                    n_engines = st.slider(
                        "引擎數量 Engine Count",
                        1, max_count,
                        int(eng["typical_count"]),
                        1,
                        key=f"pc_neng_{family['id']}_{sel_idx}",
                    )

                with pc3:
                    use_vac = st.checkbox(
                        "使用真空 Isp  Use vacuum Isp",
                        value=not use_s1,
                        key=f"pc_vac_{family['id']}_{sel_idx}",
                        help="Stage 1 typically uses SL Isp; Stage 2 uses vacuum Isp.",
                    )

                if use_s1:
                    dry_kg  = float(baseline["stage1"]["dry_mass"])
                    prop_kg = float(baseline["stage1"]["prop_mass"])
                    pay_kg  = 0.0   # payload stays with S2
                else:
                    dry_kg  = float(baseline["stage2"]["dry_mass"])
                    prop_kg = float(baseline["stage2"]["prop_mass"])
                    pay_kg  = float(baseline["payload_mass"]) + float(
                        baseline.get("fairing_mass", 0)
                    )

                perf = _engine_performance_calc(
                    eng, dry_kg, prop_kg, pay_kg, n_engines, use_vac
                )

                # Baseline comparison (Merlin 1D for S1, Merlin Vacuum for S2)
                baseline_eng = (
                    baseline["stage1"]["engine"] if use_s1
                    else baseline["stage2"]["engine"]
                )
                baseline_eng_lib = {
                    "thrust_sl_N":  float(baseline_eng["thrust_sl"]),
                    "thrust_vac_N": float(baseline_eng["thrust_vac"]),
                    "isp_sl_s":     float(baseline_eng["isp_sl"]),
                    "isp_vac_s":    float(baseline_eng["isp_vac"]),
                    "mass_kg":      float(baseline_eng["mass"]),
                }
                base_count = (
                    int(baseline["stage1"]["engine_count"]) if use_s1 else 1
                )
                perf_base = _engine_performance_calc(
                    baseline_eng_lib, dry_kg, prop_kg, pay_kg,
                    base_count, use_vac
                )

                if perf and perf_base:
                    r1, r2, r3, r4 = st.columns(4)
                    dv_delta  = perf["dv_m_s"] - perf_base["dv_m_s"]
                    twr_delta = perf["twr_liftoff"] - perf_base["twr_liftoff"]
                    r1.metric(
                        "Δv",
                        f"{perf['dv_m_s']:,.0f} m/s",
                        delta=f"{dv_delta:+,.0f} m/s vs baseline",
                        delta_color="normal",
                    )
                    r2.metric(
                        "推重比 T/W",
                        f"{perf['twr_liftoff']:.2f}",
                        delta=f"{twr_delta:+.2f} vs baseline",
                        delta_color="normal",
                    )
                    r3.metric(
                        "燃燒時間 Burn Time",
                        f"{perf['burn_time_s']:.0f} s",
                    )
                    r4.metric(
                        "總推力 Total Thrust",
                        f"{perf['total_thrust_N']/1e6:.2f} MN",
                    )
                    st.caption(
                        f"Isp used: {perf['isp_used_s']} s  ·  "
                        f"Gross mass: {perf['gross_mass_kg']:,.0f} kg  ·  "
                        f"Burnout mass: {perf['burnout_mass_kg']:,.0f} kg  ·  "
                        f"Engine count: {n_engines}"
                    )

                    # Detailed comparison table
                    with st.expander("詳細對比表 Detail Comparison Table"):
                        cmp_rows = [
                            {"指標 Metric": "引擎名稱 Engine",
                             "選定引擎 Selected": eng["name"] + " " + eng["variant"],
                             "基準引擎 Baseline": baseline_eng.get("name", "Baseline")},
                            {"指標 Metric": "引擎數量 Count",
                             "選定引擎 Selected": str(n_engines),
                             "基準引擎 Baseline": str(base_count)},
                            {"指標 Metric": "使用 Isp (s)",
                             "選定引擎 Selected": str(perf["isp_used_s"]),
                             "基準引擎 Baseline": str(perf_base["isp_used_s"])},
                            {"指標 Metric": "總推力 (MN)",
                             "選定引擎 Selected": f"{perf['total_thrust_N']/1e6:.3f}",
                             "基準引擎 Baseline": f"{perf_base['total_thrust_N']/1e6:.3f}"},
                            {"指標 Metric": "起飛質量 (kg)",
                             "選定引擎 Selected": f"{perf['gross_mass_kg']:,.0f}",
                             "基準引擎 Baseline": f"{perf_base['gross_mass_kg']:,.0f}"},
                            {"指標 Metric": "Δv (m/s)",
                             "選定引擎 Selected": f"{perf['dv_m_s']:,.0f}",
                             "基準引擎 Baseline": f"{perf_base['dv_m_s']:,.0f}"},
                            {"指標 Metric": "推重比 T/W",
                             "選定引擎 Selected": f"{perf['twr_liftoff']:.3f}",
                             "基準引擎 Baseline": f"{perf_base['twr_liftoff']:.3f}"},
                            {"指標 Metric": "燃燒時間 (s)",
                             "選定引擎 Selected": f"{perf['burn_time_s']:.0f}",
                             "基準引擎 Baseline": f"{perf_base['burn_time_s']:.0f}"},
                        ]
                        st.dataframe(cmp_rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Tab 5: Trajectory Globe
# ---------------------------------------------------------------------------

def tab_trajectory(base_url: str, baseline: dict) -> None:
    st.header("🌍 3D 軌跡模擬  3-D Trajectory Globe")
    st.caption(
        "設定發射場與軌道參數，在三維地球儀上觀看火箭從發射到入軌的完整飛行軌跡。\n"
        "Configure the launch site and orbital parameters, then watch the full ascent "
        "trajectory from liftoff to orbit on an interactive 3-D globe."
    )

    # ── Controls ──────────────────────────────────────────────────────────
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("🚀 發射參數  Launch Parameters")

        site_name = st.selectbox(
            "發射場 Launch Site",
            list(LAUNCH_SITES.keys()),
            index=0,
        )
        site_lat, site_lon, site_az, site_note = LAUNCH_SITES[site_name]

        if "自訂" in site_name:
            site_lat = st.number_input("緯度 Latitude (°N)", -90.0, 90.0,
                                       float(site_lat), 0.5)
            site_lon = st.number_input("經度 Longitude (°E)", -180.0, 180.0,
                                       float(site_lon), 0.5)
            site_az  = st.number_input("發射方位角 Azimuth (°, 0=N 90=E)",
                                       0.0, 360.0, float(site_az), 1.0)
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("緯度 Lat",  f"{site_lat:.1f}°N")
            c2.metric("經度 Lon",  f"{site_lon:.1f}°E")
            c3.metric("方位角 Az", f"{site_az:.1f}°")
            if site_note:
                st.caption(f"載具 Vehicle: {site_note}")

        azimuth_deg = st.slider(
            "發射方位角 Launch Azimuth (°)  0=正北 North  90=正東 East",
            0.0, 360.0, float(site_az), 1.0,
        )
        st.caption(
            "方位角決定飛行方向與軌道傾角。正東（90°）產生最低傾角（等於發射緯度）。\n"
            "Azimuth sets the flight direction and orbital inclination. "
            "Due east (90°) yields minimum inclination = launch latitude."
        )

    with col_right:
        st.subheader("🛰️ 軌道參數  Orbital Parameters")

        target_alt = st.slider(
            "目標軌道高度 Target Altitude (km)", 200, 1200,
            int(baseline["mission"]["target_altitude_km"]), 50,
        )

        # Auto-compute inclination from azimuth + launch latitude
        inc_auto = np.degrees(
            np.arccos(np.clip(np.cos(np.radians(site_lat)) *
                              np.sin(np.radians(azimuth_deg)), -1, 1))
        )
        inclination_deg = st.slider(
            "軌道傾角 Orbital Inclination (°)", 0.0, 98.0,
            float(round(inc_auto, 1)), 0.5,
            help="自動由發射方位角計算，亦可手動調整。 Auto-computed from azimuth; adjust manually if needed.",
        )
        st.metric("自動計算傾角 Auto-computed inclination",
                  f"{inc_auto:.1f}°",
                  delta=f"{inclination_deg - inc_auto:+.1f}° offset")

        with st.expander("📖 傾角說明 Inclination Explained", expanded=False):
            st.markdown("""
**English:** Orbital inclination is the angle between the orbital plane and Earth's equatorial plane.
- 0° = equatorial orbit (geostationary satellites)
- 28.5° = Cape Canaveral minimum (direct east launch)
- 51.6° = ISS orbit (allows Russian launches from Baikonur)
- 97–98° = Sun-synchronous orbit (SSO) — used for Earth observation

**中文：** 軌道傾角是軌道平面與地球赤道面的夾角。
- 0° = 赤道軌道（地球同步衛星）
- 28.5° = 卡納維爾角最小傾角（正東發射）
- 51.6° = 國際空間站軌道（兼容拜科努爾基地）
- 97–98° = 太陽同步軌道（對地觀測衛星常用）
""")

    st.divider()

    # ── Run button ────────────────────────────────────────────────────────
    run_traj = st.button("▶ 執行軌跡模擬  Run Trajectory Simulation",
                         type="primary", use_container_width=True)

    if run_traj:
        with st.spinner("計算軌跡並投影至 3-D 地球儀… Computing trajectory and projecting to 3-D globe…"):
            pts, stats = _compute_physics_trajectory(
                baseline, target_alt, site_lat, site_lon, azimuth_deg
            )
        st.session_state["traj_pts"]         = pts
        st.session_state["traj_stats"]       = stats
        st.session_state["traj_site_lat"]    = site_lat
        st.session_state["traj_site_lon"]    = site_lon
        st.session_state["traj_azimuth"]     = azimuth_deg
        st.session_state["traj_inclination"] = inclination_deg
        st.session_state["traj_alt"]         = target_alt
        st.session_state["show_anim"]        = False  # reset animation on new trajectory

    # ── Globe ─────────────────────────────────────────────────────────────
    pts   = st.session_state.get("traj_pts")
    stats = st.session_state.get("traj_stats")
    s_lat = st.session_state.get("traj_site_lat", site_lat)
    s_lon = st.session_state.get("traj_site_lon", site_lon)
    s_az  = st.session_state.get("traj_azimuth",  azimuth_deg)
    s_inc = st.session_state.get("traj_inclination", inclination_deg)
    s_alt = st.session_state.get("traj_alt", target_alt)

    if not pts:
        # Show empty globe with orbit ring preview only
        st.info(
            "點擊「執行軌跡模擬」以顯示飛行路徑。地球儀可自由旋轉縮放。\n"
            "Click **Run Trajectory Simulation** to display the flight path. "
            "The globe is freely rotatable and zoomable."
        )
        fig = go.Figure()
        for trace in _earth_surface_traces():
            fig.add_trace(trace)
        raan = _raan_from_launch(site_lat, site_lon, azimuth_deg)
        xo, yo, zo = _orbit_ring_xyz(target_alt, inclination_deg, raan)
        fig.add_trace(go.Scatter3d(
            x=xo, y=yo, z=zo, mode="lines",
            line=dict(color="#2ECC71", width=2, dash="dot"),
            name=f"目標軌道 {target_alt} km",
        ))
        lx, ly, lz = _latlon_to_xyz(site_lat, site_lon, 0)
        fig.add_trace(go.Scatter3d(
            x=[lx], y=[ly], z=[lz], mode="markers+text",
            marker=dict(size=7, color="#FF6B35"),
            text=["🚀 Launch"], textposition="top center",
            textfont=dict(color="#FF6B35", size=11),
            name="Launch Site",
        ))
        axis_style = dict(showbackground=False, showgrid=False,
                          zeroline=False, showticklabels=False, title="")
        fig.update_layout(
            scene=dict(xaxis=axis_style, yaxis=axis_style, zaxis=axis_style,
                       bgcolor="#05070f", aspectmode="data",
                       camera=dict(eye=dict(x=1.4, y=1.2, z=0.6))),
            paper_bgcolor="#05070f", height=620,
            margin=dict(l=0, r=0, t=20, b=0),
            legend=dict(font=dict(color="#ccc"), bgcolor="rgba(5,7,15,0.7)"),
            font=dict(color="#ccc"),
        )
        st.plotly_chart(fig, use_container_width=True)
        return

    # ── Globe chart ───────────────────────────────────────────────────────
    fig = chart_trajectory_globe(
        traj_points     = pts,
        target_alt_km   = s_alt,
        launch_lat      = s_lat,
        launch_lon      = s_lon,
        azimuth_deg     = s_az,
        inclination_deg = s_inc,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "💡 拖曳旋轉地球儀 / 滾輪縮放 / 點擊圖例隱藏圖層\n"
        "Drag to rotate · Scroll to zoom · Click legend items to toggle layers"
    )

    # ── Animation section ─────────────────────────────────────────────────
    st.divider()
    st.subheader("🎬 升空動畫  Launch Animation")
    st.caption(
        "根據已計算的軌跡生成逐幀動畫，顯示火箭從發射到入軌的完整過程。\n"
        "Generate a frame-by-frame animation of the rocket's ascent from "
        "liftoff to orbit insertion."
    )

    t_total = pts[-1]["t_s"] if pts else 0.0

    a_col1, a_col2, a_col3, a_col4 = st.columns([2, 2, 1, 1])
    with a_col1:
        anim_step = st.select_slider(
            "時間步長 Time Step (s/frame)",
            options=[5, 10, 15, 20, 30, 45, 60, 90, 120],
            value=30,
            help=(
                "每幀代表的模擬時間（秒）。步長小 → 幀數多、動畫流暢；"
                "步長大 → 幀數少、播放較快。\n"
                "Simulated seconds per frame.  "
                "Smaller = more frames / smoother.  Larger = fewer frames / faster."
            ),
        )
    with a_col2:
        anim_speed = st.select_slider(
            "播放速度 Frame Duration (ms/frame)",
            options=[30, 50, 80, 100, 150, 200, 300, 500],
            value=80,
            help=(
                "每幀在瀏覽器中播放的毫秒數。數值越小播放越快。\n"
                "Milliseconds each frame is displayed.  Lower = faster playback."
            ),
        )
    with a_col3:
        n_frames_est = int(t_total / max(anim_step, 1)) + 1
        st.metric("預計幀數 Frames", str(n_frames_est))
    with a_col4:
        duration_est = n_frames_est * anim_speed / 1000.0
        st.metric("播放時長 Duration", f"{duration_est:.0f} s")

    gen_anim = st.button(
        "▶ 生成動畫  Generate Animation",
        type="secondary",
        use_container_width=False,
        help="根據上方參數建立動畫並顯示於下方地球儀。 Build the animation with the settings above.",
    )

    if gen_anim:
        st.session_state["anim_step"]   = anim_step
        st.session_state["anim_speed"]  = anim_speed
        st.session_state["show_anim"]   = True

    if st.session_state.get("show_anim") and pts:
        _step  = st.session_state.get("anim_step",  30)
        _speed = st.session_state.get("anim_speed", 80)
        with st.spinner("建立動畫幀… Building animation frames…"):
            anim_fig = chart_trajectory_globe_animated(
                traj_points     = pts,
                target_alt_km   = s_alt,
                launch_lat      = s_lat,
                launch_lon      = s_lon,
                azimuth_deg     = s_az,
                inclination_deg = s_inc,
                time_step_s     = _step,
                frame_duration_ms = _speed,
            )
        st.plotly_chart(anim_fig, use_container_width=True)
        st.caption(
            "▶ 播放 / ⏸ 暫停 / ⏮ 重置  ·  拖曳時間軸跳至任意時刻  ·  地球儀可自由旋轉縮放\n"
            "Play · Pause · Reset  ·  Drag the timeline to jump to any moment  "
            "·  Globe is freely rotatable and zoomable"
        )

    # ── Stats panel ───────────────────────────────────────────────────────
    st.divider()

    if stats.get("physics_based"):
        st.subheader("📊 物理軌跡統計  Physics-Based Trajectory Statistics")
        orbit_ok = stats.get("orbit_achieved")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("入軌達成 Orbit", "✅ 是 YES" if orbit_ok else "❌ 否 NO")
        c2.metric("燃盡速度 Burnout Vel.",
                  f"{stats['burnout_velocity_m_s']:,.0f} m/s",
                  delta=f"{stats['burnout_velocity_m_s'] - stats['orbital_velocity_m_s']:+,.0f} m/s vs circ.")
        c3.metric("燃盡高度 Burnout Alt.", f"{stats['burnout_alt_km']:.1f} km")
        c4.metric("積分 Δv  Integrated ΔV", f"{stats['integrated_dv_m_s']:,.0f} m/s")
        c5.metric("總射程 Downrange", f"{stats['downrange_km']:.0f} km")

        c6, c7, c8, c9, c10 = st.columns(5)
        c6.metric("MECO T+", f"{stats['t_meco_s']:.0f} s")
        c7.metric("SECO T+", f"{stats['t_seco_s']:.0f} s")
        c8.metric("Max-Q 壓力", f"{stats['max_q_kPa']:.1f} kPa")
        c9.metric("Max-Q 高度", f"{stats['max_q_alt_km']:.1f} km")
        c10.metric("Max-Q T+", f"{stats['max_q_time_s']:.0f} s")

        with st.expander("📐 Δv 預算解析  Δv Budget Explained", expanded=False):
            v_circ = stats["orbital_velocity_m_s"]
            v_bo   = stats["burnout_velocity_m_s"]
            dv_int = stats["integrated_dv_m_s"]
            diff   = v_bo - v_circ
            label  = ("速度不足 under-speed — 未達圓軌道 below circular orbit"
                      if v_bo < v_circ * 0.95 else
                      "速度超出 over-speed" if v_bo > v_circ * 1.05 else
                      "接近圓軌道速度 near circular orbit ✅")
            st.markdown(f"""
**圓軌道速度 Circular orbit velocity** at {s_alt} km:
$$v_{{\\text{{circ}}}} = \\sqrt{{\\mu / (R_\\oplus + h)}} = {v_circ:,.0f}\\text{{ m/s}}$$

| 量 Quantity | 數值 Value |
|---|---|
| 積分 Δv (ODE result) | {dv_int:,.0f} m/s |
| 燃盡速度 Burnout velocity | {v_bo:,.0f} m/s |
| 差值 Difference vs. circular | {diff:+,.0f} m/s — {label} |

**教師備注 Teacher Note:** 燃盡速度接近（而非完全等於）圓軌道速度，
才是真實 ODE 積分的特徵。完美的符合代表「終點被手工設定」。
真實飛行器的 GNC 系統在 SECO 時會有控制誤差，最終靠末燃修正。

The burnout velocity approaching (not exactly equalling) v_circ is the hallmark
of a genuine numerical integration. A perfect match would indicate the endpoint
was manually forced. Real GNC systems accept a small residual, corrected by a trim burn.
""")
    else:
        st.subheader("📊 軌跡統計（簡化模型）Trajectory Statistics (simplified model)")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("目標高度 Target Alt",   f"{stats['target_alt_km']:.0f} km")
        c2.metric("軌道速度 Orbital Vel.", f"{stats['orbital_velocity_m_s']:,.0f} m/s")
        c3.metric("MECO T+",               f"{stats['t_meco_s']:.0f} s")
        c4.metric("SECO T+",               f"{stats['t_seco_s']:.0f} s")
        c5.metric("總射程 Downrange",      f"{stats['downrange_km']:.0f} km")

    if stats.get("warnings"):
        for w_msg in stats["warnings"]:
            st.warning(w_msg)

    with st.expander("📋 軌跡數據表 Trajectory Data Table", expanded=False):
        rows = [
            {
                "T (s)":               round(p.get("t_s", 0), 1),
                "高度 Alt (km)":       round(p.get("altitude_km", 0), 2),
                "射程 Downrange (km)": round(p.get("downrange_km", 0), 1),
                "速度 Velocity (m/s)": round(p.get("velocity_m_s", 0), 0),
                "質量 Mass (kg)":      round(p.get("mass_kg", 0), 0),
                "飛行段 Phase":        p.get("phase", ""),
            }
            for p in pts[::max(1, len(pts) // 50)]
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)

    # ── CSV download ──────────────────────────────────────────────────────
    model_tag = "3DOF-ODE" if stats.get("physics_based") else "simplified-display"
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow([f"# 軌跡資料 Trajectory Data ({model_tag})"])
    w.writerow(["# 發射場", f"lat={s_lat} lon={s_lon} az={s_az}°"])
    w.writerow(["# 軌道", f"alt={s_alt} km  inc={s_inc}°"])
    w.writerow(["T (s)", "Alt (km)", "Downrange (km)", "Velocity (m/s)", "Mass (kg)", "Phase"])
    for p in pts:
        w.writerow([p.get("t_s"), p.get("altitude_km"),
                    p.get("downrange_km"), p.get("velocity_m_s"),
                    p.get("mass_kg", 0), p.get("phase")])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label="⬇ 下載軌跡 CSV  Download Trajectory CSV",
        data=buf.getvalue(),
        file_name=f"trajectory_{ts}.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    base_url, baseline, run_baseline = build_sidebar()

    st.title("🚀 獵鷹 9 號式火箭教育模擬器 — 設計權衡研究工具")
    st.caption("Falcon 9-like Rocket Educational Simulator — Interactive Trade Study GUI | 互動式設計分析介面")

    if "api_ok" not in st.session_state:
        st.session_state["api_ok"] = api_health(base_url)

    if not st.session_state.get("api_ok"):
        st.error(
            "**無法連線至 API / Cannot reach the API.**\n\n"
            "請先啟動後端伺服器 / Start the backend server:\n"
            "```\nuvicorn apps.api.app.main:app --reload\n```"
        )

    # ── Apply engine-library overrides (set via Tab 6) ────────────────────
    for stage_key, ss_key in [("stage1", "eng_override_s1"),
                               ("stage2", "eng_override_s2")]:
        ov = st.session_state.get(ss_key)
        if ov:
            for field in ("name", "thrust_sl", "thrust_vac",
                          "isp_sl", "isp_vac", "mass"):
                if field in ov:
                    baseline[stage_key]["engine"][field] = ov[field]

    # ── Sidebar: show override indicator ──────────────────────────────────
    ov1 = st.session_state.get("eng_override_s1")
    ov2 = st.session_state.get("eng_override_s2")
    if ov1 or ov2:
        st.sidebar.divider()
        st.sidebar.warning(
            "**引擎覆蓋啟用 Engine Override Active**\n\n" +
            (f"S1: {ov1['name']}\n" if ov1 else "") +
            (f"S2: {ov2['name']}\n" if ov2 else "") +
            "\n前往「發動機資料庫」分頁清除。\n"
            "Go to Engine Library tab to clear."
        )

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 儀表板 Dashboard",
        "📈 單參數掃描 Single Sweep",
        "🗺️ 雙參數比較 Two-Parameter",
        "📚 學習指南 Guide",
        "🌍 軌跡模擬 Trajectory Globe",
        "🔧 發動機資料庫 Engine Library",
        "⚙️ 求解器文件 Solver Reference",
    ])

    with tab1:
        tab_dashboard(base_url, baseline, run_baseline)
    with tab2:
        tab_single_sweep(base_url, baseline)
    with tab3:
        tab_two_param(base_url, baseline)
    with tab4:
        tab_guide()
    with tab5:
        tab_trajectory(base_url, baseline)
    with tab6:
        tab_engine_library(baseline)
    with tab7:
        tab_solver_reference()


if __name__ == "__main__":
    main()
