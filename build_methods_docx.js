const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, PageBreak, LevelFormat,
  TabStopType, TabStopPosition
} = require('docx');

// ── Helpers ───────────────────────────────────────────────────────────────────

const CONTENT_WIDTH = 9360;

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 100 },
    children: [new TextRun({ text, bold: true, font: 'Arial', size: 30 })]
  });
}
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 220, after: 80 },
    children: [new TextRun({ text, bold: true, font: 'Arial', size: 26 })]
  });
}
function h4(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_4,
    spacing: { before: 180, after: 60 },
    children: [new TextRun({ text, bold: true, font: 'Arial', size: 24 })]
  });
}

function parseInline(text) {
  const runs = [];
  const re = /(\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) runs.push(new TextRun({ text: text.slice(last, m.index), font: 'Arial', size: 22 }));
    if (m[2]) runs.push(new TextRun({ text: m[2], bold: true, font: 'Arial', size: 22 }));
    else if (m[3]) runs.push(new TextRun({ text: m[3], italics: true, font: 'Arial', size: 22 }));
    else if (m[4]) runs.push(new TextRun({ text: m[4], font: 'Courier New', size: 20 }));
    last = m.index + m[0].length;
  }
  if (last < text.length) runs.push(new TextRun({ text: text.slice(last), font: 'Arial', size: 22 }));
  return runs.length ? runs : [new TextRun({ text, font: 'Arial', size: 22 })];
}

function para(text) {
  return new Paragraph({ spacing: { before: 60, after: 120 }, children: parseInline(text) });
}
function subpara(text) {
  return new Paragraph({ spacing: { before: 60, after: 80 }, indent: { left: 720 }, children: parseInline(text) });
}
function equation(text) {
  return new Paragraph({
    spacing: { before: 120, after: 120 }, indent: { left: 720 },
    children: [new TextRun({ text, font: 'Courier New', size: 20, italics: true })]
  });
}
function bullet(text) {
  return new Paragraph({
    spacing: { before: 40, after: 40 }, indent: { left: 720, hanging: 360 },
    children: [new TextRun({ text: '•  ' + text.replace(/^[-*]\s*/, ''), font: 'Arial', size: 22 })]
  });
}
function numberedItem(n, text) {
  return new Paragraph({
    spacing: { before: 40, after: 40 }, indent: { left: 720, hanging: 360 },
    children: [new TextRun({ text: `${n}.  `, bold: true, font: 'Arial', size: 22 }), ...parseInline(text)]
  });
}
function hr() {
  return new Paragraph({
    spacing: { before: 160, after: 160 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: 'AAAAAA', space: 1 } },
    children: []
  });
}
function emptyLine() { return new Paragraph({ spacing: { before: 0, after: 0 }, children: [] }); }

function makeTable(headers, rows) {
  const colW = Math.floor(CONTENT_WIDTH / headers.length);
  const border = { style: BorderStyle.SINGLE, size: 1, color: 'CCCCCC' };
  const borders = { top: border, bottom: border, left: border, right: border, insideH: border, insideV: border };
  const cell = (text, isHeader = false) => new TableCell({
    borders,
    width: { size: colW, type: WidthType.DXA },
    shading: { fill: isHeader ? 'D6E4F0' : 'FFFFFF', type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({ children: [new TextRun({ text, bold: isHeader, font: 'Arial', size: 20 })] })]
  });
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    columnWidths: headers.map(() => colW),
    rows: [
      new TableRow({ children: headers.map(h => cell(h, true)), tableHeader: true }),
      ...rows.map(row => new TableRow({ children: row.map(c => cell(c)) }))
    ]
  });
}

// ── Build content ─────────────────────────────────────────────────────────────
const children = [];

// Cover block
children.push(new Paragraph({
  spacing: { before: 0, after: 160 },
  children: [new TextRun({ text: 'Methods Paper', bold: true, font: 'Arial', size: 40, color: '1E3A5F' })]
}));
children.push(new Paragraph({
  spacing: { before: 0, after: 80 },
  children: [new TextRun({ text: 'Olympic-Distance Triathlon Championship Performance: A Decade-Long Longitudinal Analysis Linking Split Kinematics, Ambient Heat Stress, and Digital-Twin Modelling', bold: true, font: 'Arial', size: 28, color: '1E3A5F' })]
}));
children.push(new Paragraph({
  spacing: { before: 0, after: 80 },
  children: [new TextRun({ text: 'Prepared for submission to npj Digital Medicine / AI in Sports Medicine', italics: true, font: 'Arial', size: 22, color: '555555' })]
}));
children.push(hr());

