# Rocket-Edu-Sim – Instructor's Guide (2-Hour Lab)
# 火箭模擬器 — 教師指南（2 小時實驗課）

---

## 0. Overview 概述

**Audience 適用對象:** 2nd–3rd year aerospace / ME students, or advanced high-school STEM.  
二、三年級航太／機械系學生，或程度較高的高中 STEM 學生。

**Duration 時長:** 2 hours (1× lab session) / 2 小時（單次實驗課）

**Goal 目標:** Use *rocket-edu-sim* to connect the rocket equation, staging, and trade studies to an interactive Falcon-9-like launch vehicle.  
利用 *rocket-edu-sim*，將火箭方程式、分節策略與設計權衡研究連結至可互動的獵鷹 9 號類比載具。

By the end of the lab, students should be able to:  
完成實驗後，學生應能夠：

- Explain what a **design trade study** is in the context of launch vehicles.  
  說明**設計權衡研究**在運載火箭中的定義與目的。
- Relate **rocket equation parameters** (Isp, mass ratio) to payload capacity.  
  將**火箭方程式參數**（比衝、質量比）與酬載能力連結起來。
- Interpret key performance metrics from the simulator (Δv, TWR, payload fraction).  
  解讀模擬器輸出的關鍵性能指標（Δv、推重比、酬載分率）。
- Run at least one **single-parameter trade study** and extract a trend.  
  執行至少一項**單參數權衡研究**並歸納趨勢。
- Present a short, data-based conclusion (e.g., "Stage-2 Isp is more impactful than Stage-1 Isp for payload").  
  提出簡短的數據驅動結論（例如「第二節比衝對酬載的影響大於第一節比衝」）。

---

## 1. Pre-Lab Preparation (Instructor) 課前準備（教師）

### 1.1 Install & sanity check 安裝與驗證

On the lab machine (or your own machine, to prepare):  
在實驗室電腦（或自己的電腦）上執行：

```bash
git clone https://github.com/RhynoW/rocket-edu-sim.git
cd rocket-edu-sim

# Install core package / 安裝核心套件
pip install -e packages/rocket_core

# Optional: create a virtual environment first / 建議先建立虛擬環境
# python -m venv .venv && source .venv/bin/activate   (Linux/macOS)
# .venv\Scripts\activate                              (Windows)

# Install GUI dependencies / 安裝介面套件
pip install streamlit plotly numpy scipy

# Launch the simulator / 啟動模擬器
streamlit run trade_study_gui.py
```

**Sanity check 驗證步驟:**

1. In the browser, select the **Falcon-like** template and click **Run Simulation**.  
   在瀏覽器中選擇 **Falcon-like** 模板，點擊 **Run Simulation**。
2. Open the **Results** tab and confirm:  
   開啟 **Results** 頁籤並確認：
   - Final orbit altitude is in the ~255–265 km range / 最終軌道高度在 ~255–265 km
   - Orbital velocity is ~7.75 km/s / 軌道速度 ~7.75 km/s
3. If these numbers appear, the environment and dependencies are correct.  
   若數值符合，表示環境與套件安裝正確。

### 1.2 Decide lab format 決定實驗形式

- **Ideal: pairs** (2 students per machine) → encourages discussion and shared reasoning.  
  **建議：兩人一組**（每台電腦 2 名學生）→ 促進討論與互助學習。
- Have students bring a notebook or note-taking app — some calculations use the rocket equation directly.  
  請學生準備筆記本或筆記軟體 — 部分計算需直接使用火箭方程式。

---

## 2. Suggested 2-Hour Timeline 建議 2 小時時間表

### Segment 1 – Intro & Demo 簡介與示範 (0:00–0:20, ~20 min)

**Objective:** Students understand what the tool does and the basic workflow.  
**目標：** 學生了解工具功能與基本操作流程。

#### 5 min — Concept recap (board / slides) 概念回顧

- Rocket equation / 火箭方程式:
  $$\Delta v = I_{sp} \, g_0 \ln\frac{m_0}{m_f}$$
- Define / 定義：
  - Δv to reach **LEO** ~ 9.3–9.7 km/s (including losses) / 到達低地球軌道的 Δv ~ 9.3–9.7 km/s（含損失）
  - **Payload fraction** = payload / liftoff mass / **酬載分率** = 酬載 / 起飛質量
  - **Trade study**: systematically varying one design variable at a time to quantify its effect / **設計權衡研究**：逐一改變設計變數以量化其影響

