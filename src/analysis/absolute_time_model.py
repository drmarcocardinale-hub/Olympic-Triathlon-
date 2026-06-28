"""
Absolute race-time analysis: effect of environmental heat (WBGT) on
mean split times at the race level.

Environmental conditions are classified using World Triathlon Heat Stress
flag thresholds (World Triathlon Technical Regulations):
  🟢 Green  < 25.7°C WBGT — Low heat stress
  🔵 Blue   25.7–27.8°C   — Moderate heat stress
  🟠 Orange 27.9–30.0°C   — High heat stress
  🔴 Red    30.1–32.2°C   — Very high heat stress
  ⬛ Black  > 32.2°C      — Extreme heat stress

Analysis approach:
  1. Aggregate athlete-level data to race-sex means (one row per race × sex).
  2. Fit linear OLS: mean_time ~ WBGT — tests for a continuous linear relationship.
  3. Fit threshold model: mean_time ~ WBGT + I(WBGT ≥ 25.7) — captures the
     non-linear performance collapse at the Green→Blue flag boundary.
  4. Category comparison: t-test between Blue/above (WBGT ≥ 25.7°C)
     and Green (< 25.7°C) races.
  5. Category means by World Triathlon flag level.
  6. Save coefficient tables and category means.

Key findings will update after re-running with new threshold. Previous run
(HOT_THRESHOLD = 25.0°C):
  Men:   run +505s (p=0.001), bike +1000s (p=0.010) in hot races
  Women: run +619s (p=0.001) in hot races
"""
from __future__ import annotations
import pathlib
import numpy as np
import pandas as pd
from scipy import stats

ROOT   = pathlib.Path(__file__).resolve().parents[2]
MASTER = ROOT / "data" / "processed" / "master.parquet"
TAB    = ROOT / "outputs" / "tables"

# World Triathlon Green→Blue flag boundary (hot/cool split for threshold model)
HOT_THRESHOLD = 25.7
# Reference WBGT for cool-race baseline (study population mean)
COOL_REFERENCE = 20.0

OUTCOMES = [
    ("run_mean",   "Run split (10 km)"),
    ("bike_mean",  "Bike split (40 km)"),
    ("swim_mean",  "Swim split (1500 m)"),
    ("total_mean", "Total race time"),
]

# World Triathlon flag categories
WBGT_CATS = {
    "Green (<25.7°C)":      (0,    25.7),
    "Blue (25.7–27.8°C)":   (25.7, 27.9),
    "Orange (27.9–30.0°C)": (27.9, 30.1),
    "Red (30.1–32.2°C)":    (30.1, 32.3),
    "Black (>32.2°C)":      (32.3, 60),
}


def load_race_level() -> pd.DataFrame:
    """
    Load master.parquet, filter to valid finishers with WBGT data,
    and aggregate to one row per race × sex.
    """
    df = pd.read_parquet(MASTER)
    # Normalise column names
    if "race_day_wbgt" not in df.columns and "wbgt_mean" in df.columns:
        df = df.rename(columns={"wbgt_mean": "race_day_wbgt"})

    # Exclude DNFs and implausible times (relays / sprint format / data errors)
    # Upper bounds: elite Olympic-distance times rarely exceed 180 min total
    df = df[
        (df["dnf_flag"] == 0) &
        (df["total_s"] > 3600)  & (df["total_s"] < 10800) &   # 60–180 min
        (df["bike_s"]  > 1800)  & (df["bike_s"]  < 6000)  &   # 30–100 min
        (df["run_s"]   > 1200)  & (df["run_s"]   < 3600)  &   # 20–60 min
        (df["swim_s"]  > 600)   & (df["swim_s"]  < 2400)  &   # 10–40 min
        (df["race_day_wbgt"].notna())
    ].copy()

    race = (
        df.groupby(["race_id", "sex", "venue", "year", "race_day_wbgt"])
        .agg(
            total_mean=("total_s", "mean"),
            bike_mean=("bike_s",  "mean"),
            run_mean=("run_s",   "mean"),
            swim_mean=("swim_s", "mean"),
            n_finishers=("athlete_id", "count"),
        )
        .reset_index()
    )
    race = race.rename(columns={"race_day_wbgt": "wbgt"})
    return race