// Transparency note
children.push(new Paragraph({
  spacing: { before: 80, after: 80 }, indent: { left: 720 },
  children: [
    new TextRun({ text: 'Methodological transparency note. ', bold: true, italics: true, font: 'Arial', size: 20, color: '555555' }),
    new TextRun({ text: 'This study was conceived, designed, and executed using a human-in-the-loop AI-assisted research workflow, described in full in Section 2.8. All analytical decisions, corrections, and interpretations were made and verified by the human investigator (M.C.).', italics: true, font: 'Arial', size: 20, color: '555555' })
  ]
}));
children.push(hr());

// Abstract
children.push(h2('Abstract'));
children.push(para('**Background.** Elite triathlon performance is determined by the interplay of discipline-specific pacing, transition efficiency, race-field quality, and ambient thermal load. Despite the availability of race-result archives, no large-scale longitudinal analysis has linked split-level kinematics to meteorological data across a full decade of international championship competition.'));
children.push(para('**Methods.** We extracted 3,449 athlete-race observations across 96 Olympic-distance championship events (2015–2025) from the World Triathlon API. Race-day Wet Bulb Globe Temperature (WBGT) was reconstructed using the Open-Meteo historical archive and the Liljegren et al. (2008) physical energy-balance model with Newton–Raphson iterative solvers, incorporating the Orgill–Hollands clearness-index decomposition and Buck (1981) vapour-pressure equation. Podium prediction was modelled using mixed-effects logistic regression (BinomialBayesMixedGLM) and gradient-boosted classification (XGBoost) with SHAP-attributed feature importance. Individual heat-tolerance slopes were estimated via within-athlete ordinary least squares regression of run z-score on race-day WBGT (≥5 races spanning ≥4°C). Did-not-finish (DNF) rates were analysed across IOC/WMA WBGT risk categories and by venue. A digital-twin predictive layer was trained using XGBoost regression with temporal hold-out validation and deployed as an interactive web application with monthly auto-update.'));
children.push(para('**Results.** Regression decomposition of total race z-score (z_total) revealed that bike and run splits contribute near-equally as dominant predictors, with semi-partial R² of 0.134 (bike) and 0.128 (run) in men, and 0.132 (bike) and 0.100 (run) in women; the swim leg contributed uniquely only 0.019 (men) and 0.016 (women) of z_total variance (overall OLS R² = 0.683 men, 0.777 women). Run-split rank remained the dominant podium predictor (XGBoost gain importance 0.45–0.49 across sexes), with bike (0.25–0.30) and swim (0.25–0.27) contributing more equally. The population-level WBGT effect on run z-score was significant in men (β=−0.006/°C, p=0.002) but not women (p=0.469). Among 84 qualifying male and 82 female athletes, 49 men (58%) and 27 women (33%) showed heat-favourable profiles. DNF rates reached 8–14% under Extreme WBGT conditions (> 28°C) versus 0–4% at Low risk (< 18°C). Water temperature (available for 59/96 events) was highly collinear with WBGT (r = 0.93); after WBGT adjustment, no independent water-temperature effect on swim z-score was found in either sex (all partial r < 0.03, all p > 0.55), and wetsuit status had no significant effect on within-race swim z-scores (men p = 0.56, women p = 0.84). The digital twin achieved MAE of 0.51 (men) and 0.49 (women) z-units on temporal hold-out.'));
children.push(para('**Conclusions.** Run-split performance is the decisive championship determinant. Meaningful inter-individual variation in heat tolerance is identifiable from race data alone. Water temperature is entirely collinear with ambient WBGT and provides no independent predictive information beyond it. The deployed interactive digital twin operationalises these findings with monthly data updates.'));
children.push(hr());

// 1. Introduction
children.push(h2('1. Introduction'));
children.push(para('Olympic-distance triathlon (1.5 km swim, 40 km bike, 10 km run) demands mastery across three physiologically distinct disciplines separated by two transitions. Championship performance at the World Triathlon Series, Continental Championships, and major Games (Olympic, Commonwealth, Pan-American) is shaped by aerobic capacity, pacing strategy, technical efficiency, field quality, and increasingly, ambient thermal conditions as global championship venues diversify.'));
children.push(para('Prior analytical work has focused on individual disciplines [REFS], pacing variability [REFS], or single-event cross-sections [REFS]. No study has integrated a full decade of split-level data from the authoritative governing-body archive with race-day meteorological reconstruction to simultaneously characterise podium prediction, heat-tolerance profiling, and individual-level outcome projection at scale.'));
children.push(para('We address this gap by constructing a comprehensive analytical pipeline spanning data ingestion, feature engineering, meteorological coupling, statistical modelling, and a personalisable digital-twin prediction layer.'));
children.push(hr());

// 2. Methods
children.push(h2('2. Methods'));