#### 10 min — Live demo of rocket-edu-sim 現場示範

- Show **Vehicle Config** tab:  
  展示 **Vehicle Config** 頁籤：
  - Explain Stage-1 vs Stage-2 parameters, Isp, propellant mass, dry mass, payload.  
    說明第一、二節參數、比衝、推進劑質量、乾重、酬載。
- Run a simulation and show results:  
  執行模擬並展示結果：
  - **Results** tab: TWR, Δv budget, payload fraction, orbit altitude.  
    **Results** 頁籤：推重比、Δv 預算、酬載分率、軌道高度。
  - Briefly open **Trajectory Globe** to show the 3D ascent path.  
    簡短展示 **Trajectory Globe** 中的 3D 飛行軌跡。

#### 5 min — Explain lab tasks 說明實驗任務

Each pair will:  
每組學生將：

1. Run the baseline Falcon-like case and record key metrics.  
   執行基準獵鷹 9 號模擬，記錄關鍵性能指標。
2. Perform a **single-parameter trade study** (S2 Isp sweep).  
   執行一項**單參數權衡研究**（第二節比衝掃描）。
3. Optionally perform a second trade study (S1/S2 prop split or S2 dry mass).  
   選做第二項權衡研究（第一/二節推進劑分配或第二節乾重）。
4. Answer 2–3 short questions and write a 5–6 sentence conclusion.  
   回答 2–3 道問答題，並撰寫 5–6 句總結。

---

### Segment 2 – Baseline Simulation 基準模擬 (0:20–0:35, ~15 min)

**Objective:** Students get comfortable with the UI and interpret core metrics.  
**目標：** 學生熟悉介面並解讀核心指標。

**Student tasks 學生任務:**

1. Load the **Falcon-like** vehicle template.  
   載入 **Falcon-like** 載具模板。
2. Run the simulation.  
   執行模擬。
3. Record / 記錄：
   - Liftoff mass / 起飛質量
   - Payload mass and **payload fraction** / 酬載質量與**酬載分率**
   - Liftoff **TWR** / 起飛**推重比**
   - Total Δv from the staging summary / 分節摘要中的總 Δv
   - Final orbit altitude and velocity / 最終軌道高度與速度

**Quick questions (display on board / worksheet) 課堂問題（板書或工作表）:**

- **Q1:** Is the total Δv enough for LEO? Compare to ~9.3–9.7 km/s.  
  **Q1：** 總 Δv 是否足夠達到低地球軌道？與 ~9.3–9.7 km/s 比較。
- **Q2:** Is the liftoff TWR > 1.2? What would happen if TWR < 1?  
  **Q2：** 起飛推重比是否 > 1.2？若推重比 < 1 會發生什麼？
- **Q3:** What is the payload fraction? Is 2–5% typical for orbital rockets?  
  **Q3：** 酬載分率為何？2–5% 對軌道火箭而言是否典型？

**Instructor note:** Roam the room to help students locate each metric in the UI.  
**教師注意：** 巡視教室，協助學生找到各指標在介面中的位置。

---

### Segment 3 – Trade Study 1: S2 Isp vs Payload 第二節比衝 vs 酬載 (0:35–1:10, ~35 min)

**Objective:** Show how upper-stage Isp affects payload more strongly than lower-stage Isp.  
**目標：** 展示上節比衝對酬載的影響強於下節比衝。

**Setup in Trade Study tab 在 Trade Study 頁籤中設定:**

| Setting 設定 | Value 數值 |
|------------|----------|
| Scan mode 掃描模式 | Single-parameter sweep 單參數掃描 |
| Parameter 參數 | S2 Vacuum Isp |
| Range 範圍 | 320–380 s |
| Step 步進 | 10 s |

**Worksheet tasks 工作表任務:**

> **Task A — Predict 預測**  
> Using the rocket equation qualitatively: why might an increase in S2 Isp be especially valuable for payload?  
> *(Hint: S2 burns when the rocket is already fast; small Δv gains here translate directly into payload.)*  
> 定性使用火箭方程式：為何提高第二節比衝對酬載特別有利？  
> *（提示：第二節燃燒時火箭已在高速飛行，此時的 Δv 增益直接轉換為酬載。）*

