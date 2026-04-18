# Rocket Trade Study Simulator 火箭設計權衡研究模擬器

> **For** undergraduate aerospace / mechanical engineering students and space enthusiasts who want to see how design choices — Isp, staging, TWR — translate into payload to orbit.  
> **適合** 大學航太／機械系學生及太空愛好者，透過互動方式理解比衝、分節策略、推重比等設計選擇如何影響入軌酬載量。

An interactive educational simulator for exploring two-stage rocket design trade-offs, inspired by the Falcon 9 Block 5.  
互動式教育模擬器，以獵鷹 9 號 Block 5 為靈感，探索兩節式火箭設計的權衡取捨。

> **Disclaimer 免責聲明:** This is a teaching tool, not a mission-design reference. Numbers are calibrated to be realistic but are approximate — focus on trends and sensitivities rather than absolute values.  
> 本工具為教學用途，非任務設計參考。數值已校準至合理範圍，但屬近似值 — 請著重趨勢與敏感度分析，而非絕對數字。

---

## Features 功能特色

| Tab 頁籤 | Description 說明 |
|---------|----------------|
| **Vehicle Config 載具設定** | Configure stage masses, engine counts, propellant, and mission target / 設定各節質量、發動機數量、推進劑與任務目標 |
| **Results 結果分析** | ΔV budget, payload fraction, TWR, staging summary / ΔV 預算、酬載分率、推重比、分節摘要 |
| **Trade Study 權衡研究** | Single-parameter sweeps and two-parameter heat-maps / 單參數掃描與雙參數熱圖比較 |
| **Trajectory Globe 軌跡地球儀** | 3D animated globe with world boundaries, launch site, orbit ring, and phase-coloured trajectory / 3D 動畫地球儀，含世界邊界、發射場、目標軌道環與分段著色軌跡 |
| **Sensitivity 敏感度分析** | Tornado chart ranking design variables by payload impact / 龍捲風圖，排序設計變數對酬載的影響 |
| **Engine Library 發動機庫** | Browse SpaceX, Rocket Lab, and Legacy engines; compare Isp / thrust / T-W; apply to either stage / 瀏覽 SpaceX、Rocket Lab 與傳統發動機；比較比衝、推力、推重比；套用至各節 |
| **Solver Reference 解算器說明** | Phase timeline Gantt chart and in-depth documentation of the physics solver / 飛行段甘特圖與核心物理解算器深入說明 |
| **Student Guide 學習指南** | Bilingual student version and teacher edition with derivations / 雙語學生版與含推導過程的教師版 |

---

## Physics Highlights 物理亮點

- **Two-burn Hohmann ascent** — Stage 2 Burn 1 raises apogee to target altitude; Hohmann coast; Burn 2 circularises  
  **兩次點火霍曼上升** — 第二節第一次燃燒將遠地點抬升至目標高度；霍曼滑行；第二次燃燒完成圓化
- **Corrected 2-D local-frame ODE** — includes the Coriolis term `−vy·vx/r` and centrifugal term `+vx²/r` required for angular-momentum conservation during unpowered coast  
  **修正後的二維局部座標系運動方程** — 加入無動力滑行段角動量守恆所需的科氏項與離心項
- **ZEV guidance** — Zero-Elevation-rate-Vector pitch program for Stage 2 burns  
  **ZEV 導引律** — 第二節燃燒使用零仰角速率向量俯仰程序
- **Event-driven integration** — `scipy.solve_ivp` with per-phase terminal events (MECO, apogee, circularisation)  
  **事件驅動積分** — 使用 `scipy.solve_ivp`，各飛行段以端點事件觸發切換
- **Model scope & limitations** — 2-D point-mass, no 6-DOF attitude / structural bending / propellant slosh; atmosphere is exponential; no winds or range-safety constraints  
  **模型範圍與限制** — 二維質點模型，不含六自由度姿態、結構彎曲或推進劑晃動；大氣為指數模型，不含風場或飛行安全限制

---

## Project Structure 專案結構