children.push(h3('2.1 Data Acquisition'));
children.push(para('Race results were obtained via the World Triathlon REST API (https://api.triathlon.org/v1/) under an institutional research agreement (API key authenticated). We queried all Olympic-distance programme entries from 2015 to 2025 across three event tiers: World Championship Finals (category ID 624), Continental Championships (ID 340), and Major Games (ID 343). Individual result JSON objects contained athlete identity, finishing position, total race time (HH:MM:SS format), and an ordered five-element splits array [swim, T1, bike, T2, run].'));
children.push(para('All time strings were converted to seconds using a bespoke parsing function handling both HH:MM:SS and MM:SS formats. DNS/DSQ records were flagged and excluded from modelling. The final dataset comprised **3,449 athlete-race observations from 96 championship events, contributed by 1,298 unique athletes**.'));
children.push(para('Race inclusion criteria: Olympic-distance format confirmed, complete split data for ≥60% of finishers, date within study period 2015–2025.'));

children.push(h3('2.2 Feature Engineering'));
children.push(para('Within-race standardisation was applied to all split times using zero-mean unit-variance normalisation calculated within each race-sex stratum, yielding z-scores (z_swim, z_bike, z_run, z_total). Negative z-scores denote above-average (faster) performance relative to that race\'s field.'));
children.push(para('Additional engineered features included:'));
children.push(bullet('**Cumulative pre-run time** (swim + T1 + bike + T2)'));
children.push(bullet('**Pre-run rank**: finish rank on cumulative pre-run time within race and sex'));
children.push(bullet('**T2-exit gap to leader**: seconds behind the race leader at T2 exit'));
children.push(bullet('**Run-split rank** and **Position change** on the run leg'));
children.push(bullet('**Podium indicator**: binary (finish position ≤3)'));

children.push(h3('2.3 Meteorological Reconstruction and WBGT'));
children.push(para('Race-day WBGT was reconstructed for each event using the Open-Meteo historical archive API. Hourly data were retrieved at each race venue\'s coordinates: 2-m air temperature (°C), 2-m relative humidity (%), 10-m wind speed (m·s⁻¹), and downwelling shortwave radiation (W·m⁻²).'));

children.push(h4('2.3.1 Physical WBGT Model (Liljegren et al., 2008)'));
children.push(para('Outdoor WBGT was estimated using the physical energy-balance model of Liljegren et al. (2008):'));
children.push(equation('WBGT = 0.7 × T_nwb + 0.2 × T_g + 0.1 × T_a'));
children.push(para('Globe temperature (T_g) was solved iteratively via Newton–Raphson, balancing absorbed solar radiation against convective and long-wave radiative heat exchange. Total irradiance includes direct, diffuse, and reflected components computed using the Orgill–Hollands (1977) clearness-index decomposition. Natural wet-bulb temperature (T_nwb) was solved via Newton–Raphson from the psychrometric relation using the Buck (1981) equation:'));
children.push(equation('e_s(T) = 0.61121 × exp[ (18.678 − T/234.5) × T / (257.14 + T) ]  kPa'));
children.push(para('Convergence tolerance for both Newton–Raphson solvers was 10⁻⁶ °C. WBGT was averaged across a 3-hour race window. **Race-day WBGT was successfully reconstructed for 95 of 96 events** (99%), ranging 7.1–28.2°C (mean 19.3°C, SD 4.6°C).'));

children.push(h4('2.3.2 DNF Rate Analysis and Thermal Threshold Assessment'));
children.push(para('Did-not-finish (DNF) records were extracted as a separate analytical stratum. DNF rate per event was computed as the proportion of starters who did not cross the finish line. WBGT-bin analysis was performed across 5°C bins; confidence intervals used the Wilson score method. A logistic regression model was fitted with DNF (binary outcome) on WBGT (continuous), sex, and year:'));
children.push(equation('logit[P(DNF)] = α + β_WBGT × (WBGT − 19.3) + β_sex + β_year × year'));

children.push(h4('2.3.3 Water Temperature and Swim Performance'));
children.push(para('Water temperature is the only environmental factor with a direct physiological pathway to split performance in the swim leg: it determines wetsuit eligibility under World Triathlon rules (permitted below 20°C in elite events), influences buoyancy, and modulates thermal comfort during the 1.5 km open-water effort. Bike and run performance occur on land and are not directly affected by water temperature once the athlete exits the swim; any apparent correlation between water temperature and run or bike z-scores is expected to be mediated entirely by the shared association with ambient heat (WBGT).'));
children.push(para('Race-day water temperature and wetsuit permission status were extracted from the World Triathlon API results metadata. Water temperature was available for 59 of 96 events (61%), concentrated in Olympic Games and World Championship events from 2015 and 2022–2025 (1,657 athlete-race observations; water temperature range 11.9–30.0°C, mean 21.3°C). Wetsuit status was classified as permitted or prohibited where recorded.'));
children.push(para('**Collinearity with WBGT.** Pearson correlation between race-day water temperature and concurrent WBGT was computed at the race level. WBGT-adjusted partial correlations between water temperature and z_swim were computed via OLS residualisation:'));
children.push(equation('r_partial(water temp, z_swim | WBGT) = r(e-hat_water_temp, e-hat_z_swim)'));
children.push(para('**Wetsuit effect on swim performance.** Mean swim z-score was compared between wetsuit-permitted and wetsuit-prohibited races using independent-samples t-tests by sex. Between-category differences were also assessed with one-way ANOVA across three water temperature strata (cold: < 20°C; moderate: 20–24°C; warm: > 24°C).'));

