# Rocket Trade Study Simulator 火箭設計權衡研究模擬器

An interactive educational simulator for exploring two-stage rocket design trade-offs, inspired by the Falcon 9 Block 5.  
互動式教育模擬器，以獵鷹 9 號 Block 5 為靈感，探索兩節式火箭設計的權衡取捨。

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

---

## Project Structure 專案結構

```
rocket-edu-sim/
├── trade_study_gui.py          # Streamlit application entry point / Streamlit 應用程式入口
├── trade_study.py              # Headless batch trade study runner / 無介面批次執行器
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
├── apps/
│   └── api/                    # FastAPI REST service / FastAPI REST 服務
│       └── app/
│           ├── routers/        # /simulate endpoint / 模擬端點
│           ├── schemas/        # Pydantic request/response models
│           └── services/       # Orchestration layer / 服務編排層
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

### API Server (optional) API 服務（選用）

```bash
pip install -r apps/api/requirements.txt
uvicorn apps.api.app.main:app --reload
# Docs at http://localhost:8000/docs
```

---

## Tech Stack 技術棧

| Layer 層 | Technology 技術 |
|---------|---------------|
| GUI | [Streamlit](https://streamlit.io/) |
| Visualisation 視覺化 | [Plotly](https://plotly.com/) (3D globe, animations, subplots) |
| ODE solver ODE 解算器 | `scipy.integrate.solve_ivp` (RK45) |
| Data models 資料模型 | [Pydantic v2](https://docs.pydantic.dev/) |
| API | [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn |
| Packaging 套件管理 | [Hatch](https://hatch.pypa.io/) |

---

## License 授權

MIT License — see [LICENSE](LICENSE) for details.  
MIT 授權 — 詳見 [LICENSE](LICENSE)。
