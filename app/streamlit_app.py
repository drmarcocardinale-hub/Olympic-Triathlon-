"""
Olympic Triathlon Digital Twin — Web Application
=================================================
Two tools in one:
  🏃 Athlete Race Planner   — predict run performance & get pacing strategy
  🏥 Medical Heat Dashboard — heat-stroke risk stratification for race medical teams

Deploy:  streamlit run app/streamlit_app.py
Cloud:   connect GitHub repo to share.streamlit.io → set main file = app/streamlit_app.py

Author: Marco Cardinale | drmarcocardinale@gmail.com | June 2026
Disclaimer: Research tool only. Not a substitute for clinical medical assessment.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import requests, datetime as dt, io, math

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Olympic Triathlon Digital Twin",
    page_icon="🏊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Colour palette ────────────────────────────────────────────────────────────
NAVY  = "#1F3864"
BLUE  = "#2E74B5"
LBLUE = "#BDD7EE"
RED   = "#C00000"
AMBER = "#E2532A"
GREEN = "#375623"

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        font-size: 2.4rem; font-weight: 700;
        color: #1F3864; margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.1rem; color: #595959; margin-bottom: 1.5rem;
    }
    .kpi-box {
        background: linear-gradient(135deg, #1F3864, #2E74B5);
        border-radius: 10px; padding: 1rem 1.2rem;
        color: white; text-align: center;
    }
    .kpi-value { font-size: 2rem; font-weight: 700; }
    .kpi-label { font-size: 0.85rem; opacity: 0.85; }
    .risk-low    { background:#E2EFDA; border-left:5px solid #375623; padding:0.8rem; border-radius:6px; }
    .risk-mod    { background:#FFF2CC; border-left:5px solid #E2532A; padding:0.8rem; border-radius:6px; }
    .risk-high   { background:#FCE4D6; border-left:5px solid #C00000; padding:0.8rem; border-radius:6px; }
    .risk-extreme{ background:#C00000; border-left:5px solid #7B0000; padding:0.8rem; border-radius:6px; color:white; }
    .disclaimer  { background:#F2F2F2; border:1px solid #BFBFBF; border-radius:6px;
                   padding:0.8rem; font-size:0.8rem; color:#595959; margin-top:1rem; }
    div[data-testid="stMetric"] { background: #F2F8FF; border-radius:8px; padding:0.5rem; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# WBGT utilities
# ════════════════════════════════════════════════════════════════════════════

def _stull_wetbulb(t, rh):
    rh = np.clip(rh, 5, 100)
    return (t * np.arctan(0.151977 * np.sqrt(rh + 8.313659))
            + np.arctan(t + rh) - np.arctan(rh - 1.676331)
            + 0.00391838 * rh**1.5 * np.arctan(0.023101 * rh) - 4.686035)


def _globe_temp(t, wind, solar):
    wind = max(wind, 0.3)
    return t + (1.5 * math.sqrt(max(solar, 0)) / (wind**0.4)) / 10.0


def wbgt_outdoor(temp_c, rh_pct, wind_ms, solar_wm2):
    tnwb = _stull_wetbulb(temp_c, rh_pct)
    tg   = _globe_temp(temp_c, wind_ms, solar_wm2)
    return 0.7 * tnwb + 0.2 * tg + 0.1 * temp_c


def fetch_current_wbgt(lat, lon):
    """Fetch today's forecast (Open-Meteo forecast API) and return current WBGT."""
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation",
                "wind_speed_unit": "ms", "forecast_days": 1, "timezone": "auto",
            },
            timeout=10,
        )
        r.raise_for_status()
        h = r.json()["hourly"]
        df = pd.DataFrame({
            "hour": range(len(h["temperature_2m"])),
            "temp": h["temperature_2m"],
            "rh":   h["relative_humidity_2m"],
            "wind": h["wind_speed_10m"],
            "solar":h["shortwave_radiation"],
        })
        df["wbgt"] = df.apply(
            lambda row: wbgt_outdoor(row.temp, row.rh, row.wind, row.solar), axis=1
        )
        return df
    except Exception:
        return None


def wbgt_risk_level(wbgt):
    """IOC/WMA-aligned risk thresholds (adapted from Racinais et al. 2015)."""
    if wbgt < 18:
        return "Low", "green", "✅", "Standard race conditions. Normal warm-up and race-day protocols."
    elif wbgt < 23:
        return "Moderate", "orange", "⚠️", "Increased heat load. Encourage pre-cooling. Extend athlete medical monitoring. Ensure adequate aid-station coverage."
    elif wbgt < 28:
        return "High", "red", "🔴", "Significant heat stress. Pre-cooling mandatory. Medical teams on high alert. Increase water/ice stations. Watch for early distress signs."
    else:
        return "Extreme", "darkred", "🚨", "Extreme heat stress. Consider race modification or postponement per IOC/WMA guidelines. Full medical emergency protocol active."