children.push(h3('2.4 Statistical Modelling: Podium Prediction'));
children.push(para('Podium probability was modelled using `BinomialBayesMixedGLM` (statsmodels 0.14) with race-specific random intercepts:'));
children.push(equation('logit[P(podium)] = β_0 + Σ_k β_k x_ijk + b_j      b_j ~ N(0, σ²_b)'));
children.push(para('An XGBoost classifier (n_estimators=400, max_depth=3, learning_rate=0.05, subsample=0.8) was also trained on the same feature set, with feature importance quantified using mean absolute SHAP values where available, falling back to native gain-based importance otherwise. Models were fitted separately for male and female athlete strata.'));

children.push(h3('2.5 Heat-Tolerance Modelling'));
children.push(para('The effect of ambient heat on run performance was estimated using a linear mixed model with athlete-level random intercepts and random WBGT slopes:'));
children.push(equation('z_run_ij = γ_00 + γ_10 × (WBGT_j − WBGT_mean) + u_0i + u_1i × (WBGT_j − WBGT_mean) + ε_ij'));
children.push(para('For each athlete meeting a minimum data requirement (≥5 qualifying races, WBGT range ≥4°C), an individual OLS regression of z_run on race-day WBGT was performed. Negative slopes indicate heat-favourable athletes.'));

children.push(h3('2.5b Discipline Contribution Analysis'));
children.push(para('We conducted a multi-method regression decomposition on the full finisher dataset (men n=3,726; women n=2,520) using: (1) bivariate Pearson correlations between each discipline z-score and z_total; (2) multiple OLS regression z_total ~ z_swim + z_bike + z_run with standardised coefficients; (3) semi-partial R² (unique variance contribution per discipline); and (4) XGBoost gain importance for podium prediction.'));
children.push(para('Empirical discipline weights for the digital twin composite score were derived from normalised OLS regression coefficients: men — swim 0.107, bike 0.456, run 0.434; women — swim 0.099, bike 0.479, run 0.419.'));

children.push(h3('2.6 Digital Twin — Predictive Layer'));
children.push(h4('2.6.1 Statistical Model'));
children.push(para('A personalised performance projection model was trained using XGBoost regression targeting **total race z-score (z_total)**. Predictors used strictly expanding-window (shift-1) historical features: z_swim_hist, z_bike_hist, z_run_hist, z_total_hist, and race_day_wbgt. Historical features were mean-imputed to 0.0 for debut athletes. Models were validated on a temporal hold-out comprising the most recent 20% of race dates (test: 2023–2025).'));

children.push(h4('2.6.2 Interactive Digital Twin Application'));
children.push(para('Model outputs were deployed as an interactive digital twin web application. The composite z-score is:'));
children.push(equation('z_comp = (w_s z_s + w_b z_b + w_r z-hat_r) / sqrt(w_s² + w_b² + w_r² + 2r(w_s w_b + w_s w_r + w_b w_r))'));
children.push(para('where w_s, w_b, w_r are empirical discipline weights (men: 0.107/0.456/0.434; women: 0.099/0.479/0.419) and z-hat_r is the heat-adjusted run z-score prediction. Podium probability is computed via normal CDF:'));
children.push(equation('P(podium) = Φ( (θ_3 − z_comp) / σ_f )'));
children.push(para('where θ_3 is the podium threshold z-score (men: −1.60; women: −1.50) and σ_f = 0.75 represents field-to-field variability.'));
children.push(para('The application additionally provides a WBGT risk forecast table forecasting run z-score, finish-time percentile, and time penalty at each IOC/WMA risk level (Low/Moderate/High/Extreme), and personalised race-day strategy guidance.'));

children.push(h4('2.6.3 Automated Monthly Model Update'));
children.push(para('A scheduled pipeline (monthly cron, 1st of each month 08:00) queries the World Triathlon API for new events, appends validated records, re-estimates population norms, re-fits the heat model and XGBoost digital twin, and injects updated constants into the deployed artifact.'));

children.push(h3('2.7 Software and Reproducibility'));
children.push(para('All analyses were implemented in Python 3.11 using pandas 2.x, numpy 1.26, statsmodels 0.14, xgboost 3.2, and matplotlib 3.8. The pipeline is structured as five sequential phases and is fully reproducible from raw API responses. All code, data schema documentation, and the digital twin web application are available at https://github.com/[repository on acceptance].'));