def linear_ols(race: pd.DataFrame) -> pd.DataFrame:
    """
    OLS regression: mean_split_time ~ WBGT, separately by sex and outcome.
    Returns a table of slope, intercept, r, p-value, per-10°C effect.
    """
    rows = []
    for sex in ["men", "women"]:
        sub = race[race["sex"] == sex]
        for col, label in OUTCOMES:
            slope, intercept, r, p, se = stats.linregress(sub["wbgt"], sub[col])
            rows.append({
                "sex": sex, "outcome": label, "col": col,
                "n_races": len(sub),
                "slope_s_per_C": round(slope, 2),
                "intercept_s": round(intercept, 1),
                "r": round(r, 3),
                "p_value": round(p, 4),
                "per_10C_s": round(slope * 10, 1),
                "per_10C_min": f"{'+' if slope*10>=0 else ''}{slope*10/60:.2f}",
                "significant": p < 0.05,
            })
    return pd.DataFrame(rows)


def threshold_model(race: pd.DataFrame) -> pd.DataFrame:
    """
    OLS with a binary hot indicator: mean_time ~ wbgt + I(wbgt >= HOT_THRESHOLD).
    The hot coefficient (beta_hot) estimates the extra time penalty above the threshold.
    """
    rows = []
    for sex in ["men", "women"]:
        sub = race[race["sex"] == sex].copy()
        sub["hot"] = (sub["wbgt"] >= HOT_THRESHOLD).astype(float)
        w = sub["wbgt"].values
        h = sub["hot"].values

        for col, label in OUTCOMES:
            y = sub[col].values
            X = np.column_stack([np.ones(len(w)), w, h])
            b, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            y_pred = X @ b
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan

            # t-test for hot coefficient
            n = len(y)
            k = X.shape[1]
            mse = ss_res / max(n - k, 1)
            Xt = X.T @ X
            try:
                cov = mse * np.linalg.inv(Xt)
                se_hot = np.sqrt(cov[2, 2])
                t_hot = b[2] / se_hot
                p_hot = 2 * (1 - stats.t.cdf(abs(t_hot), df=n - k))
            except np.linalg.LinAlgError:
                se_hot = p_hot = np.nan

            rows.append({
                "sex": sex, "outcome": label, "col": col,
                "beta_wbgt": round(b[1], 2),
                "beta_hot_s": round(b[2], 1),
                "beta_hot_min": f"{b[2]/60:+.2f}",
                "se_hot": round(se_hot, 1) if not np.isnan(se_hot) else np.nan,
                "p_hot": round(p_hot, 4) if not np.isnan(p_hot) else np.nan,
                "r2": round(r2, 3),
                "significant": p_hot < 0.05 if not np.isnan(p_hot) else False,
                "n_hot": int(sub["hot"].sum()),
                "n_cool": int((1 - sub["hot"]).sum()),
            })
    return pd.DataFrame(rows)