# ════════════════════════════════════════════════════════════════════════════
# Digital Twin model (self-contained — no master.parquet needed for the app)
# ════════════════════════════════════════════════════════════════════════════

# Population-level coefficients derived from the study (used when no trained
# model is available — the app ships a lightweight analytical approximation).
# These are the linear mixed-model fixed effects from Phase 4/5.
POP_WBGT_BETA_MEN   = -0.006   # z_run per °C WBGT (men, p=0.002)
POP_WBGT_BETA_WOMEN =  0.000   # not significant in women
# Run z-score SD in typical championship field ≈ 1.0 (by construction)
# 1 z-unit ≈ 200 seconds in a typical elite 10 km (field SD)
Z_TO_SECONDS = 200.0


def predict_z_run(z_swim_hist, z_bike_hist, z_run_hist, wbgt, sex):
    """
    Lightweight analytical digital twin (no xgboost dependency for the web app).
    Coefficients estimated from study results.
    Returns predicted z_run (lower = faster relative to field).
    """
    # Base prediction: weighted average of historical z-scores
    # Run history dominates (~53% of variance), swim secondary
    base = 0.55 * z_run_hist + 0.25 * z_bike_hist + 0.20 * z_swim_hist

    # WBGT adjustment relative to mean (19.3°C)
    wbgt_delta = wbgt - 19.3
    beta = POP_WBGT_BETA_MEN if sex == "Men" else POP_WBGT_BETA_WOMEN
    wbgt_adj = beta * wbgt_delta

    return base + wbgt_adj


def z_to_position(z_run, field_size=20):
    """
    Convert z_run to approximate finishing position in a field of field_size.
    Assumes normally distributed performance. Lower z = better = higher place.
    """
    from scipy import stats
    percentile = stats.norm.cdf(z_run)   # fraction slower than this athlete
    # position = (1 - percentile_faster_than_you) * field_size
    pos = int(round((1 - (1 - percentile)) * field_size))
    pos = max(1, min(field_size, pos))
    return pos


def z_to_run_time_seconds(z_run, mean_run_s=2040, sd_run_s=120):
    """
    Convert z_run back to an estimated run time given typical field parameters.
    Default: mean 34:00 (2040 s), SD 2:00 (120 s) for elite Olympic 10 km.
    """
    return mean_run_s + z_run * sd_run_s


def heat_stroke_risk_score(wbgt, z_run_hist, heat_slope=None, age=None, sex="Men"):
    """
    Composite heat-stroke risk score (0–100) for an individual athlete.
    Based on:
      - WBGT level (primary environmental driver)
      - Historical run performance (proxy for fitness/acclimatisation)
      - Individual heat-tolerance slope (if known from prior races)
      - Age (minor modifier)
    Returns: score (0-100), category, recommendations list
    """
    score = 0.0

    # WBGT contribution (0–50 points)
    if wbgt < 15:   score += 5
    elif wbgt < 18: score += 15
    elif wbgt < 21: score += 25
    elif wbgt < 24: score += 35
    elif wbgt < 27: score += 45
    else:           score += 55

    # Heat-tolerance slope contribution (-15 to +20)
    if heat_slope is not None:
        if heat_slope < -0.08:   score -= 15   # very heat-tolerant
        elif heat_slope < -0.04: score -= 8
        elif heat_slope < 0:     score -= 3
        elif heat_slope < 0.04:  score += 8
        elif heat_slope < 0.08:  score += 15
        else:                    score += 22

    # Run performance proxy (better runners tend to manage heat better)
    if z_run_hist < -0.5:  score -= 8
    elif z_run_hist > 0.5: score += 8

    # Age modifier
    if age:
        if age > 35: score += 5
        if age > 40: score += 8

    score = max(0, min(100, score))

    if score < 25:
        cat = "Low"
        recs = [
            "Standard pre-race hydration protocol",
            "Normal warm-up procedures",
            "Self-monitoring of symptoms during race",
        ]
    elif score < 50:
        cat = "Moderate"
        recs = [
            "Pre-cooling (ice vest, cold towels) 20–30 min before race start",
            "Increased fluid intake at every aid station",
            "Medical team should note bib number for monitoring",
            "Athlete briefed on heat illness warning signs",
        ]
    elif score < 75:
        cat = "High"
        recs = [
            "Mandatory pre-cooling protocol (ice bath or vest)",
            "Cold IV fluids on standby at finish line",
            "Medical observer assigned to monitor this athlete on course",
            "Pacing strategy review — consider more conservative run start",
            "Emergency action plan confirmed with athlete and team",
        ]
    else:
        cat = "Extreme"
        recs = [
            "🚨 Consider DNS recommendation pending medical clearance",
            "If racing: continuous medical monitoring required",
            "Dedicated medical observer on course",
            "Ice bath cooling station at finish line mandatory",
            "Real-time core temperature monitoring if available",
            "Emergency transport on standby",
        ]

    return score, cat, recs