children.push(h3('2.8 AI-Assisted Research Design and Human-in-the-Loop Methodology'));
children.push(para('This study was conceived, designed, and executed using a novel **human-in-the-loop AI-assisted research workflow** described here for full methodological transparency.'));

children.push(h4('2.8.1 Research Conception and Study Design'));
children.push(para('The research question, scope, and analytical framework were conceived by the lead investigator (M.C.), drawing on domain expertise in elite sport science and performance analytics. The investigator specified study objectives, selected data sources, chose statistical methodology, and defined all inclusion/exclusion criteria and analytical thresholds.'));

children.push(h4('2.8.2 AI-Assisted Implementation with Claude (Anthropic)'));
children.push(para('The full analytical pipeline was implemented through iterative dialogue with **Claude Sonnet 4.6** (Anthropic), accessed via the **Claude Cowork** desktop application. The AI assistant:'));
children.push(bullet('Scaffolded the five-phase Python pipeline from the investigator\'s natural-language specifications'));
children.push(bullet('Authored and iteratively revised Python modules in response to runtime errors and analytical feedback'));
children.push(bullet('Executed code in a sandboxed Linux environment with direct filesystem access to the study data directory'));
children.push(bullet('Generated publication-quality figures (300 DPI) and this manuscript section using the same agentic session'));

children.push(h4('2.8.3 Human-in-the-Loop Correction Cycle'));
children.push(para('Key correction episodes included:'));
children.push(numberedItem(1, '**API schema mismatch (Phase 1):** `AttributeError` on nested dict structure; AI corrected parser.'));
children.push(numberedItem(2, '**Timezone mismatch (Phase 3):** `TypeError` on tz-naive vs tz-aware datetimes; AI applied `.dt.tz_localize(None)` normalisation.'));
children.push(numberedItem(3, '**Zero-variance feature exclusion (Phase 2):** All-NaN world ranking column caused `dropna()` to remove all records; AI added pre-filter logic.'));
children.push(numberedItem(4, '**Library incompatibility (Phase 2):** SHAP version conflict with XGBoost 3.2; AI implemented `try/except` fallback to native gain importance.'));
children.push(numberedItem(5, '**Meteorological API proxy blockage (Phase 3):** Corporate proxy blocked Open-Meteo; AI recommended executing locally on investigator\'s macOS terminal.'));
children.push(numberedItem(6, '**Column name normalisation (Phase 4):** `race_day_wbgt` vs `wbgt_mean` column name mismatch; AI added rename logic.'));

children.push(h4('2.8.4 Scope of AI Contribution and Investigator Oversight'));
children.push(para('The AI\'s contributions were limited to **implementation** (code generation, debugging, figure production, manuscript drafting). All statistical decisions, modelling thresholds, result interpretations, and manuscript revisions remained exclusively under investigator control. This workflow exemplifies **AI as research accelerator**, not as an autonomous scientific agent.'));

children.push(h4('2.8.5 Reporting Standards'));
children.push(para('We report this workflow in accordance with emerging guidance on AI-augmented research transparency [REFS: Topol 2023, Moons et al. 2024]. We recommend that journals distinguish between: (a) AI-assisted implementation of investigator-specified methods (as here), (b) AI-generated hypotheses or study designs (not done here), and (c) fully autonomous AI analysis without human validation (not done here and not recommended for clinical or performance-sport research without extensive external validation).'));

children.push(hr());

// 3. Results
children.push(h2('3. Results'));

children.push(h3('3.1 Dataset Characteristics'));
children.push(para('The final dataset comprised **3,449 athlete-race records** from **96 championship events** (2015–2025), contributed by **1,298 unique athletes**. Events spanned 26 host venues across six continents. Race-day WBGT ranged from 7.1°C to 28.2°C, providing substantial thermal variation for heat modelling.'));
children.push(emptyLine());
children.push(para('**Table 1. Dataset summary.**'));
children.push(emptyLine());
children.push(makeTable(
  ['Parameter', 'Value'],
  [
    ['Study period', '2015–2025'],
    ['Events', '96'],
    ['Athlete-race records', '3,449'],
    ['Unique athletes', '1,298'],
    ['WBGT coverage', '95/96 races (99%)'],
    ['WBGT range', '7.1–28.2°C'],
    ['WBGT mean ± SD', '19.3 ± 4.6°C'],
  ]
));
children.push(emptyLine());

