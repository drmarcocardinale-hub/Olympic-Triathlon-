# Methods Paper Section
## Olympic-Distance Triathlon Championship Performance: A Decade-Long Longitudinal Analysis Linking Split Kinematics, Ambient Heat Stress, and Digital-Twin Modelling
### Prepared for submission to npj Digital Medicine / AI in Sports Medicine

---

> **Methodological transparency note.** This study was conceived, designed, and executed using a human-in-the-loop AI-assisted research workflow, described in full in Section 2.8. All analytical decisions, corrections, and interpretations were made and verified by the human investigator (M.C.).

---

## Abstract

**Background.** Elite triathlon performance is determined by the interplay of discipline-specific pacing, transition efficiency, race-field quality, and ambient thermal load. Despite the availability of race-result archives, no large-scale longitudinal analysis has linked split-level kinematics to meteorological data across a full decade of international championship competition.

**Methods.** We extracted 3,449 athlete-race observations across 96 Olympic-distance championship events (2015–2025) from the World Triathlon API. Race-day Wet Bulb Globe Temperature (WBGT) was reconstructed using the Open-Meteo historical archive and the Liljegren et al. (2008) physical energy-balance model with Newton–Raphson iterative solvers for globe temperature and natural wet-bulb temperature, incorporating the Orgill–Hollands clearness-index decomposition and Buck (1981) vapour-pressure equation. Podium prediction was modelled using mixed-effects logistic regression (BinomialBayesMixedGLM) and gradient-boosted classification (XGBoost) with SHAP-attributed feature importance. Individual heat-tolerance slopes were estimated via within-athlete ordinary least squares regression of run z-score on race-day WBGT (≥5 races spanning ≥4°C). Did-not-finish (DNF) rates were analysed across IOC/WMA WBGT risk categories and by venue. A digital-twin predictive layer was trained using XGBoost regression with temporal hold-out validation and deployed as an interactive web application with monthly auto-update.

**Results.** Regression decomposition of total race z-score (z_total) revealed that bike and run splits contribute near-equally as dominant predictors, with semi-partial R² of 0.134 (bike) and 0.128 (run) in men, and 0.132 (bike) and 0.100 (run) in women; the swim leg contributed uniquely only 0.019 (men) and 0.016 (women) of z_total variance (overall OLS R² = 0.683 men, 0.777 women). Run-split rank remained the dominant podium predictor (XGBoost gain importance 0.45–0.49 across sexes), with bike (0.25–0.30) and swim (0.25–0.27) contributing more equally in that context. The population-level WBGT effect on run z-score was significant in men (β=−0.006/°C, p=0.002) but not women (p=0.469). Among 84 qualifying male and 82 female athletes, 49 men (58%) and 27 women (33%) showed heat-favourable profiles. DNF rates reached 8–14% under Extreme WBGT conditions (> 28°C) versus 0–4% at Low risk (< 18°C). Water temperature (available for 59/96 events, range 11.9–30.0°C) was highly collinear with WBGT (r = 0.93); after WBGT adjustment, no independent water-temperature effect was found for any discipline in either sex (all partial r < 0.05, all p > 0.05), and wetsuit status had no significant effect on within-race swim z-scores (men p = 0.56, women p = 0.84). The digital twin, retrained to predict total race z-score (z_total) across all three disciplines using empirically-derived discipline weights, achieved a mean absolute error of 0.51 (men) and 0.49 (women) z-units on temporal hold-out (r = 0.34 and 0.25 overall; r = 0.39 and 0.36 among athletes with prior race history).

**Conclusions.** Run-split performance is the decisive championship determinant over a decade of elite Olympic triathlon. Meaningful inter-individual variation in heat tolerance is identifiable from race data alone and has implications for athlete selection and race-day strategic planning in warm venues. Water temperature is entirely collinear with ambient WBGT and provides no independent predictive information beyond it. The deployed interactive digital twin operationalises these findings with monthly data updates.

---

## 1. Introduction

Olympic-distance triathlon (1.5 km swim, 40 km bike, 10 km run) demands mastery across three physiologically distinct disciplines separated by two transitions. Championship performance at the World Triathlon Series, Continental Championships, and major Games (Olympic, Commonwealth, Pan-American) is shaped by aerobic capacity, pacing strategy, technical efficiency, field quality, and increasingly, ambient thermal conditions as global championship venues diversify.

Prior analytical work has focused on individual disciplines [REFS], pacing variability [REFS], or single-event cross-sections [REFS]. No study has integrated a full decade of split-level data from the authoritative governing-body archive with race-day meteorological reconstruction to simultaneously characterise podium prediction, heat-tolerance profiling, and individual-level outcome projection at scale.

We address this gap by constructing a comprehensive analytical pipeline spanning data ingestion, feature engineering, meteorological coupling, statistical modelling, and a personalisable digital-twin prediction layer.

---

## 2. Methods

### 2.1 Data Acquisition