```
rocket-edu-sim/
├── trade_study_gui.py          # Streamlit application entry point / Streamlit 應用程式入口
├── trade_study.py              # Interactive CLI trade-study runner / 互動式 CLI 工具
├── requirements.txt            # Streamlit Cloud dependencies / 雲端部署相依套件
│
├── packages/
│   └── rocket_core/            # Physics solver library / 物理解算器核心庫
│       ├── vehicle/            # Vehicle & stage data models / 載具與各節資料模型
│       ├── propulsion/         # Thrust, Isp, mass-flow solver / 推力、比衝、質量流率
│       ├── mass_budget/        # Liftoff mass, TWR, payload fraction / 起飛質量、推重比、酬載分率
│       ├── staging/            # Per-stage ΔV and loss accounting / 各節 ΔV 與損失計算
│       ├── payload/            # Maximum payload estimator / 最大酬載估算
│       ├── constraints/        # TWR / burn-time / structure-fraction checker / 約束檢查
│       └── trajectory/         # 2-D ODE trajectory solver (Hohmann) / 二維軌跡解算器（霍曼）
│
├── data/
│   ├── engines/
│   │   ├── engine_library.json # 9 engines across 3 families / 3 系列共 9 款發動機
│   │   └── merlin_catalog.json
│   ├── templates/              # Vehicle config presets / 載具設定預設值
│   │   ├── template_falcon9_like.json
│   │   └── template_student_starter.json
│   ├── geo/
│   │   └── world_boundaries.geojson  # Country boundaries for 3D globe / 3D 地球儀國界資料
│   └── propellants/
│       └── propellants.json
│
├── docs/
│   └── instructor_guide.md     # 2-hour lab plan / 2 小時實驗課程計畫
│
└── tests/
    ├── unit/
    └── integration/
```

---

## Calibration Reference 校準參考

The Falcon 9-like template is calibrated against publicly observed NG-24 Cygnus mission data:  
獵鷹 9 號模板根據 NG-24 天鵝座任務公開觀測數據校準：

| Parameter 參數 | Observed 觀測值 | Simulated 模擬值 |
|---------------|---------------|----------------|
| Deployment altitude 部署高度 | ~256 km (T+14:47) | 260.4 km |
| Circular orbital velocity 圓形軌道速度 | ~7,742 m/s | 7,752 m/s (+10 m/s) |
| Total ΔV incl. losses 含損失總 ΔV | — | ~9,200–9,500 m/s (see Results tab) |

---

## Engine Library 發動機庫

| Family 系列 | Engines 發動機 |
|------------|--------------|
| SpaceX | Merlin 1D (SL & Vacuum), Raptor 2, Raptor Vacuum |
| Rocket Lab | Rutherford (SL & Vacuum) |
| Legacy | RD-180, BE-4, RS-25 |

---

## Quick Start 快速開始

### Prerequisites 前置需求

- Python 3.11+
- [Streamlit](https://streamlit.io/) `pip install streamlit`

### Install & Run 安裝與執行

```bash
# Clone the repository / 複製儲存庫
git clone https://github.com/RhynoW/rocket-edu-sim.git
cd rocket-edu-sim

# Install the physics solver library / 安裝物理解算器套件
pip install -e packages/rocket_core

# Install GUI dependencies / 安裝介面相依套件
pip install streamlit plotly numpy scipy

# Launch the simulator / 啟動模擬器
streamlit run trade_study_gui.py
```

### First-run sanity check 首次執行驗證

1. In the sidebar, select the **Falcon 9-like** template and click **Run Simulation**.  
   在側邊欄選擇 **Falcon 9-like** 模板，點擊 **Run Simulation**。
2. Open the **Results** tab — you should see final orbit altitude in the ~255–265 km range and orbital velocity ~7.75 km/s.  
   開啟 **Results** 頁籤 — 最終軌道高度應在 ~255–265 km，軌道速度 ~7.75 km/s。
3. If those numbers appear, your environment is correctly installed.  
   若數值符合，表示環境安裝正確。

### CLI Trade Study (optional) CLI 模式（選用）

```bash
python trade_study.py   # interactive menu / 互動式選單
```

---

## Documentation 文件

| Document 文件 | Description 說明 |
|--------------|----------------|
| [Instructor's Guide](docs/instructor_guide.md) | 2-hour lab plan with timeline, worksheets, and discussion questions / 2 小時實驗課程計畫，含時間表、工作表與討論題 |
| Student Guide (in app) | Bilingual student + teacher edition — open the **Student Guide** tab in the simulator / 雙語學生版與教師版 — 在模擬器中開啟「學習指南」頁籤 |
| Solver Reference (in app) | Phase Gantt chart and physics documentation — open the **Solver Reference** tab / 飛行段甘特圖與物理文件 — 在模擬器中開啟「解算器說明」頁籤 |

---

## Tech Stack 技術棧

| Layer 層 | Technology 技術 |
|---------|---------------|
| GUI | [Streamlit](https://streamlit.io/) |
| Visualisation 視覺化 | [Plotly](https://plotly.com/) (3D globe, animations, subplots) |
| ODE solver ODE 解算器 | `scipy.integrate.solve_ivp` (RK45) |
| Data models 資料模型 | [Pydantic v2](https://docs.pydantic.dev/) |
| Packaging 套件管理 | [Hatch](https://hatch.pypa.io/) |

---

## License 授權

MIT License — see [LICENSE](LICENSE) for details.  
MIT 授權 — 詳見 [LICENSE](LICENSE)。