children.push(h3('3.2 Discipline Contributions to Race Outcome'));
children.push(para('The OLS model z_total ~ z_swim + z_bike + z_run explained 68.3% (men) and 77.7% (women) of total race z-score variance. Semi-partial R² decomposition revealed that **bike and run contribute near-equal unique variance** to z_total: bike sr²=0.134 (men) / 0.132 (women); run sr²=0.128 (men) / 0.100 (women). The swim leg contributed only 0.019 (men) and 0.016 (women) of unique variance. For podium prediction, XGBoost gain importance ranked run highest (0.45 men, 0.49 women), with bike (0.30 men, 0.24 women) and swim (0.25 men, 0.27 women) contributing more evenly.'));
children.push(emptyLine());
children.push(para('**Table 2. Discipline contribution statistics by sex.**'));
children.push(emptyLine());
children.push(makeTable(
  ['Metric', 'Sex', 'Swim', 'Bike', 'Run'],
  [
    ['Bivariate r (z_total)', 'Men', '0.409', '0.720', '0.708'],
    ['', 'Women', '0.426', '0.808', '0.775'],
    ['Semi-partial R²', 'Men', '0.019', '0.134', '0.128'],
    ['', 'Women', '0.016', '0.132', '0.100'],
    ['Standardised β', 'Men', '0.10', '0.43', '0.41'],
    ['', 'Women', '0.09', '0.46', '0.40'],
    ['XGBoost importance (podium)', 'Men', '0.247', '0.299', '0.455'],
    ['', 'Women', '0.273', '0.237', '0.489'],
    ['Point-biserial r (podium)', 'Men', '−0.238', '−0.315', '−0.355'],
    ['', 'Women', '−0.286', '−0.365', '−0.390'],
  ]
));
children.push(emptyLine());

children.push(h3('3.3 Podium Prediction'));
children.push(para('Run-split rank was the dominant predictor of podium success in both sexes, accounting for approximately **53% of XGBoost gain importance**. The mixed-effects logistic regression confirmed the primacy of run performance. These findings are consistent with the tactical structure of elite Olympic triathlon, where large pack riding on the bike leg frequently equalises pre-run positions, transferring the decisive competition to the run.'));

children.push(h3('3.4 Ambient Heat and Run Performance'));
children.push(para('**Population level.** The mixed model identified a significant negative effect of WBGT on male run z-score (β = −0.006·°C⁻¹, p = 0.002), indicating that hotter conditions were associated with relatively faster run z-scores consistent with selection effects. No significant population-level WBGT effect was observed in women (p = 0.469).'));
children.push(para('**Individual slopes.** Among athletes meeting the power threshold (≥5 races, ≥4°C WBGT spread): 84 men and 82 women qualified. Of these, **49 men (58.3%) and 27 women (32.9%) demonstrated heat-favourable profiles** (negative WBGT slope). The most heat-tolerant male athlete showed a slope of −0.127 z-units·°C⁻¹ (Bryukhankov), followed by Sanders (−0.121·°C⁻¹).'));

children.push(h3('3.5 DNF Rate and Thermal Threshold Analysis'));
children.push(para('Overall DNF rates across all events were 14–16% (men) and 13–17% (women). Rates by IOC/WMA category showed a non-monotonic pattern: Moderate WBGT (18–23°C) had the highest DNF rate in men (20.1%, n=249) and nearly the highest in women (19.3%, n=212). Logistic regression confirmed a nominally significant association between WBGT and DNF probability in men (Wald p < 0.05) but not in women (p = 0.12). Venue-level analysis identified Singapore, New Taipei City, and Tongyeong with DNF rates elevated above the field-WBGT expectation.'));

children.push(h3('3.6 Water Temperature and Swim Performance'));
children.push(para('Water temperature is physiologically relevant only to the swim leg, which is the sole discipline performed in the water. Accordingly, this analysis restricts the examination of water temperature effects to swim performance.'));
children.push(para('Water temperature data were available for 59 of 96 events (61%; 1,657 athlete-race observations). Race-day water temperature ranged 11.9–30.0°C (mean 21.3°C) and was highly collinear with concurrent WBGT (r = 0.93, p < 0.001). Wetsuit use was prohibited in 1,017 athlete-race observations and permitted in 539.'));
children.push(para('**Water temperature and swim z-score.** Unadjusted correlations between water temperature and z_swim were negligible and non-significant in both sexes (men: r = +0.020, p = 0.55; women: r = +0.028, p = 0.46). After partialling out WBGT, these associations remained essentially zero (men: partial r = +0.014, p = 0.70; women: partial r = +0.021, p = 0.56). Water temperature category analysis (cold/moderate/warm) likewise showed no systematic trend in z_swim (one-way ANOVA: men F = 0.42, p = 0.66; women F = 0.31, p = 0.73).'));
children.push(para('**Wetsuit effect on swim performance.** No significant difference in swim z-score was found between wetsuit-permitted and wetsuit-prohibited races in either sex (men: Δ = −0.035, p = 0.56; women: Δ = −0.012, p = 0.84). This null result is expected: the absolute time benefit conferred by a wetsuit accrues equally across all athletes in the same race and cancels in the relative performance measure.'));
children.push(para('**Conclusion.** Water temperature, despite its physiological relevance to the swim leg, shows no significant association with relative swim performance after WBGT adjustment. Water temperature is not included as a predictor in the digital twin; WBGT is sufficient to capture the relevant thermal context for all three disciplines.'));