def hot_cool_comparison(race: pd.DataFrame) -> pd.DataFrame:
    """
    Independent-samples t-test: Blue flag or above (WBGT ≥ 25.7°C) vs
    Green flag (<25.7°C) mean times. Uses World Triathlon threshold.
    """
    rows = []
    for sex in ["men", "women"]:
        sub = race[race["sex"] == sex]
        cool = sub[sub["wbgt"] < HOT_THRESHOLD]
        hot  = sub[sub["wbgt"] >= HOT_THRESHOLD]
        for col, label in OUTCOMES:
            diff = hot[col].mean() - cool[col].mean()
            t, p = stats.ttest_ind(hot[col], cool[col])
            m = int(abs(diff) // 60); s = int(abs(diff) % 60)
            rows.append({
                "sex": sex, "outcome": label,
                "n_hot": len(hot), "n_cool": len(cool),
                "mean_cool_s": round(cool[col].mean(), 1),
                "mean_hot_s":  round(hot[col].mean(), 1),
                "diff_s": round(diff, 1),
                "diff_fmt": f"+{m}m{s:02d}s" if diff > 0 else f"-{m}m{s:02d}s",
                "t_stat": round(t, 3),
                "p_value": round(p, 4),
                "significant": p < 0.05,
            })
    return pd.DataFrame(rows)


def category_means(race: pd.DataFrame) -> pd.DataFrame:
    """Mean split times by World Triathlon flag category."""
    bins   = [v[0] for v in WBGT_CATS.values()] + [60]
    labels = list(WBGT_CATS.keys())
    race = race.copy()
    race["wbgt_cat"] = pd.cut(race["wbgt"], bins=bins, labels=labels)
    rows = []
    for cat in labels:
        sub = race[race["wbgt_cat"] == cat]
        for col, label in OUTCOMES:
            rows.append({
                "wbgt_cat": cat,
                "outcome": label,
                "n": len(sub),
                "mean_s": round(sub[col].mean(), 1) if len(sub) > 0 else np.nan,
                "se_s": round(sub[col].sem(), 1)   if len(sub) > 1 else np.nan,
            })
    return pd.DataFrame(rows)


def heat_time_coefficients(ols: pd.DataFrame, threshold: pd.DataFrame) -> pd.DataFrame:
    """
    Export the key coefficients used by the digital twin for real-time
    time-impact estimation. Merges linear beta and threshold hot_delta.
    """
    lin = ols[["sex", "col", "slope_s_per_C", "r", "p_value"]].copy()
    thr = threshold[["sex", "col", "beta_hot_s", "p_hot", "r2", "significant"]].copy()
    thr = thr.rename(columns={"beta_hot_s": "hot_delta_s",
                               "p_hot": "p_hot", "r2": "threshold_r2"})
    merged = lin.merge(thr, on=["sex", "col"])
    merged["wbgt_ref"] = COOL_REFERENCE
    merged["hot_threshold"] = HOT_THRESHOLD
    return merged


def main():
    TAB.mkdir(parents=True, exist_ok=True)
    print("Loading race-level data...")
    race = load_race_level()
    print(f"  {len(race)} race-sex observations | "
          f"WBGT {race['wbgt'].min():.1f}–{race['wbgt'].max():.1f}°C | "
          f"Hot races (≥{HOT_THRESHOLD}°C): {(race['wbgt']>=HOT_THRESHOLD).sum()}")

    print("\n── LINEAR OLS: mean split time ~ WBGT ──")
    ols = linear_ols(race)
    print(ols[["sex","outcome","slope_s_per_C","per_10C_min","r","p_value","significant"]]
          .to_string(index=False))
    ols.to_csv(TAB / "absolute_time_linear_ols.csv", index=False)

    print("\n── THRESHOLD MODEL: time ~ WBGT + hot(≥25°C) ──")
    thr = threshold_model(race)
    print(thr[["sex","outcome","beta_hot_s","beta_hot_min","p_hot","r2","n_hot","significant"]]
          .to_string(index=False))
    thr.to_csv(TAB / "absolute_time_threshold_model.csv", index=False)

    print("\n── HOT vs COOL: mean time difference ──")
    comp = hot_cool_comparison(race)
    print(comp[["sex","outcome","n_hot","n_cool","diff_fmt","t_stat","p_value","significant"]]
          .to_string(index=False))
    comp.to_csv(TAB / "absolute_time_hot_vs_cool.csv", index=False)

    print("\n── CATEGORY MEANS ──")
    cats = category_means(race)
    pivot = cats.pivot_table(index=["outcome"], columns="wbgt_cat",
                             values="mean_s", aggfunc="first")
    print(pivot.round(0).to_string())
    cats.to_csv(TAB / "absolute_time_category_means.csv", index=False)

    print("\n── HEAT TIME COEFFICIENTS (for digital twin) ──")
    coefs = heat_time_coefficients(ols, thr)
    coefs.to_csv(TAB / "heat_time_coefficients.csv", index=False)
    print(coefs[["sex","col","slope_s_per_C","hot_delta_s","p_hot","threshold_r2","significant"]]
          .to_string(index=False))

    print(f"\nAll tables saved to {TAB}/")


if __name__ == "__main__":
    main()