> **Task B — Run the sweep 執行掃描**  
> In the Trade Study tab, sweep S2 Isp and record Isp values, payload mass, and payload fraction.  
> 在 Trade Study 頁籤執行 S2 Isp 掃描，記錄各 Isp 值對應的酬載質量與分率。

> **Task C — Plot & interpret 繪圖與解讀**  
> - Sketch (or use the built-in chart) of Payload vs S2 Isp.  
>   繪製（或使用內建圖表）酬載 vs S2 Isp 的關係圖。
> - Is the curve roughly linear, or does it show diminishing returns?  
>   曲線接近線性，還是呈現效益遞減？
> - Estimate "payload gain per +10 s of S2 Isp" in kg.  
>   估算「每提升 10 s 比衝的酬載增量（kg）」。

**Instructor notes 教師注意事項:**

- Encourage students to compare the slope of Payload vs S2 Isp against their intuition from the rocket equation.  
  鼓勵學生將酬載 vs 比衝的斜率與火箭方程式的直覺相互對應。
- If they finish early, ask: "If we increased S1 Isp by the same amount, would payload change by more or less? Why?"  
  若提早完成，追問：「若第一節比衝提升相同量，酬載的變化幅度會更大還是更小？為什麼？」

---

### Segment 4 – Trade Study 2: Mass / Staging Effects 質量與分節效應 (1:10–1:35, ~25 min)

**Objective:** Show how mass distribution and staging strategy affect payload.  
**目標：** 展示質量分配與分節策略如何影響酬載。

Offer students one of two options depending on comfort level:  
依學生程度提供兩種選項：

#### Option 1 — S1/S2 Propellant Split (two-parameter heatmap) 第一/二節推進劑分配（雙參數熱圖）

| Setting 設定 | Value 數值 |
|------------|----------|
| Mode 模式 | Two-parameter trade 雙參數比較 |
| Parameter X | S1 propellant mass (e.g. 350–450 t) |
| Parameter Y | S2 propellant mass (e.g. 80–130 t) |

Questions / 問題：

1. Where is the **payload maximum** in the S1 × S2 prop space?  
   在 S1 × S2 推進劑空間中，**酬載最大值**在哪裡？
2. Is the optimum near the ~80/20 split discussed in the Teacher Edition?  
   最佳點是否接近教師版討論的 ~80/20 分配？
3. What happens to payload when propellant is moved from S2 to S1?  
   將推進劑從第二節移至第一節時，酬載如何變化？

#### Option 2 — S2 Dry Mass vs S2 Isp (two-parameter) 第二節乾重 vs 第二節比衝（雙參數）

| Setting 設定 | Value 數值 |
|------------|----------|
| Parameter X | S2 dry mass (±20% of baseline) |
| Parameter Y | S2 Isp (±20 s of baseline) |

Questions / 問題：

1. Which is more beneficial for payload: reducing S2 dry mass by X% or increasing S2 Isp by Y s?  
   對酬載而言，降低 X% 第二節乾重 vs 提升 Y s 比衝，哪個效益更大？
2. How does this relate to the "structure vs propulsion" investment decision?  
   這與「結構輕量化 vs 推進性能提升」的投資決策有何關聯？

**Instructor tip:** If time is short, have everyone do Option 1 and keep Option 2 as a challenge problem.  
**教師提示：** 若時間緊迫，全班統一做選項 1，選項 2 留作進階挑戰。

---

### Segment 5 – Wrap-Up & Discussion 總結與討論 (1:35–2:00, ~25 min)

**Objective:** Synthesize findings and connect back to core concepts.  
**目標：** 整合發現並與核心概念對應。

Have each pair write down short answers (max 1 page):  
每組學生撰寫簡短回答（不超過 1 頁）：

**1. Baseline summary 基準摘要**

| Item | Value |
|------|-------|
| Vehicle template 載具模板 | |
| Liftoff mass 起飛質量 | |
| Payload mass & fraction 酬載質量與分率 | |
| Total Δv vs required Δv 總 Δv vs 所需 Δv | |

**2. Trade Study 1 — S2 Isp**

- Range of Isp tested / 測試的比衝範圍：
- Payload trend in one sentence, e.g. "Each +10 s Isp increased payload by ~X kg." /  
  一句話描述趨勢，例如「每提升 10 s 比衝，酬載增加約 X kg」：
- Connection to rocket equation / 與火箭方程式的關聯：

**3. Trade Study 2 — Mass / Staging**