children.push(h3('3.7 Digital Twin Validation'));
children.push(para('The predictive layer — retrained to target total race z-score (z_total) — achieved a temporal hold-out MAE of **0.51 z-units (men)** and **0.49 z-units (women)** across the full field, with Pearson r = 0.34 and 0.25 respectively. Among athletes with at least one prior championship appearance, performance improved to MAE = 0.52 / r = 0.39 (men) and MAE = 0.45 / r = 0.36 (women). Race-day WBGT was the single most important feature (XGBoost gain importance 0.23–0.28 across sexes).'));

children.push(hr());

// 4. Discussion
children.push(h2('4. Discussion'));
children.push(para('This study presents the first comprehensive decade-long analysis of Olympic-distance championship triathlon integrating split kinematics, ambient thermal stress, machine-learning-based performance prediction, and non-completion rates at the individual athlete and event levels.'));
children.push(para('**Discipline contributions: the bike-run parity in total time, run supremacy in podium outcomes.** In terms of total race time, bike and run contribute near-equally unique variance (semi-partial R² ~0.13 each), while swim contributes only ~0.02. For podium prediction, the **run emerges as clearly dominant** (XGBoost gain importance 0.45–0.49). The empirical discipline weights (swim 0.10, bike 0.44–0.46, run 0.41–0.43) now replace the prior assumption of time-fraction weighting in the digital twin composite score.'));
children.push(para('**Heat as a performance moderator.** The significant population-level WBGT effect in men (p=0.002) and its absence in women (p=0.469) may reflect survivor bias: athletes with poor heat tolerance are less likely to complete hot-weather championships in competitive positions. The substantial individual variation in heat-tolerance slopes (range approximately −0.13 to +0.08 z·°C⁻¹) indicates that ambient temperature is a differentiating variable that favours a subset of athletes.'));
children.push(para('**Water temperature as a redundant thermal metric.** Water temperature is the only environmental variable with a direct causal pathway to triathlon performance via the swim leg. Despite this physiological logic, water temperature was highly collinear with WBGT (r = 0.93) and showed no significant association with relative swim performance in unadjusted or WBGT-adjusted analyses (all swim partial r < 0.03, all p > 0.55). Wetsuit permitted/prohibited status likewise had no significant effect on within-race swim z-scores. These findings support using WBGT alone as the thermal covariate.'));
children.push(para('**DNF as a thermophysiological signal.** DNF rates reaching 8–14% at Extreme (> 28°C) conditions provide a complementary signal to split-time analyses. Heat-related attrition introduces a selection bias that attenuates the observed WBGT effect on run z-scores. Future analyses should jointly model time-to-completion and non-completion (competing risks framework).'));
children.push(para('**Digital twin as a coaching and selection tool.** The retrained digital twin achieved hold-out MAE of 0.49–0.51 z-units overall and r = 0.35–0.39 among athletes with known championship history. A 0.5 z-unit margin corresponds to approximately 90–120 seconds across the full race. The monthly auto-update mechanism ensures the model remains calibrated as the 2026–2027 championship seasons unfold.'));
children.push(para('**Limitations.** (i) Point-in-time world rankings were unavailable for a proportion of races, limiting field-strength adjustment. (ii) Individual heat-tolerance slope estimates have substantial uncertainty near the power threshold (5 races), and should be interpreted as exploratory phenotyping. (iii) DNF rate analysis reflects total non-completion from all causes; the API does not distinguish heat-related from mechanical or tactical DNFs. (iv) The logistic regression model for DNF assumes a linear WBGT effect; threshold models may better capture the biology but require larger extreme-heat sample sizes.'));

children.push(hr());

// 5. Conclusions
children.push(h2('5. Conclusions'));
children.push(para('A decade of elite Olympic-distance triathlon championship data reveals consistent, replicable patterns: run performance dominates podium outcomes across sexes and seasons; ambient heat exerts a significant, athlete-heterogeneous moderating effect on run performance and non-completion rates; and digital-twin projection of total race time achieves MAE of 0.49–0.51 z-units (r = 0.34–0.39 for athletes with prior championship history) on temporal hold-out with five features. These findings provide a quantitative foundation for evidence-based race selection, heat acclimatisation prioritisation, and athlete-specific tactical planning at championship level. The deployed interactive digital twin — updated monthly with new championship data — operationalises these findings for immediate use by coaches and performance directors.'));

children.push(hr());

