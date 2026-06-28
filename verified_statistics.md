# Verified Statistics — Olympic Triathlon Study
Generated: 2026-06-28 from master.parquet after WBGT backfill (301/339 races)

---

## Table 1 — Dataset Characteristics (VERIFIED)

| Parameter | Verified value |
|-----------|---------------|
| Study period | 2015–2025 |
| Total events | **339** (147 WCS + 192 Olympic Games) |
| Athlete-race records (all) | **7,415** |
| Athlete-race records (finishers) | **6,561** |
| Unique athletes | **3,060** |
| WBGT coverage | **301/339 races (88.8%)** |
| WBGT range | **7.1–28.0°C** |
| WBGT mean ± SD | **18.9 ± 4.3°C** |
| Overall DNF rate | **11.5%** (854 of 7,415) |

### By sex (finishers)
| Sex | Finisher race-starts | Events |
|-----|---------------------|--------|
| Men | 3,923 | 171 |
| Women | 2,638 | 164 |

---

## Discipline Decomposition

Subset: finishers with complete z-scores (z_swim, z_bike, z_run, z_total).

| Sex | n race-starts | Events |
|-----|--------------|--------|
| Men | 3,726 | 155 |
| Women | 2,520 | 145 |

### Pearson r with z_total (all p < 0.001)
| Sex | r_swim | r_bike | r_run |
|-----|--------|--------|-------|
| Men | +0.409 | +0.720 | +0.708 |
| Women | +0.426 | +0.808 | +0.775 |

### XGBoost feature importance (podium prediction)
| Sex | Swim | Bike | Run |
|-----|------|------|-----|
| Men | 26.6% | 36.0% | **37.5%** |
| Women | 27.0% | 27.7% | **45.3%** |

---

## Digital Twin Model Performance (Table 3 — VERIFIED)

| Sex | MAE (z-units) | r | Baseline MAE | n_train | n_test |
|-----|--------------|---|-------------|---------|--------|
| Men | **0.490** | **0.383** | 0.512 | 3,154 | 769 |
| Women | **0.468** | **0.295** | 0.444 | 2,110 | 522 |

Note: MAE improved from 0.514/0.488 (50-race WBGT subset) to 0.490/0.468 after backfill.

---

## Heat Model (WBGT-Dependent)

### DNF rates by World Triathlon flag category

| Flag | WBGT | Men starts | Men DNF% | Women starts | Women DNF% |
|------|------|-----------|----------|-------------|------------|
| Green | <25.7°C | 3,925 (142 events) | **12.7%** | 2,594 (136 events) | **11.7%** |
| Blue | 25.7–27.8°C | 141 (11 events) | **16.3%** | 96 (10 events) | **18.8%** |
| Orange | 27.8–30.0°C | 31 (1 event) | **3.2%** | 14 (1 event) | **7.1%** |
| Red | 30.0–32.2°C | 0 | — | 0 | — |
| Black | >32.2°C | 0 | — | 0 | — |

> Max WBGT = **28.0°C** → only Green, Blue, and Orange conditions observed.
> The Orange result (3.2%/7.1% DNF) comes from a **single event** and should not be over-interpreted.

### WBGT vs overall performance
- Men: r(WBGT, z_total) = −0.005, p = 0.75 (n = 3,576) — not significant
- Women: r(WBGT, z_total) = +0.055, p = 0.008 (n = 2,376) — small positive effect

---

## Heat Tolerance Slope Analysis (UPDATED)

Inclusion: ≥3 races with WBGT data, ≥3°C WBGT spread within athlete

| Sex | Athletes qualifying | Mean slope | SD | t | p |
|-----|-------------------|-----------|-----|---|---|
| Men | **391** | −0.0077 | 0.0821 | −1.85 | 0.065 |
| Women | **271** | +0.0090 | 0.0905 | +1.63 | 0.104 |

- Men heat tolerant (slope > 0): 185/391 (47.3%)
- Men heat sensitive (slope < 0): 206/391 (52.7%)
- Women heat tolerant (slope > 0): 170/271 (62.7%)
- Women heat sensitive (slope < 0): 101/271 (37.3%)

Neither sex shows a statistically significant mean slope (p > 0.05), suggesting
heterogeneous individual responses rather than a systematic population-level effect.

---

## Water Temperature (swim performance)

- Events with water temp: 59, finisher rows: 1,657
- Water temp range: 11.9–30.0°C (mean 21.3°C)
- Wetsuit forbidden: 1,017 rows; permitted: 539 rows

### Unadjusted and partial correlations (water temp vs z_swim)
After WBGT backfill, partial correlations use a larger shared subset (53 events, n=1,548):

| Sex | n | Unadj r | p | Partial r (WBGT-adj) | p |
|-----|---|---------|---|----------------------|---|
| Men | 852 | +0.022 | 0.51 | **+0.043** | 0.21 |
| Women | 696 | +0.029 | 0.45 | **+0.068** | 0.07 |

Note: partial r values attenuated compared to pre-backfill subset (was +0.12/+0.11).
The smaller previous subset (23 events) oversampled hotter races, inflating the partial r.
The larger current subset is more representative.

---

## Key Manuscript Corrections Needed

1. **Table 1**: Update all 6 values (events, records, athletes, WBGT coverage/range/mean)
2. **Table 3**: MAE → 0.490 (men), 0.468 (women); r → 0.383 (men), 0.295 (women)
3. **XGBoost run importance**: was "53%" → correct is 37.5% (men) / 45.3% (women)
4. **Water temp partial r**: was "+0.12 (p=0.025)"  → correct is +0.043 (p=0.21) for men; +0.068 (p=0.07) for women — no longer statistically significant in the full dataset
5. **DNF extreme heat**: now have limited Orange data (1 event only); no Red/Black
6. **Heat tolerance n**: 89/86 → 391/271 athletes (much larger pool)
7. **WBGT max**: 27.2°C (pre-backfill) → 28.0°C (post-backfill)