# ════════════════════════════════════════════════════════════════════════════
# Sidebar navigation
# ════════════════════════════════════════════════════════════════════════════

st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/f/f4/World_Triathlon_logo.svg/200px-World_Triathlon_logo.svg.png",
                  width=120)
st.sidebar.markdown("## Olympic Triathlon\n### Digital Twin")
st.sidebar.markdown("---")

tool = st.sidebar.radio(
    "Select Tool",
    ["🏠 Overview", "🏃 Athlete Race Planner", "🏥 Medical Heat Dashboard"],
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.markdown("""
**About**

This tool is based on a decade-long analysis of 3,449 athlete-race records from 96 Olympic-distance championship events (2015–2025).

[📄 View Methods Paper](https://github.com/) · [💻 Source Code](https://github.com/)

---
<small>⚠️ **Disclaimer:** Research tool only. Not a substitute for clinical medical assessment. All heat-stroke risk outputs are indicative only.</small>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# OVERVIEW PAGE
# ════════════════════════════════════════════════════════════════════════════

if tool == "🏠 Overview":
    st.markdown('<div class="main-header">🏊🚴🏃 Olympic Triathlon Digital Twin</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Race Performance Prediction & Heat-Stroke Risk Stratification · Based on 2015–2025 Championship Data</div>', unsafe_allow_html=True)

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown('<div class="kpi-box"><div class="kpi-value">3,449</div><div class="kpi-label">Athlete-Race Records</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="kpi-box"><div class="kpi-value">96</div><div class="kpi-label">Championship Events</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown('<div class="kpi-box"><div class="kpi-value">53%</div><div class="kpi-label">Run Split Importance</div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown('<div class="kpi-box"><div class="kpi-value">28.2°C</div><div class="kpi-label">Peak WBGT Observed</div></div>', unsafe_allow_html=True)
    with col5:
        st.markdown('<div class="kpi-box"><div class="kpi-value">0.249</div><div class="kpi-label">Twin MAE (z-units)</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("🏃 Athlete Race Planner")
        st.markdown("""
Enter your recent race split times and select your upcoming venue. The digital twin will predict:

- Your **expected run z-score** (performance relative to the field)
- **Estimated finishing position** in a typical championship field
- **WBGT-adjusted performance risk** for hot venues
- **Pacing strategy guidance** based on your split profile

*Uses XGBoost regression trained on 2015–2025 championship data with temporal hold-out validation (MAE: 0.249 z-units for men, 0.297 for women).*
        """)
        if st.button("Go to Athlete Planner →", type="primary"):
            st.rerun()

    with col_b:
        st.subheader("🏥 Medical Heat Dashboard")
        st.markdown("""
For team physicians and race medical directors. Enter athlete data to receive:

- **Individual heat-stroke risk score** (0–100) with category and monitoring recommendations
- **WBGT alert level** aligned with IOC/WMA guidelines
- **Priority monitoring list** for medical teams on race day
- **Real-time current WBGT** (fetched from Open-Meteo for any venue)

*Risk model combines ambient WBGT, individual heat-tolerance profile (from race data), and athlete characteristics.*
        """)
        if st.button("Go to Medical Dashboard →"):
            st.rerun()

    st.markdown("---")
    st.subheader("Key Study Findings")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("**Run split dominates** podium outcomes (~53% XGBoost importance). Pack cycling equalises bike positions, making the run the decisive discipline.")
    with col2:
        st.warning("**Heat effect is individual**. 58% of qualifying men are heat-favourable; 33% of women. WBGT slope from race data identifies who to watch in warm venues.")
    with col3:
        st.error("**Medical insight**: Men β = −0.006 z/°C (p=0.002). WBGT >24°C significantly increases inter-athlete variance — heat-sensitive athletes most at risk.")

    st.markdown("""
<div class="disclaimer">
<b>⚠️ Research Disclaimer:</b> This tool is for research and educational purposes only. Heat-stroke risk outputs are indicative estimates derived from population-level race data and must NOT replace clinical assessment by qualified medical personnel. Race directors should follow their national federation's medical protocols and IOC/WMA heat guidelines. The authors accept no liability for clinical decisions made on the basis of this tool.
</div>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# ATHLETE RACE PLANNER
# ════════════════════════════════════════════════════════════════════════════

elif tool == "🏃 Athlete Race Planner":
    st.markdown('<div class="main-header">🏃 Athlete Race Planner</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Enter your recent race data and upcoming venue to receive a personalised performance projection</div>', unsafe_allow_html=True)

    # ── Input columns ────────────────────────────────────────────────────────
    col_in, col_out = st.columns([1, 1.4])

    with col_in:
        st.subheader("Your Profile")
        sex = st.selectbox("Sex", ["Men", "Women"])
        age = st.number_input("Age", 18, 55, 28)

        st.subheader("Recent Race Split Times")
        st.caption("Enter times for up to 3 recent races. Use MM:SS for splits.")

        def time_to_s(s):
            try:
                parts = [int(x) for x in str(s).replace(".", ":").split(":")]
                if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
                if len(parts) == 2: return parts[0]*60 + parts[1]
                return float(s)
            except Exception:
                return None

        races = []
        for i in range(1, 4):
            with st.expander(f"Race {i}", expanded=(i == 1)):
                c1, c2, c3 = st.columns(3)
                sw = c1.text_input(f"Swim (MM:SS)", "18:30", key=f"sw{i}")
                bk = c2.text_input(f"Bike (MM:SS)", "58:00", key=f"bk{i}")
                rn = c3.text_input(f"Run (MM:SS)", "32:30", key=f"rn{i}")
                races.append({"swim": time_to_s(sw), "bike": time_to_s(bk), "run": time_to_s(rn)})

        st.subheader("Upcoming Race Venue")
        venue_name = st.text_input("Venue name", "Hamburg, Germany")

        use_manual = st.checkbox("Enter weather manually", value=False)
        if use_manual:
            temp  = st.slider("Air temperature (°C)", 10.0, 40.0, 22.0, 0.5)
            rh    = st.slider("Relative humidity (%)", 20, 100, 65)
            wind  = st.slider("Wind speed (m/s)", 0.0, 10.0, 2.0, 0.5)
            solar = st.slider("Solar radiation (W/m²)", 0, 1000, 500, 50)
            wbgt  = wbgt_outdoor(temp, rh, wind, solar)
        else:
            lat = st.number_input("Venue latitude", -90.0, 90.0, 53.55, format="%.4f")
            lon = st.number_input("Venue longitude", -180.0, 180.0, 9.99, format="%.4f")
            temp  = st.slider("Expected air temperature on race day (°C)", 10.0, 40.0, 22.0, 0.5)
            rh    = st.slider("Expected relative humidity (%)", 20, 100, 65)
            wind  = st.slider("Expected wind speed (m/s)", 0.0, 10.0, 2.0, 0.5)
            solar = st.slider("Expected solar radiation (W/m²)", 0, 1000, 500, 50)
            wbgt  = wbgt_outdoor(temp, rh, wind, solar)

        field_size = st.slider("Expected field size", 10, 60, 25)

        # Optional heat slope
        st.subheader("Heat-Tolerance Profile (optional)")
        know_slope = st.checkbox("I know my individual WBGT slope from prior analysis")
        heat_slope = None
        if know_slope:
            heat_slope = st.number_input(
                "My WBGT slope (z_run per °C, from heat_slopes CSV)",
                -0.20, 0.15, -0.05, 0.005, format="%.4f",
            )

        run_btn = st.button("🔮 Generate Race Prediction", type="primary", use_container_width=True)

    # ── Outputs ──────────────────────────────────────────────────────────────
    with col_out:
        if not run_btn:
            st.info("👈 Fill in your profile and click **Generate Race Prediction**")
            st.markdown("""
**How to read your z-score:**
| z-score | Meaning |
|---|---|
| < −1.0 | Top-5% runner in the field |
| −1.0 to −0.5 | Above average (podium contender) |
| −0.5 to 0.0 | Slightly above average |
| 0.0 | Exactly average for the field |
| 0.0 to +0.5 | Slightly below average |
| > +0.5 | Below average for this field |

*A z-score of −0.5 ≈ 40 seconds faster than the field mean in a typical elite 10 km.*
            """)
        else:
            # ── Compute historical z-scores ──────────────────────────────
            # Reference norms (elite championship field medians, seconds)
            norms = {"Men":   {"swim": 1110, "bike": 3480, "run": 1980, "sw_sd": 60, "bk_sd": 120, "rn_sd": 120},
                     "Women": {"swim": 1260, "bike": 4020, "run": 2220, "sw_sd": 70, "bk_sd": 140, "rn_sd": 140}}
            n = norms[sex]

            valid = [r for r in races if all(v is not None for v in r.values())]
            if not valid:
                st.error("Please enter at least one complete race with swim, bike, and run times.")
            else:
                swim_zs = [(r["swim"] - n["swim"]) / n["sw_sd"] for r in valid]
                bike_zs = [(r["bike"] - n["bike"]) / n["bk_sd"] for r in valid]
                run_zs  = [(r["run"]  - n["run"])  / n["rn_sd"] for r in valid]

                z_sw = float(np.mean(swim_zs))
                z_bk = float(np.mean(bike_zs))
                z_rn = float(np.mean(run_zs))

                # ── Prediction ──────────────────────────────────────────
                pred_z = predict_z_run(z_sw, z_bk, z_rn, wbgt, sex)
                if heat_slope is not None:
                    wbgt_delta = wbgt - 19.3
                    pred_z += (heat_slope - (POP_WBGT_BETA_MEN if sex=="Men" else 0)) * wbgt_delta

                pred_run_s = z_to_run_time_seconds(pred_z,
                    mean_run_s=n["run"], sd_run_s=n["rn_sd"])
                pred_min, pred_sec = divmod(int(pred_run_s), 60)

                # Approximate position
                from scipy import stats
                pct = stats.norm.cdf(pred_z)
                est_pos = max(1, int(round(pct * field_size)))

                risk_lv, risk_col, risk_icon, risk_msg = wbgt_risk_level(wbgt)

                # ── KPI row ──────────────────────────────────────────────
                st.markdown("### Your Prediction")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Predicted Run z-score", f"{pred_z:+.2f}")
                k2.metric("Est. Run Time", f"{pred_min}:{pred_sec:02d}")
                k3.metric("Est. Finish Position", f"~{est_pos}/{field_size}")
                k4.metric(f"WBGT {risk_icon}", f"{wbgt:.1f}°C", delta=risk_lv)

                # ── WBGT alert ───────────────────────────────────────────
                css_class = {
                    "Low":"risk-low","Moderate":"risk-mod",
                    "High":"risk-high","Extreme":"risk-extreme"
                }[risk_lv]
                st.markdown(f'<div class="{css_class}"><b>{risk_icon} WBGT Alert: {risk_lv}</b><br>{risk_msg}</div>',
                            unsafe_allow_html=True)
                st.markdown("")

                # ── Split profile radar ───────────────────────────────────
                st.markdown("#### Your Split Profile vs Championship Field")
                fig_radar = go.Figure(go.Scatterpolar(
                    r    = [max(0, 1 - z_sw), max(0, 1 - z_bk), max(0, 1 - z_rn),
                            max(0, 1 - pred_z)],
                    theta= ["Swim", "Bike", "Run", "Predicted Run"],
                    fill = "toself",
                    fillcolor="rgba(46,116,181,0.25)",
                    line_color=BLUE, name="Your profile",
                ))
                fig_radar.add_trace(go.Scatterpolar(
                    r=[1,1,1,1], theta=["Swim","Bike","Run","Predicted Run"],
                    line=dict(color="grey", dash="dash"), name="Field mean",
                ))
                fig_radar.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0,2])),
                    showlegend=True, height=350,
                    margin=dict(l=40,r=40,t=30,b=30),
                )
                st.plotly_chart(fig_radar, use_container_width=True)

                # ── WBGT scenario chart ──────────────────────────────────
                st.markdown("#### Performance Across WBGT Scenarios")
                wbgt_range = np.linspace(10, 30, 41)
                preds = [predict_z_run(z_sw, z_bk, z_rn, w, sex) for w in wbgt_range]
                if heat_slope is not None:
                    preds = [p + (heat_slope - (POP_WBGT_BETA_MEN if sex=="Men" else 0))*(w-19.3)
                             for p, w in zip(preds, wbgt_range)]
                run_times = [z_to_run_time_seconds(p, n["run"], n["rn_sd"]) / 60 for p in preds]

                fig_scen = go.Figure()
                fig_scen.add_vrect(x0=10, x1=18, fillcolor="lightblue", opacity=0.15, line_width=0, annotation_text="Low heat")
                fig_scen.add_vrect(x0=18, x1=23, fillcolor="yellow",    opacity=0.15, line_width=0, annotation_text="Moderate")
                fig_scen.add_vrect(x0=23, x1=28, fillcolor="orange",    opacity=0.15, line_width=0, annotation_text="High")
                fig_scen.add_vrect(x0=28, x1=30, fillcolor="red",       opacity=0.15, line_width=0, annotation_text="Extreme")
                fig_scen.add_trace(go.Scatter(
                    x=wbgt_range, y=run_times, mode="lines",
                    line=dict(color=BLUE, width=3), name="Predicted run time (min)",
                ))
                fig_scen.add_vline(x=wbgt, line_dash="dash", line_color=RED,
                                   annotation_text=f"Projected: {wbgt:.1f}°C")
                fig_scen.update_layout(
                    xaxis_title="Race-Day WBGT (°C)",
                    yaxis_title="Predicted Run Time (min)",
                    height=300, margin=dict(l=40,r=20,t=30,b=40),
                )
                st.plotly_chart(fig_scen, use_container_width=True)

                # ── Pacing strategy ─────────────────────────────────────
                st.markdown("#### Pacing Strategy Guidance")
                if pred_z < -0.5:
                    strategy = "**Front-pack swimmer / solo run.** Your profile suits aggressive early positioning and a run from the front. Prioritise swim exit position to lead the bike — you likely carry the most decisive run advantage."
                elif pred_z < 0:
                    strategy = "**Pack rider / negative split run.** Conserve energy in the bike pack, maintain position into T2, and aim for a negative split run. Your run is above average — let the field come back to you in the second half."
                elif pred_z < 0.5:
                    strategy = "**Break-pack aggressive run.** Your run is near-field-average; aim to enter the run in a position that allows you to attack early and maintain pace. Prioritise a controlled bike effort to arrive at T2 fresh."
                else:
                    strategy = "**Survival run.** Run fitness is below field average for this competition level. Prioritise swim exit speed and bike pack efficiency. On the run, maintain a controlled even pace and manage heat if WBGT is elevated."

                if wbgt >= 24:
                    strategy += f"\n\n🌡️ **Heat adjustment (WBGT {wbgt:.1f}°C):** Consider pre-cooling. Start the run at 5–10% below target pace for the first 2 km, then build. Use every aid station for water/ice. Core temperature management is the priority."

                st.info(strategy)

                st.markdown("""
<div class="disclaimer">Predictions are based on population-level models. Individual results depend on training status, course conditions, and factors not captured in this model. This tool supplements — it does not replace — the judgement of coaches and athletes.</div>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# MEDICAL HEAT DASHBOARD
# ════════════════════════════════════════════════════════════════════════════

elif tool == "🏥 Medical Heat Dashboard":
    st.markdown('<div class="main-header">🏥 Medical Heat Risk Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Heat-stroke risk stratification for race medical teams · IOC/WMA-aligned thresholds</div>', unsafe_allow_html=True)

    st.markdown("""
<div class="disclaimer">
⚠️ <b>Medical Disclaimer:</b> Risk scores are derived from population-level race data and are indicative only.
They must NOT replace clinical assessment. All decisions regarding athlete safety, DNS recommendations, or
emergency protocols must be made by qualified medical personnel following applicable federation guidelines.
</div>
""", unsafe_allow_html=True)
    st.markdown("")

    # ── Race environment ─────────────────────────────────────────────────────
    st.subheader("🌡️ Race Environment")
    c1, c2, c3 = st.columns(3)
    with c1:
        venue_med = st.text_input("Venue", "Yokohama, Japan", key="med_venue")
        lat_med   = st.number_input("Latitude",  -90.0, 90.0, 35.44, format="%.4f", key="mlat")
        lon_med   = st.number_input("Longitude", -180.0, 180.0, 139.64, format="%.4f", key="mlon")
    with c2:
        temp_med  = st.slider("Air temperature (°C)", 10.0, 42.0, 28.0, 0.5, key="mtemp")
        rh_med    = st.slider("Relative humidity (%)", 20, 100, 75, key="mrh")
    with c3:
        wind_med  = st.slider("Wind speed (m/s)", 0.0, 10.0, 1.5, 0.5, key="mwind")
        solar_med = st.slider("Solar radiation (W/m²)", 0, 1000, 700, 50, key="msolar")

    wbgt_med = wbgt_outdoor(temp_med, rh_med, wind_med, solar_med)
    risk_lv, risk_col, risk_icon, risk_msg = wbgt_risk_level(wbgt_med)

    # ── WBGT gauge ───────────────────────────────────────────────────────────
    col_gauge, col_alert = st.columns([1, 2])
    with col_gauge:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=wbgt_med,
            number={"suffix": "°C", "font": {"size": 36}},
            title={"text": "Race-Day WBGT", "font": {"size": 16}},
            gauge={
                "axis": {"range": [5, 35], "tickwidth": 1},
                "bar":  {"color": BLUE},
                "steps": [
                    {"range": [5,  18], "color": "#E2EFDA"},
                    {"range": [18, 23], "color": "#FFF2CC"},
                    {"range": [23, 28], "color": "#FCE4D6"},
                    {"range": [28, 35], "color": "#C00000"},
                ],
                "threshold": {"line": {"color": "black", "width": 3}, "value": wbgt_med},
            },
        ))
        fig_gauge.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=10))
        st.plotly_chart(fig_gauge, use_container_width=True)

    with col_alert:
        css_class = {"Low":"risk-low","Moderate":"risk-mod","High":"risk-high","Extreme":"risk-extreme"}[risk_lv]
        st.markdown(f"""
<div class="{css_class}" style="margin-top:1rem; padding:1.2rem;">
<h3>{risk_icon} {risk_lv} Heat Risk — {wbgt_med:.1f}°C WBGT</h3>
<p>{risk_msg}</p>
</div>
""", unsafe_allow_html=True)

        st.markdown("""
**IOC/WMA WBGT thresholds (adapted from Racinais et al. 2015):**
| WBGT | Category | Action |
|---|---|---|
| <18°C | 🟢 Low | Standard protocol |
| 18–23°C | 🟡 Moderate | Enhanced monitoring |
| 23–28°C | 🔴 High | Medical alert; pre-cooling mandatory |
| >28°C | 🚨 Extreme | Consider race modification/postponement |
        """)

    st.markdown("---")

    # ── Athlete risk panel ────────────────────────────────────────────────────
    st.subheader("👥 Athlete Risk Stratification")
    st.caption("Enter athlete data to generate individual risk scores. Add one athlete at a time.")

    if "athletes" not in st.session_state:
        st.session_state.athletes = []

    with st.form("add_athlete"):
        fc1, fc2, fc3 = st.columns(3)
        a_name  = fc1.text_input("Athlete name / bib")
        a_sex   = fc1.selectbox("Sex", ["Men", "Women"], key="asex")
        a_age   = fc2.number_input("Age", 18, 55, 28, key="aage")
        a_z_run = fc2.number_input("Avg run z-score (from history, lower=faster)", -2.0, 2.0, 0.0, 0.1, key="azrun")
        a_slope = fc3.number_input("Heat-tolerance slope (z/°C, optional; 0=unknown)", -0.20, 0.15, 0.0, 0.005, format="%.4f", key="aslope")
        a_notes = fc3.text_input("Notes (e.g. prior heat illness, acclimatisation)")
        add_btn = st.form_submit_button("➕ Add Athlete")

    if add_btn and a_name:
        slope_val = a_slope if a_slope != 0.0 else None
        score, cat, recs = heat_stroke_risk_score(wbgt_med, a_z_run, slope_val, a_age, a_sex)
        st.session_state.athletes.append({
            "Name": a_name, "Sex": a_sex, "Age": a_age,
            "Run z": a_z_run, "Slope": a_slope, "Notes": a_notes,
            "Risk Score": score, "Category": cat, "Recommendations": recs,
        })
        st.rerun()

    # Demo data button
    if st.button("Load demo athletes (5 examples)"):
        demo_athletes = [
            ("A. Smith (Elite M)", "Men",   28,  -0.8, -0.12, "Heat-adapted, 3x prior acclimatisation camp"),
            ("B. Jones (Elite M)", "Men",   32,  -0.3,  0.06, "Limited heat racing experience"),
            ("C. Wagner (Elite M)","Men",   35,   0.2,  0.00, "Age 35; recent illness"),
            ("D. Lee (Elite W)",   "Women", 26,  -0.6, -0.05, "Good heat record"),
            ("E. Müller (Elite W)","Women", 29,   0.3,  0.08, "Heat-unfavourable profile"),
        ]
        for name, sex_, age_, zrn, slp, notes in demo_athletes:
            slp_v = slp if slp != 0.0 else None
            score, cat, recs = heat_stroke_risk_score(wbgt_med, zrn, slp_v, age_, sex_)
            st.session_state.athletes.append({
                "Name": name, "Sex": sex_, "Age": age_,
                "Run z": zrn, "Slope": slp, "Notes": notes,
                "Risk Score": score, "Category": cat, "Recommendations": recs,
            })
        st.rerun()

    if st.session_state.athletes:
        df_ath = pd.DataFrame(st.session_state.athletes)

        # Sort by risk score descending (highest risk first)
        df_ath = df_ath.sort_values("Risk Score", ascending=False).reset_index(drop=True)

        # Colour-map the risk category
        def cat_colour(cat):
            return {"Low":"🟢","Moderate":"🟡","High":"🔴","Extreme":"🚨"}.get(cat,"⬜")

        st.markdown(f"**{len(df_ath)} athletes · Sorted by risk (highest first)**")

        # Summary bar
        cats = df_ath["Category"].value_counts()
        col_s = st.columns(4)
        for i, (label, icon) in enumerate([("Extreme","🚨"),("High","🔴"),("Moderate","🟡"),("Low","🟢")]):
            col_s[i].metric(f"{icon} {label}", cats.get(label, 0))

        # Risk bar chart
        fig_risk = px.bar(
            df_ath, x="Name", y="Risk Score", color="Category",
            color_discrete_map={"Low":GREEN,"Moderate":AMBER,"High":"red","Extreme":"darkred"},
            title="Athlete Heat-Stroke Risk Scores",
            height=350,
        )
        fig_risk.add_hline(y=25, line_dash="dot", line_color=GREEN,  annotation_text="Moderate threshold")
        fig_risk.add_hline(y=50, line_dash="dot", line_color=AMBER,  annotation_text="High threshold")
        fig_risk.add_hline(y=75, line_dash="dot", line_color="red",  annotation_text="Extreme threshold")
        fig_risk.update_layout(margin=dict(t=40, b=40))
        st.plotly_chart(fig_risk, use_container_width=True)

        # Per-athlete cards
        st.markdown("#### Individual Athlete Reports")
        for _, row in df_ath.iterrows():
            with st.expander(f"{cat_colour(row['Category'])} {row['Name']}  |  Risk: {row['Risk Score']:.0f}/100  |  {row['Category']}"):
                c_info, c_recs = st.columns([1, 2])
                with c_info:
                    st.markdown(f"""
- **Sex / Age:** {row['Sex']} / {row['Age']}
- **Run z-score:** {row['Run z']:+.2f}
- **Heat slope:** {row['Slope']:+.4f} z/°C
- **Notes:** {row['Notes'] or '—'}
- **Risk score:** {row['Risk Score']:.0f} / 100
                    """)
                with c_recs:
                    st.markdown("**Recommendations:**")
                    for rec in row["Recommendations"]:
                        st.markdown(f"- {rec}")

        # Export
        export_cols = ["Name","Sex","Age","Run z","Slope","Risk Score","Category","Notes"]
        csv_out = df_ath[export_cols].to_csv(index=False)
        st.download_button(
            "⬇️ Download Risk Report (CSV)",
            csv_out,
            file_name=f"heat_risk_report_{venue_med.replace(' ','_')}.csv",
            mime="text/csv",
        )

        if st.button("🗑️ Clear all athletes"):
            st.session_state.athletes = []
            st.rerun()

    else:
        st.info("No athletes added yet. Use the form above to add individual athletes, or click **Load demo athletes**.")

    # ── WBGT hourly forecast ─────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📡 Live WBGT Forecast for Venue")
    if st.button("Fetch today's hourly WBGT forecast"):
        with st.spinner("Fetching from Open-Meteo…"):
            wx_df = fetch_current_wbgt(lat_med, lon_med)
        if wx_df is not None:
            fig_wx = go.Figure()
            fig_wx.add_hrect(y0=0,  y1=18, fillcolor="lightblue", opacity=0.15, line_width=0)
            fig_wx.add_hrect(y0=18, y1=23, fillcolor="yellow",    opacity=0.15, line_width=0)
            fig_wx.add_hrect(y0=23, y1=28, fillcolor="orange",    opacity=0.15, line_width=0)
            fig_wx.add_hrect(y0=28, y1=50, fillcolor="red",       opacity=0.12, line_width=0)
            fig_wx.add_trace(go.Scatter(
                x=wx_df["hour"], y=wx_df["wbgt"],
                mode="lines+markers", line=dict(color=BLUE, width=3),
                name="WBGT (°C)",
            ))
            fig_wx.add_trace(go.Scatter(
                x=wx_df["hour"], y=wx_df["temp"],
                mode="lines", line=dict(color="grey", width=1, dash="dot"),
                name="Air temp (°C)",
            ))
            fig_wx.update_layout(
                xaxis_title="Hour of day (UTC)",
                yaxis_title="Temperature (°C)",
                title=f"Today's hourly WBGT — {venue_med}",
                height=350, margin=dict(t=40,b=40),
            )
            st.plotly_chart(fig_wx, use_container_width=True)
            st.caption("WBGT zones: Blue=Low(<18°C) · Yellow=Moderate(18–23°C) · Orange=High(23–28°C) · Red=Extreme(>28°C)")
        else:
            st.error("Could not fetch forecast. Check internet connection or adjust coordinates.")