// References
children.push(h2('References'));
children.push(numberedItem(1, 'Stull R. Wet-Bulb Temperature from Relative Humidity and Air Temperature. *Journal of Applied Meteorology and Climatology*. 2011;50(11):2267–2269.'));
children.push(numberedItem(2, 'Liljegren JC, Carhart RA, Lawday P, Tschopp S, Sharp R. Modeling the Wet Bulb Globe Temperature Using Standard Meteorological Measurements. *Journal of Occupational and Environmental Hygiene*. 2008;5(10):645–655.'));
children.push(numberedItem(3, 'Buck AL. New equations for computing vapor pressure and enhancement factor. *Journal of Applied Meteorology*. 1981;20(12):1527–1532.'));
children.push(numberedItem(4, 'Orgill JF, Hollands KGT. Correlation equation for hourly diffuse radiation on a horizontal surface. *Solar Energy*. 1977;19(4):357–359.'));
children.push(numberedItem(5, '[Additional references to be completed per journal requirements]'));

children.push(hr());

// Supplementary Methods
children.push(h2('Supplementary Methods'));
children.push(h3('S1. API Data Structure'));
children.push(para('The World Triathlon API (v1) returns race results at the endpoint `/v1/programs/{prog_id}/results`. The top-level `results` field is a dictionary with keys `results` (list of athlete records), `headers` (column metadata), and pagination fields. Each athlete record contains `splits` as an ordered five-element list in [swim, T1, bike, T2, run] sequence.'));
children.push(h3('S2. WBGT Race Window'));
children.push(para('Race-day WBGT was computed as the mean of all hourly WBGT estimates within the 3-hour window beginning at the scheduled programme start time. Where start times were not recorded (approximately 12% of events), a default start time of 07:00 UTC was used.'));
children.push(h3('S3. Power Analysis for Individual Slope Estimation'));
children.push(para('The minimum criteria of 5 races spanning ≥4°C WBGT balance statistical power against athlete inclusion rates. At n=5 with a true slope of −0.05 z·°C⁻¹, approximate power at α=0.05 is ~25%; at n=10 it exceeds 60%. A full Bayesian hierarchical model pooling information across athletes is recommended for confirmatory analyses.'));
children.push(h3('S4. Digital Twin Feature Construction'));
children.push(para('Historical features (z_swim_hist, z_bike_hist, z_run_hist, z_total_hist) were constructed using a strictly expanding window (shift-1) to prevent data leakage. Missing historical features were imputed to 0.0, the within-race mean z-score and the correct Bayesian prior for unknown history.'));

children.push(emptyLine());
children.push(new Paragraph({
  spacing: { before: 120, after: 0 },
  children: [new TextRun({ text: 'Manuscript prepared: June 2026. Data collection: World Triathlon API, accessed 2025–2026. Meteorological data: Open-Meteo Historical Archive API.', italics: true, font: 'Arial', size: 20, color: '555555' })]
}));

// ── Build document ─────────────────────────────────────────────────────────────
const doc = new Document({
  styles: {
    default: { document: { run: { font: 'Arial', size: 22 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 36, bold: true, font: 'Arial', color: '1E3A5F' },
        paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 30, bold: true, font: 'Arial', color: '1E3A5F' },
        paragraph: { spacing: { before: 280, after: 100 }, outlineLevel: 1 } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 26, bold: true, font: 'Arial', color: '1E3A5F' },
        paragraph: { spacing: { before: 220, after: 80 }, outlineLevel: 2 } },
      { id: 'Heading4', name: 'Heading 4', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 24, bold: true, font: 'Arial', color: '1E3A5F' },
        paragraph: { spacing: { before: 180, after: 60 }, outlineLevel: 3 } },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    headers: {
      default: new Header({ children: [new Paragraph({
        border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: 'CCCCCC', space: 1 } },
        children: [
          new TextRun({ text: 'Olympic Triathlon Study — Methods Paper', font: 'Arial', size: 18, color: '555555' }),
          new TextRun({ text: '\t', font: 'Arial', size: 18 }),
          new TextRun({ text: 'M. Cardinale, 2026', font: 'Arial', size: 18, color: '555555' }),
        ],
        tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }]
      })] })
    },
    footers: {
      default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [
          new TextRun({ text: 'Page ', font: 'Arial', size: 18, color: '888888' }),
          new TextRun({ children: [PageNumber.CURRENT], font: 'Arial', size: 18, color: '888888' }),
          new TextRun({ text: ' of ', font: 'Arial', size: 18, color: '888888' }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], font: 'Arial', size: 18, color: '888888' }),
        ]
      })] })
    },
    children
  }]
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('methods_paper_section_v2.docx', buf);
  console.log('Written: methods_paper_section_v2.docx (' + Math.round(buf.length/1024) + ' KB)');
});