- Which variable was more influential on payload? /哪個變數對酬載影響較大？
- Did the optimum prop split match your expectation from theory? / 最佳推進劑分配是否符合理論預期？

**4. Concept question for class discussion 課堂概念討論題**

> "If you had a limited budget, would you spend it on increasing S2 Isp or reducing S1 dry mass? Why?"  
> 「若預算有限，你會優先提升第二節比衝，還是降低第一節乾重？為什麼？」

Ask for 1–2 pairs to present a 2-minute summary.  
請 1–2 組學生進行 2 分鐘口頭摘要報告。

---

## 3. Assessment Ideas 評量建議

| Format 形式 | Description 說明 |
|------------|----------------|
| **Formative (no grade) 形成性（無成績）** | Submit screenshots of trade-study plots + short written conclusion / 繳交權衡研究圖表截圖與簡短書面結論 |
| **Graded lab 計分實驗** | Rubric: correct baseline metrics, properly executed sweep, clear result table/graph, physical interpretation referencing the rocket equation / 評分標準：正確基準指標、正確執行掃描、清晰結果表格或圖表、引用火箭方程式的物理解釋 |

---

## 4. Common Pitfalls & Tips 常見問題與建議

| Pitfall 問題 | Tip 建議 |
|------------|---------|
| Adjusting too many knobs at once 同時調整太多參數 | Emphasize: change *one* variable at a time in Trade Study 1 / 強調：第一項研究每次只改一個變數 |
| Confusing Isp with propellant mass 混淆比衝與推進劑質量 | Remind: Isp = "quality" (engine), propellant mass = "quantity" / 提醒：比衝 = 「品質」（發動機特性），推進劑質量 = 「數量」 |
| Over-interpreting absolute numbers 過度解讀絕對數值 | Reiterate: this is a teaching model — focus on trends, not exact Falcon 9 performance / 重申：這是教學模型 — 著重趨勢，而非精確的獵鷹 9 號性能 |
| Simulation shows no orbit / warnings 模擬未達軌道或出現警告 | Often caused by very low TWR or insufficient propellant — use the baseline template as a sanity anchor / 通常因推重比過低或推進劑不足，建議回到基準模板重新確認 |

---

## 5. Optional Extensions 選修延伸活動

If you have a second lab session or homework assignment:  
若有第二次實驗課或作業：

- **Excel / Python comparison**: Ask students to replicate their S2 Isp sweep results using the rocket equation directly (no trajectory) and compare against the simulator.  
  **Excel / Python 比較**：讓學生直接用火箭方程式重現 S2 Isp 掃描結果，並與模擬器比較。
- **Custom engine**: Have students add or modify an engine in the **Engine Library** tab, then re-run their trade studies with the new engine applied.  
  **自訂發動機**：讓學生在 **Engine Library** 頁籤新增或修改發動機，套用後重新執行研究。
- **Trajectory analysis**: Use the **Trajectory Globe** outputs to discuss max-Q, gravity losses, and staging altitudes.  
  **軌跡分析**：利用 **Trajectory Globe** 頁籤輸出，討論最大動壓、重力損失與分節高度。
- **Lab report**: Write a 1–2 page mini-report in the style of an engineering trade study: problem statement, method, results (with figures), and conclusion.  
  **實驗報告**：撰寫 1–2 頁工程權衡研究格式的小型報告：問題定義、方法、結果（含圖表）、結論。

---

## 6. Quick-Reference: Key Parameter Ranges 快速參考：關鍵參數範圍

| Parameter 參數 | Baseline (Falcon-like) 基準值 | Suggested Sweep Range 建議掃描範圍 |
|---------------|---------------------------|--------------------------------|
| S2 Vacuum Isp | 380 s | 320–400 s |
| S1 propellant mass 第一節推進劑 | 411,000 kg | 350,000–450,000 kg |
| S2 propellant mass 第二節推進劑 | 107,500 kg | 80,000–130,000 kg |
| S2 dry mass 第二節乾重 | 4,000 kg | 3,000–6,000 kg |
| Payload mass 酬載質量 | 20,000 kg | 10,000–25,000 kg |
| Target altitude 目標高度 | 280 km | 200–600 km |

---

*For questions or contributions, open an issue or pull request at [github.com/RhynoW/rocket-edu-sim](https://github.com/RhynoW/rocket-edu-sim).*