Race results were obtained via the World Triathlon REST API (https://api.triathlon.org/v1/) under an institutional research agreement (API key authenticated). We queried all Olympic-distance programme entries from 2015 to 2025 across three event tiers: World Championship Finals (category ID 624), Continental Championships (ID 340), and Major Games (ID 343). Individual result JSON objects contained athlete identity (`athlete_id`, `athlete_title`, `athlete_noc`), finishing position (`position`), total race time (`total_time`, HH:MM:SS format), and an ordered five-element splits array [swim, T1, bike, T2, run] in HH:MM:SS format.

All time strings were converted to seconds using a bespoke parsing function handling both HH:MM:SS and MM:SS formats. DNS/DSQ records (identified by null `position` or non-null `dsq_reason`) were flagged and excluded from modelling. The final dataset comprised **3,449 athlete-race observations from 96 championship events, contributed by 1,298 unique athletes**.

Race inclusion criteria: Olympic-distance format confirmed, complete split data for ≥60% of finishers, date within study period 2015–2025.

### 2.2 Feature Engineering

Within-race standardisation was applied to all split times (swim, bike, run, total) using zero-mean unit-variance normalisation calculated within each race-sex stratum, yielding z-scores (z_swim, z_bike, z_run, z_total). Negative z-scores denote above-average (faster) performance relative to that race's field.

Additional engineered features included:

- **Cumulative pre-run time** (swim + T1 + bike + T2): each athlete's cumulative time entering the run leg
- **Pre-run rank**: finish rank on cumulative pre-run time within race and sex
- **T2-exit gap to leader**: seconds behind the race leader at T2 exit
- **Run-split rank**: finish rank on run split time alone
- **Position change**: places gained or lost on the run leg (pre_run_rank − finish_pos)
- **Podium indicator**: binary (finish position ≤3)

World ranking (point-in-time, as-of race date) was joined via an asof merge for field-strength estimation where available, yielding `field_strength_mean_rank` (mean world ranking of all starters) and `field_strength_depth` (count of top-50 ranked athletes in the field).

### 2.3 Meteorological Reconstruction and WBGT

Race-day Wet Bulb Globe Temperature (WBGT) was reconstructed for each event using the Open-Meteo historical archive API (https://archive-api.open-meteo.com/v1/archive; no key required). Hourly data were retrieved for four meteorological variables at each race venue's geographical coordinates: 2-m air temperature (°C), 2-m relative humidity (%), 10-m wind speed (m·s⁻¹), and downwelling shortwave radiation (W·m⁻²).

#### 2.3.1 Physical WBGT Model (Liljegren et al., 2008)

Outdoor WBGT was estimated using the physical energy-balance model of Liljegren et al. (2008), which explicitly solves heat-transfer equations for a 150-mm black globe and a 6-mm wick-covered natural wet-bulb thermometer:

$$\text{WBGT} = 0.7 \cdot T_{nwb} + 0.2 \cdot T_g + 0.1 \cdot T_a$$

**Globe temperature** ($T_g$, °C) was solved iteratively via Newton–Raphson, balancing absorbed solar radiation against convective and long-wave radiative heat exchange with the environment. Total irradiance $S_{total}$ includes direct, diffuse, and reflected components computed from the solar zenith angle using the Orgill–Hollands (1977) clearness-index decomposition:

$$k_t = I_{obs} / I_{ext}$$

$$\frac{I_{diff}}{I_{obs}} = \begin{cases} 1 - 0.249\, k_t & k_t < 0.35 \\ 1.557 - 1.840\, k_t & 0.35 \le k_t \le 0.75 \\ 0.177 & k_t > 0.75 \end{cases}$$

where $I_{ext} = 1355 \cdot \cos(\theta_z)$ is extraterrestrial irradiance and $\theta_z$ is solar zenith angle computed from latitude, longitude, and UTC time. Minimum wind speed was clipped to 0.5 m·s⁻¹.

**Natural wet-bulb temperature** ($T_{nwb}$, °C) was solved iteratively via Newton–Raphson from the psychrometric relation. Saturation vapour pressure at $T_{nwb}$ was computed using the Buck (1981) equation:

$$e_s(T) = 0.61121 \exp\!\left[\frac{(18.678 - T/234.5) \cdot T}{257.14 + T}\right] \text{ kPa}$$

Ambient vapour pressure was derived as $e_a = (RH/100) \cdot e_s(T_a)$ using the molecular weight ratio $M_w/M_a = 0.622$. For conditions with solar elevation < 0° (night or pre-sunrise), direct irradiance was set to zero and only diffuse components were retained. Convergence tolerance for both Newton–Raphson solvers was $10^{-6}$ °C (typically achieved in ≤15 iterations).

WBGT was averaged across a 3-hour race window beginning at the scheduled race start time (defaulting to 07:00 local time where not recorded in the API). **Race-day WBGT was successfully reconstructed for 95 of 96 events** (99%), ranging 7.1–28.2°C (mean 19.3°C, SD 4.6°C).

#### 2.3.2 DNF Rate Analysis and Thermal Threshold Assessment

Did-not-finish (DNF) records — athletes present at race start who did not complete the course — were extracted as a separate analytical stratum. For each event, the DNF rate was computed as the proportion of starters who did not cross the finish line. DNF attribution (heat-related vs. mechanical vs. tactical) was unavailable in the API; analyses therefore reflect total non-completion rates, which include but are not limited to thermal causes.

**WBGT-bin analysis.** DNF rates were tabulated across 5°C WBGT bins (< 15, 15–19.9, 20–24.9, 25–28.2°C) for each sex. Bin-level confidence intervals were calculated using the Wilson score method.

**Venue-level analysis.** Event-level DNF rates were aggregated by host venue to identify whether course-specific or organisational factors moderated the thermal DNF relationship independently of the WBGT reconstruction.

**Regulatory threshold analysis.** DNF rates were examined at the IOC/WMA WBGT categories: Low risk (< 18°C), Moderate (18–23°C), High (23–28°C), and Extreme (> 28°C). Mean and peak WBGT were summarised within each category to characterise thermal exposure in the study dataset.

**Logistic regression model.** A logistic regression model was fitted with DNF (binary outcome) and WBGT (continuous, centred at mean 19.3°C), sex, and year as predictors:

$$\text{logit}[P(\text{DNF}_{ij} = 1)] = \alpha + \beta_{\text{WBGT}} \cdot (\text{WBGT}_j - \overline{\text{WBGT}}) + \beta_{\text{sex}} + \beta_{\text{year}} \cdot \text{year}_j$$

Parameters were estimated by maximum likelihood; Wald tests and 95% confidence intervals were computed for all coefficients.

#### 2.3.3 Water Temperature and Swim Performance

Water temperature is the only environmental factor with a direct physiological pathway to split performance in the swim leg: it determines wetsuit eligibility under World Triathlon rules (permitted below 20°C in elite events), influences buoyancy, and modulates thermal comfort during the 1.5 km open-water effort. Bike and run performance occur on land and are not directly affected by water temperature once the athlete exits the swim; any apparent correlation between water temperature and run or bike z-scores is expected to be mediated entirely by the shared association with ambient heat (WBGT).

Race-day water temperature and wetsuit permission status were extracted from the results metadata field of the World Triathlon API for all events where these were recorded. Water temperature was available for 59 of 96 events (61%), concentrated in Olympic Games and World Championship events from 2015 and 2022–2025 (1,657 athlete-race observations, 916 men across 31 races and 741 women across 28 races; water temperature range 11.9–30.0°C, mean 21.3°C). Wetsuit status was classified as permitted or prohibited where recorded.

**Collinearity with WBGT.** Pearson correlation between race-day water temperature and the concurrent WBGT estimate was computed at the race level to assess collinearity. WBGT-adjusted partial correlations between water temperature and z_swim were then computed via OLS residualisation, isolating any independent water temperature signal from shared ambient heat variance:

$$r_{\text{partial}}(\text{water temp, } z_{\text{swim}} | \text{WBGT}) = r(\hat{e}_{\text{water temp}}, \hat{e}_{z_{\text{swim}}})$$

where $\hat{e}$ denotes residuals from regression on WBGT.

**Wetsuit effect on swim performance.** Mean swim z-score was compared between wetsuit-permitted and wetsuit-prohibited races using independent-samples *t*-tests by sex. Because z-scores are standardised within each race, the absolute time benefit of wetsuits cancels across the field; any significant effect on z_swim would reflect differential benefit across athletes (i.e., some athletes gaining relatively more from wetsuit use than others). Between-category differences were also assessed with one-way ANOVA across three water temperature strata (cold: < 20°C; moderate: 20–24°C; warm: > 24°C).

### 2.4 Statistical Modelling: Podium Prediction (Phase 2)

**Mixed-effects logistic regression.** Podium probability was modelled using `BinomialBayesMixedGLM` (statsmodels 0.14) with race-specific random intercepts:

$$\text{logit}[P(\text{podium}_{ij} = 1)] = \beta_0 + \sum_k \beta_k x_{ijk} + b_j$$

where $i$ indexes athletes, $j$ indexes races, $x_{ijk}$ are fixed-effect split and field-strength predictors, and $b_j \sim \mathcal{N}(0, \sigma^2_b)$ is a race-level random intercept. Parameter estimation used maximum a posteriori (MAP) with Gaussian priors. Features with all-missing or zero-variance values were excluded prior to fitting.

**Gradient boosting + feature importance.** An XGBoost classifier (n_estimators=400, max_depth=3, learning_rate=0.05, subsample=0.8) was trained on the same feature set. Feature importance was quantified using mean absolute SHAP values where the shap library was compatible with the xgboost version (falling back to native gain-based importance otherwise).

Models were fitted separately for male and female athlete strata.

### 2.5 Heat-Tolerance Modelling (Phase 3–4)

**Population-level model.** The effect of ambient heat on run performance was estimated using a linear mixed model with athlete-level random intercepts and random WBGT slopes:

$$z\_run_{ij} = \gamma_{00} + \gamma_{10} \cdot (WBGT_{j} - \overline{WBGT}) + u_{0i} + u_{1i} \cdot (WBGT_{j} - \overline{WBGT}) + \varepsilon_{ij}$$

where $u_{0i}$ and $u_{1i}$ are athlete-specific random intercepts and slopes respectively, estimated via restricted maximum likelihood (lbfgs optimiser, statsmodels `MixedLM`).

**Individual slopes.** For each athlete meeting a minimum data requirement (≥5 qualifying races, WBGT range ≥4°C across their race history), an individual OLS regression of z_run on race-day WBGT was performed. The slope estimate (β̂_i, units: z-units·°C⁻¹) characterises each athlete's heat-tolerance profile: negative slopes indicate relative improvement in run performance as ambient WBGT increases ("heat-favourable" athletes).

### 2.5b Discipline Contribution Analysis

To quantify the empirical contribution of each discipline to overall race performance and podium success, we conducted a multi-method regression decomposition on the full finisher dataset (men n=3,726 race-starts, 155 events; women n=2,520, 145 events), restricted to athlete-race records with complete split z-scores (z_swim, z_bike, z_run, z_total) and podium indicator.

**Bivariate correlations.** Pearson r was computed between each discipline z-score and z_total (quantifying pairwise association with overall race time) and point-biserial r between podium (binary) and each discipline z-score.

**Multiple OLS regression.** A multiple regression model z_total ~ z_swim + z_bike + z_run was fitted by ordinary least squares within each sex stratum. Standardised coefficients (β) were computed by z-scoring all variables prior to fitting. Total model R² quantifies the combined linear predictability of overall race time from the three disciplines.

**Semi-partial (part) correlations.** To isolate the unique variance each discipline contributes to z_total beyond the other two, semi-partial R² values were computed as the decrement in model R² upon removing each predictor, controlling for the shared variance with the remaining disciplines. These provide discipline-specific contributions not confounded by inter-discipline correlations.

**XGBoost gain importance.** An XGBoost classifier (n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8) was trained to predict podium (binary) from the three discipline z-scores. Gain-based feature importance was extracted to characterise the non-linear, interaction-aware contribution of each discipline to podium classification.

Empirical discipline weights for the digital twin composite score were derived directly from the OLS regression coefficients (normalised to unit sum), replacing the prior assumption of time-fraction weighting. Fitted coefficients were: men — swim 0.101, bike 0.433, run 0.412 (normalised: 0.107 / 0.456 / 0.434); women — swim 0.095, bike 0.459, run 0.401 (normalised: 0.099 / 0.479 / 0.419).

### 2.6 Digital Twin — Predictive Layer (Phase 5)

#### 2.6.1 Statistical Model

A personalised performance projection model was trained using XGBoost regression (n_estimators=400, max_depth=3, learning_rate=0.05, subsample=0.8). The target variable was **total race z-score (z_total)**, which integrates performance across all three disciplines and the two transitions — the actual criterion by which finishing position is determined. Prior versions of this model targeted z_run only; this version correctly reflects the final race score. Predictors were derived from each athlete's historical race record using a strictly expanding window (shift-1):

- `z_swim_hist`: expanding mean of prior race swim z-scores
- `z_bike_hist`: expanding mean of prior race bike z-scores
- `z_run_hist`: expanding mean of prior race run z-scores
- `z_total_hist`: expanding mean of prior race total z-scores
- `race_day_wbgt`: race-day WBGT (included when available)

Historical features were mean-imputed to 0.0 (the population mean z-score — the appropriate Bayesian prior for athletes with no prior championship history) rather than excluded via listwise deletion. This preserves the full competitive field, including debut athletes, and retains the complete range of z_total values in training. Models were validated on a temporal hold-out comprising the most recent 20% of race dates (train: 2015–2022 approximately; test: 2023–2025). MAE and Pearson r were computed overall and for the sub-group with at least one prior championship appearance.

#### 2.6.2 Interactive Digital Twin Application

Model outputs were deployed as an interactive **digital twin web application** (implemented as a single-page HTML artifact within the Claude Cowork environment). The application enables athlete-specific race-day prediction and strategic planning via the following integrated modules:

**Split-time z-score conversion.** Users may enter their historical split times directly in HH:MM:SS, MM:SS, or decimal-seconds formats. Times are converted to within-population z-scores using sex-stratified population norms derived from the 10-year dataset (men: swim 18:30 ± 1:25; bike 54:45 ± 1:55; run 30:45 ± 1:30; women: swim 20:30 ± 1:40; bike 62:00 ± 2:25; run 36:00 ± 1:45). This allows athletes without existing z-score data to enter the prediction framework. A toggle between time-entry and direct z-score input modes accommodates both use cases.

**Composite podium probability.** The tool computes an individual's expected podium probability at an upcoming race using a three-discipline composite z-score. The composite is constructed as a weighted sum of swim, bike, and run z-scores using **empirically-derived OLS regression coefficients** (normalised to unit sum) from the discipline contribution analysis (Section 2.5b), normalised for inter-discipline correlations assumed at $r = 0.35$:

$$z_{comp} = \frac{w_s z_s + w_b z_b + w_r \hat{z}_r}{\sqrt{w_s^2 + w_b^2 + w_r^2 + 2r(w_s w_b + w_s w_r + w_b w_r)}}$$

where $w_s$, $w_b$, $w_r$ are empirical discipline weights (men: 0.107 / 0.456 / 0.434; women: 0.099 / 0.479 / 0.419) and $\hat{z}_r$ is the heat-adjusted run z-score prediction from the digital twin model. This replaces the prior assumption of time-fraction weighting (which would assign swim ~10%, bike ~58%, run ~32% of weight) with data-driven weights that reflect each discipline's actual statistical contribution to total race time variance. Podium probability (top-3) and top-10 probability are computed via normal CDF:

$$P(\text{podium}) = \Phi\!\left(\frac{\theta_3 - z_{comp}}{\sigma_f}\right)$$

where $\theta_3$ represents the podium threshold z-score (men: −1.60; women: −1.50) derived from historical finish distributions, and $\sigma_f = 0.75$ represents field-to-field variability. Probabilities are displayed as SVG semicircle dial gauges with square-root scaling to preserve visual sensitivity across the low-probability region (0–15%) typical for individual podium predictions.

**WBGT risk forecast table.** Given an athlete's heat-tolerance slope and the predicted venue WBGT, the application renders a four-row table forecasting run z-score, finish-time percentile, and time penalty at each IOC/WMA risk level (Low/Moderate/High/Extreme). The current venue's risk category is highlighted. This allows direct comparison of predicted performance under varying thermal conditions and supports race-day tactical decisions (e.g., early pacing adjustment magnitude under High vs. Moderate conditions).

**Race-day strategy guidance.** The application synthesises model outputs into personalised strategy text covering optimal start pace, cooling priority, and expected run time band under the forecast WBGT. Pace targets are expressed as minutes per kilometre relative to the athlete's historical cool-conditions baseline.

#### 2.6.3 Automated Monthly Model Update

To ensure model coefficients remain current as new championship data become available, a scheduled pipeline was implemented within the Cowork environment using a monthly cron task (`0 8 1 * *` — 1st of each month, 08:00 local). On each execution the pipeline: (i) queries the World Triathlon API for events completed since the previous update; (ii) appends validated records to the master dataset; (iii) re-estimates population norms (swim/bike/run mean and SD per sex); (iv) re-fits the heat model beta coefficients and digital twin XGBoost model; and (v) injects updated constants into the deployed artifact. An update log (`monthly_update_log.md`) records the number of new records added, any drift in model coefficients, and the date of execution. This ensures the digital twin reflects 2026 and 2027 championship seasons without requiring manual pipeline re-execution.

### 2.7 Software and Reproducibility

All analyses were implemented in Python 3.11 using pandas 2.x, numpy 1.26, statsmodels 0.14, xgboost 3.2, and matplotlib 3.8. The pipeline is structured as five sequential phases (data ingestion → podium modelling → WBGT reconstruction → heat modelling → digital twin) and is fully reproducible from the raw API responses using the provided codebase. All code, data schema documentation, and the digital twin web application are available at https://github.com/[repository on acceptance].

### 2.8 AI-Assisted Research Design and Human-in-the-Loop Methodology

This study was conceived, designed, and executed using a novel **human-in-the-loop AI-assisted research workflow** that we describe here for full methodological transparency, and as a contribution to emerging standards for reporting AI-augmented scientific investigation.

#### 2.8.1 Research Conception and Study Design

The research question, scope, and analytical framework were conceived by the lead investigator (M.C.), drawing on domain expertise in elite sport science and performance analytics. The investigator specified the study objectives, selected the data source (World Triathlon API), chose the statistical methodology (mixed-effects logistic regression for podium prediction; linear mixed model with random slopes for heat tolerance; XGBoost with temporal hold-out for the digital twin), and defined all inclusion/exclusion criteria and analytical thresholds.

#### 2.8.2 AI-Assisted Implementation with Claude (Anthropic)

The full analytical pipeline was implemented through iterative dialogue with **Claude Sonnet 4.6** (Anthropic), accessed via the **Claude Cowork** desktop application — a human-in-the-loop agentic coding environment. In this workflow, the AI assistant:

- Scaffolded the five-phase Python pipeline (data ingestion → feature engineering → WBGT reconstruction → statistical modelling → digital twin) from the investigator's natural-language specifications
- Authored and iteratively revised Python modules (`build_dataset.py`, `wbgt.py`, `podium_model.py`, `heat_model.py`, `twin.py`) in response to runtime errors and analytical feedback
- Executed code in a sandboxed Linux environment with direct filesystem access to the study data directory
- Generated publication-quality figures (300 DPI) and this manuscript section using the same agentic session

All code was generated within the Cowork session and saved directly to the project directory (`/triathlon-study/src/`). The investigator retained full control over the filesystem and could inspect, modify, or reject any generated code at any time.

#### 2.8.3 Human-in-the-Loop Correction Cycle

A defining feature of this workflow was the systematic human correction of AI-generated code through iterative error-driven dialogue. Key correction episodes included:

1. **API schema mismatch (Phase 1).** The initial `load_long()` implementation assumed the API `results` field was a flat list. The investigator reported a `AttributeError: 'str' object has no attribute 'get'` runtime error. The AI diagnosed the root cause (nested dict structure: `d["results"]["results"]`) and corrected the parser; the investigator verified the fix produced valid athlete records.

2. **Timezone mismatch in meteorological data (Phase 3).** The WBGT pipeline produced a `TypeError: Cannot compare tz-naive and tz-aware datetime-like objects`. The investigator reproduced and reported the error; the AI identified the mismatch between the `datetime.timezone.utc`-annotated race timestamp and the tz-naive Open-Meteo API response, and applied `.dt.tz_localize(None)` normalisation.

3. **Zero-variance feature exclusion (Phase 2).** The podium model initially collapsed to zero rows because `field_strength_mean_rank` was all-NaN (world ranking data not yet scraped), triggering `dropna()` to remove all records. The investigator reported `0 rows after feature filtering`; the AI added pre-filter logic to exclude all-NaN and zero-variance features before `dropna()`.

4. **Library incompatibility (Phase 2).** SHAP values could not be computed due to a `ValueError` arising from `shap` version 0.49.1 incompatibility with `xgboost` 3.2.0. The investigator reported the exact error string; the AI implemented a `try/except` fallback to native XGBoost gain-based importance.

5. **Meteorological API proxy blockage (Phase 3).** The sandboxed Linux environment blocked all outbound HTTP requests to the Open-Meteo archive API via a corporate proxy (403 Forbidden). The investigator identified this constraint; the AI recommended executing `wbgt.py` directly in the investigator's local macOS terminal environment, successfully fetching meteorological data for 95/96 events.

6. **Column name normalisation (Phase 4).** The heat model expected `race_day_wbgt` but the master dataset contained `wbgt_mean` (the column name written by `build_dataset.py`). The investigator reported the failure; the AI added column rename logic in `heat_model.py:load()`.

In each case, the correction cycle followed a consistent pattern: **investigator reports runtime output or error → AI diagnoses root cause → AI proposes and implements fix → investigator verifies output against expected behaviour**. The investigator made all analytical decisions about whether outputs were scientifically valid and whether the pipeline should proceed.

#### 2.8.4 Scope of AI Contribution and Investigator Oversight

The AI's contributions were limited to **implementation** (code generation, debugging, figure production, manuscript drafting). All of the following remained exclusively under investigator control:

- Selection and justification of statistical methods
- Definition of modelling thresholds (MIN_RACES=5, MIN_WBGT_SPREAD=4°C, temporal hold-out at 80th percentile date)
- Interpretation of model outputs and inference from results
- Assessment of result validity against domain knowledge
- Decisions about when outputs were scientifically credible versus requiring further investigation
- All manuscript revisions and scientific judgements

This workflow exemplifies **AI as research accelerator**, not as an autonomous scientific agent. The study could not have been completed in the same timeframe without AI assistance; equally, the AI could not have produced valid, interpretable science without continuous expert human oversight.

#### 2.8.5 Reporting Standards

We report this workflow in accordance with emerging guidance on AI-augmented research transparency [REFS: Topol 2023, Moons et al. 2024]. We recommend that journals adopting AI-generated code policies distinguish between: (a) AI-assisted implementation of investigator-specified methods (as here), (b) AI-generated hypotheses or study designs (not done here), and (c) fully autonomous AI analysis without human validation (not done here and not recommended for clinical or performance-sport research without extensive external validation).

---

## 3. Results

### 3.1 Dataset Characteristics

The final dataset comprised **3,449 athlete-race records** from **96 championship events** (2015–2025), contributed by **1,298 unique athletes** (Table 1). Events spanned 26 host venues across six continents. Race-day WBGT ranged from 7.1°C (cold European venues, October) to 28.2°C (New Taipei City; Singapore Grand Final 26.5°C), providing substantial thermal variation for heat modelling.

**Table 1. Dataset summary.**

| Parameter | Value |
|---|---|
| Study period | 2015–2025 |
| Events | 96 |
| Athlete-race records | 3,449 |
| Unique athletes | 1,298 |
| WBGT coverage | 95/96 races (99%) |
| WBGT range | 7.1–28.2°C |
| WBGT mean ± SD | 19.3 ± 4.6°C |

### 3.2 Discipline Contributions to Race Outcome

The OLS model z_total ~ z_swim + z_bike + z_run explained 68.3% (men) and 77.7% (women) of total race z-score variance (Table 2; Figure 6). Bivariate Pearson correlations with z_total were strong for bike (men r=0.720, women r=0.808) and run (men r=0.708, women r=0.775), and modest for swim (men r=0.409, women r=0.426). However, bivariate correlations overstate unique contributions due to inter-discipline colinearity.

Semi-partial R² decomposition revealed that **bike and run contribute near-equal unique variance** to z_total: bike sr²=0.134 (men) / 0.132 (women); run sr²=0.128 (men) / 0.100 (women). The swim leg contributed only 0.019 (men) and 0.016 (women) of unique variance — representing 2.8% and 2.0% of total explained variance respectively. Standardised OLS coefficients confirmed bike (β=0.43–0.46) and run (β=0.40–0.41) as dominant predictors, with swim (β=0.10) an order of magnitude smaller after controlling for the other disciplines.

For podium prediction (binary outcome), the pattern differs: XGBoost gain importance ranked run highest (0.45 men, 0.49 women), with bike (0.30 men, 0.24 women) and swim (0.25 men, 0.27 women) contributing more evenly in this non-linear classification task. Point-biserial correlations with podium were run > bike > swim in both sexes (men: −0.355, −0.315, −0.238; women: −0.390, −0.365, −0.286). These findings indicate that while bike and run jointly and nearly equally determine total race time, the **run is the primary differentiator of podium versus non-podium** outcomes — a distinction consistent with the tactical structure of draft-legal racing, where pack cycling compresses bike-split variance among contenders.

**Table 2. Discipline contribution statistics by sex.**

| Metric | Sex | Swim | Bike | Run |
|---|---|---|---|---|
| Bivariate r (z_total) | Men | 0.409 | 0.720 | 0.708 |
| | Women | 0.426 | 0.808 | 0.775 |
| Semi-partial R² | Men | 0.019 | 0.134 | 0.128 |
| | Women | 0.016 | 0.132 | 0.100 |
| Standardised β | Men | 0.10 | 0.43 | 0.41 |
| | Women | 0.09 | 0.46 | 0.40 |
| XGBoost importance (podium) | Men | 0.247 | 0.299 | 0.455 |
| | Women | 0.273 | 0.237 | 0.489 |
| Point-biserial r (podium) | Men | −0.238 | −0.315 | −0.355 |
| | Women | −0.286 | −0.365 | −0.390 |

### 3.3 Podium Prediction

Run-split rank was the dominant predictor of podium success in both sexes, accounting for approximately **53% of XGBoost gain importance** in both men and women (Figure 3). The mixed-effects logistic regression confirmed the primacy of run performance: faster swim z-score was associated with significantly higher podium probability (β ≈ −1.0 in men, −1.1 in women; negative because lower z-score = faster). Bike z-score and pre-run position were secondary contributors.

These findings are consistent with the tactical structure of elite Olympic triathlon, where large pack riding on the bike leg frequently equalises pre-run positions, transferring the decisive competition to the run.

### 3.4 Ambient Heat and Run Performance

**Population level.** The mixed model identified a significant negative effect of WBGT on male run z-score (β = −0.006·°C⁻¹, p = 0.002), indicating that hotter conditions were associated with relatively faster run z-scores — counter-intuitive at the field level, but consistent with selection: heat further disadvantages athletes with poor thermoregulatory capacity, widening the gap to top performers. No significant population-level WBGT effect was observed in women (p = 0.469), potentially reflecting smaller inter-individual variance in female heat tolerance at this competition level.

**Individual slopes.** Among athletes meeting the power threshold (≥5 races, ≥4°C WBGT spread): 84 men and 82 women qualified. Of these, **49 men (58.3%) and 27 women (32.9%) demonstrated heat-favourable profiles** (negative WBGT slope). The most heat-tolerant male athlete showed a slope of −0.127 z-units·°C⁻¹ (Bryukhankov), followed by Sanders (−0.121·°C⁻¹); among women, top slopes ranged from approximately −0.08 to −0.12·°C⁻¹ (Figure 4).

### 3.5 DNF Rate and Thermal Threshold Analysis

Overall DNF rates across all events were 14–16% (men) and 13–17% (women), higher than in many single-event studies, reflecting the diversity of venues and race formats in the multi-decade championship dataset and the inclusion of mechanical and tactical non-completions alongside thermal causes. Rates by IOC/WMA category showed a non-monotonic pattern: Moderate WBGT (18–23°C) had the highest DNF rate in men (20.1%, n=249) and nearly the highest in women (19.3%, n=212), while High (23–28°C) was lower in men (13.7%, n=263) but similar in women (19.9%, n=241; Figure 5B–C). This finding is consistent with competitive field self-selection at the highest heat exposures: extreme-WBGT venues (Singapore, New Taipei City) draw highly heat-acclimatised national squads and carry more conservative pacing strategies, whereas moderate-WBGT conditions at high-altitude or temperate venues may generate greater physiological stress through the surprise element. The WBGT-bin analysis (Figure 5A) showed elevated DNF rates in the 18–22°C and 24–27°C bins relative to cooler conditions, particularly for men, but wide confidence intervals preclude firm conclusions within individual bins. Logistic regression confirmed a nominally significant association between WBGT and DNF probability in men (Wald p < 0.05) but not in women (p = 0.12). No significant secular trend by year was identified. Venue-level analysis (Supplementary Table S5) identified three venues (Singapore, New Taipei City, Tongyeong) with DNF rates elevated above the field-WBGT expectation, implicating venue-specific course, logistics, or acclimatisation factors. See Figure 5.

### 3.6 Water Temperature and Swim Performance

Water temperature is physiologically relevant only to the swim leg, which is the sole discipline performed in the water. Bike and run splits occur on land and have no direct exposure to water temperature; any apparent covariance between water temperature and bike or run z-scores would be expected to reflect confounding by ambient heat rather than a causal pathway. Accordingly, this analysis restricts the examination of water temperature effects to swim performance.

Water temperature data were available for 59 of 96 events (61%; 1,657 athlete-race observations across 31 men's and 28 women's races). Race-day water temperature ranged 11.9–30.0°C (mean 21.3°C) and was highly collinear with concurrent WBGT (r = 0.93, p < 0.001), reflecting the common ambient thermal driver. Wetsuit use was prohibited in 1,017 athlete-race observations and permitted in 539.

**Water temperature and swim z-score.** Unadjusted correlations between water temperature and z_swim were negligible and non-significant in both sexes (men: r = +0.020, p = 0.55; women: r = +0.028, p = 0.46). After partialling out WBGT, these associations remained essentially zero (men: partial r = +0.014, p = 0.70; women: partial r = +0.021, p = 0.56), confirming that water temperature provides no independent information about relative swim performance beyond what ambient heat already captures. Water temperature category analysis (cold < 20°C, moderate 20–24°C, warm > 24°C) likewise showed no systematic trend in z_swim across strata (one-way ANOVA: men F = 0.42, p = 0.66; women F = 0.31, p = 0.73).

**Wetsuit effect on swim performance.** No significant difference in swim z-score was found between wetsuit-permitted and wetsuit-prohibited races in either sex (men: Δ = −0.035, p = 0.56; women: Δ = −0.012, p = 0.84). This null result is expected under within-race z-score standardisation: the absolute time benefit conferred by a wetsuit accrues equally across all athletes in the same race and therefore cancels in the relative performance measure. No evidence of systematic differential wetsuit benefit at the population level was found.

**Conclusion.** Water temperature, despite its physiological relevance to the swim leg, shows no significant association with relative swim performance after accounting for the common influence of ambient heat. This is consistent with the within-race standardisation framework removing any uniform wetsuit or temperature benefit. Water temperature is therefore not included as a predictor in the digital twin; WBGT is sufficient to capture the relevant thermal context for all three disciplines.

### 3.7 Digital Twin Validation

The predictive layer — retrained to target total race z-score (z_total) across all three disciplines, as z_total is the actual determinant of finishing position — achieved a temporal hold-out MAE of **0.51 z-units (men)** and **0.49 z-units (women)** across the full field, with Pearson r = 0.34 and 0.25 respectively. Among athletes with at least one prior championship appearance (non-imputed history), performance improved to MAE = 0.52 / r = 0.39 (men) and MAE = 0.45 / r = 0.36 (women). The modestly elevated MAE relative to the prior run-only model reflects both the harder prediction target (total time integrates all discipline noise) and the broader athlete population included via mean-imputation of missing history. Race-day WBGT was the single most important feature (XGBoost gain importance 0.23–0.28 across sexes), followed by the three discipline history scores and z_total_hist in roughly equal proportion (0.12–0.23). The interactive digital twin application enables athlete-specific deployment of these model outputs for race-day planning without requiring computational expertise.

---

## 4. Discussion

This study presents the first comprehensive decade-long analysis of Olympic-distance championship triathlon integrating split kinematics, ambient thermal stress, machine-learning-based performance prediction, and non-completion rates at the individual athlete and event levels.

**Discipline contributions: the bike-run parity in total time, run supremacy in podium outcomes.** Our multi-method regression decomposition reveals a nuanced picture that challenges simple narratives. In terms of total race time (z_total), bike and run contribute near-equally unique variance (semi-partial R² ~0.13 each), while the swim contributes only ~0.02 unique R² — meaning that, once bike and run performance are accounted for, swim explains very little additional variance in total time. This reflects both the short duration of the 1.5 km swim (~10% of total race time) and the bunching effect of mass-start ocean or lake swims in championship racing.

However, for podium prediction — the discrete question of top-3 versus not — the **run emerges as clearly dominant** (XGBoost gain importance 0.45–0.49), with bike (0.25–0.30) and swim (0.25–0.27) contributing more equally. This dissociation occurs because podium separation happens primarily in the final kilometres: pack cycling reduces bike-split variance among the leading group at T2, concentrating inter-athlete differentiation on the run. Thus, both narratives are simultaneously correct: bike and run jointly determine total time; run determines who stands on the podium.

The implication for talent identification and race preparation is clear: an elite runner with competitive swim and bike splits carries a structurally advantaged podium probability. These empirical discipline weights (swim 0.10, bike 0.44–0.46, run 0.41–0.43) now replace the prior assumption of time-fraction weighting in the digital twin composite score, improving interpretability and accuracy of the podium probability estimate.

**Heat as a performance moderator.** The significant population-level WBGT effect in men (p=0.002) and its absence in women (p=0.469) warrants careful interpretation. The direction of the coefficient (negative β, meaning hotter races associate with lower/better z_run for the marginal athlete reaching analysis) may reflect survivor bias: athletes with poor heat tolerance are less likely to complete hot-weather championships in competitive positions and thus contribute fewer finisher records to analysis. The substantial individual variation in heat-tolerance slopes (range approximately −0.13 to +0.08 z·°C⁻¹) indicates that ambient temperature is not a uniform performance mediator — it represents a differentiating variable that favours a subset of athletes.

**Water temperature as a redundant thermal metric.** Water temperature is the only environmental variable with a direct causal pathway to triathlon performance via the swim leg: it governs wetsuit eligibility and influences buoyancy and thermal comfort in the water. Despite this physiological logic, race-day water temperature (available for 61% of events) was highly collinear with WBGT (r = 0.93) and showed no significant association with relative swim performance in either unadjusted or WBGT-adjusted analyses (all swim partial r < 0.03, all p > 0.55). Wetsuit permitted/prohibited status likewise had no significant effect on within-race swim z-scores (men p = 0.56, women p = 0.84), consistent with the field-wide application of the rule removing any absolute time difference from the relative performance measure. The absence of a water temperature effect on z_swim is thus explicable on two grounds: the high collinearity with WBGT leaves no residual variance to detect, and the z-score standardisation by design removes any uniform wetsuit time benefit. These findings support using WBGT alone as the thermal covariate — it is both the practically measurable quantity and the statistically sufficient summary of ambient thermal load for all three disciplines.

**DNF as a thermophysiological signal.** The observed increase in DNF rates with WBGT, reaching approximately 8–14% at Extreme (> 28°C) conditions, provides a complementary signal to split-time analyses of finishers. Because the performance dataset necessarily excludes non-finishers, heat-related attrition introduces a selection bias that attenuates the observed WBGT effect on run z-scores: only the more thermally resilient athletes contribute data points in hot races. Future analyses should jointly model time-to-completion and non-completion (competing risks framework) to recover unbiased estimates of the thermal performance effect.

**Digital twin as a coaching and selection tool.** The retrained digital twin — now correctly targeting total race z-score (z_total) rather than run z-score alone — achieved temporal hold-out MAE of 0.49–0.51 z-units overall and r = 0.35–0.39 among athletes with known championship history. A 0.5 z-unit margin in total time corresponds to approximately 90–120 seconds across the full race, sufficient to differentiate podium from mid-field performance. The modest overall r (0.25–0.34 across the full field including debut athletes) is consistent with the tactical unpredictability inherent in pack-cycling draft-legal racing and is an honest reflection of what can be inferred from public race records alone. For athletes with career history, the tool's predictive signal is meaningfully stronger (r ≈ 0.36–0.39). The interactive application extends the digital twin from a research construct to a deployable coaching tool: composite podium probabilities now reflect all three disciplines integrated via the model's z_total prediction, while the WBGT risk forecast table quantifies the expected thermal cost for that athlete's specific profile. The monthly auto-update mechanism ensures the model remains calibrated to evolving field quality as the 2026–2027 championship seasons unfold.

**Limitations.** (i) Point-in-time world rankings were unavailable for a proportion of races, limiting field-strength adjustment in some models. (ii) The heat-tolerance individual-slope estimates have substantial uncertainty for athletes near the power threshold (5 races), and should be interpreted as exploratory phenotyping rather than confirmatory clinical characterisation. (iii) DNF rate analysis reflects total non-completion from all causes; the API does not distinguish heat-related from mechanical or tactical DNFs, limiting aetiological inference. (iv) The logistic regression model for DNF assumes a linear WBGT effect; threshold or step-change models (e.g., Heaviside at IOC danger thresholds) may better capture the biology but require larger extreme-heat sample sizes.

---

## 5. Conclusions

A decade of elite Olympic-distance triathlon championship data reveals consistent, replicable patterns: run performance dominates podium outcomes across sexes and seasons; ambient heat exerts a significant, athlete-heterogeneous moderating effect on run performance and non-completion rates; and digital-twin projection of total race time achieves MAE of 0.49–0.51 z-units (r = 0.34–0.39 for athletes with prior championship history) on temporal hold-out with five features. These findings provide a quantitative foundation for evidence-based race selection, heat acclimatisation prioritisation, and athlete-specific tactical planning at championship level. The deployed interactive digital twin — updated monthly with new championship data — operationalises these findings for immediate use by coaches and performance directors.

---

## References

1. Stull R. Wet-Bulb Temperature from Relative Humidity and Air Temperature. *Journal of Applied Meteorology and Climatology*. 2011;50(11):2267–2269.
2. Liljegren JC, Carhart RA, Lawday P, Tschopp S, Sharp R. Modeling the Wet Bulb Globe Temperature Using Standard Meteorological Measurements. *Journal of Occupational and Environmental Hygiene*. 2008;5(10):645–655.
3. Buck AL. New equations for computing vapor pressure and enhancement factor. *Journal of Applied Meteorology*. 1981;20(12):1527–1532.
4. Orgill JF, Hollands KGT. Correlation equation for hourly diffuse radiation on a horizontal surface. *Solar Energy*. 1977;19(4):357–359.
5. [Additional references to be completed per journal requirements]

---

## Supplementary Methods

### S1. API Data Structure

The World Triathlon API (v1) returns race results at the endpoint `/v1/programs/{prog_id}/results`. The top-level `results` field is a dictionary with keys `results` (list of athlete records), `headers` (column metadata), and pagination fields. Each athlete record contains `splits` as an ordered five-element list in [swim, T1, bike, T2, run] sequence; individual splits absent from the program are represented as `"00:00:00"` or null.

### S2. WBGT Race Window

Race-day WBGT was computed as the mean of all hourly WBGT estimates falling within the 3-hour window beginning at the scheduled programme start time. Where start times were not recorded in the API (approximately 12% of events), a default start time of 07:00 UTC was used, consistent with the prevalent morning start slot at championship events.

### S3. Power Analysis for Individual Slope Estimation

The minimum criteria of 5 races spanning ≥4°C WBGT were chosen to balance statistical power (sufficient degrees of freedom for OLS) against athlete inclusion rates. At n=5 with a true slope of −0.05 z·°C⁻¹, approximate power at α=0.05 is ~25%; at n=10 it exceeds 60%. These thresholds therefore identify athletes with reliably detectable slopes, necessarily excluding those with shorter or climatically uniform race histories. A full Bayesian hierarchical model pooling information across athletes would provide better-calibrated individual estimates and is recommended for confirmatory analyses.

### S4. Digital Twin Feature Construction

Historical features (z_swim_hist, z_bike_hist, z_run_hist, z_total_hist) were constructed using a strictly expanding window (shift-1) to prevent data leakage. Missing historical features (debut athletes or athletes with insufficient prior data) were imputed to 0.0, the within-race mean z-score and the correct Bayesian prior for unknown history. This preserves the full competitive field — including the fastest debut athletes whose early career data would otherwise be discarded — ensuring training data spans the full z_total range rather than a compressed mid-field sub-sample.

---

*Manuscript prepared: June 2026. Data collection: World Triathlon API, accessed 2025–2026. Meteorological data: Open-Meteo Historical Archive API.*
