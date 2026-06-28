"""
Water temperature analysis for Olympic Triathlon Championship events.

Water temperature is sourced from the World Triathlon official results API
(results.meta.temperature_water in each race JSON). Values are merged into
master.parquet alongside a wetsuit_allowed flag (0 = forbidden, 1 = allowed),
derived from results.meta.wetsuit.

Analysis steps
--------------
1. Extract water_temp_c and wetsuit_allowed from raw JSON files.
2. Merge into master.parquet as new columns.
3. Descriptive statistics (range, mean, wetsuit usage).
4. Collinearity check: Pearson r between water temperature and WBGT at the
   race level (requires events with both measures).
5. Unadjusted correlation: Pearson r between water temperature and z_swim.
6. Partial correlation controlling for WBGT (restricted to events with both
   water temperature and WBGT available simultaneously).
7. One-way ANOVA: z_swim across cold / moderate / warm water categories.

Key thresholds
--------------
- Wetsuit forbidden at water temperatures ≥ 20°C (World Triathlon rules).
  (Note: official threshold is 20°C; some events use 24°C for elite racing.)
- Water temperature categories: cold < 18°C | moderate 18–24°C | warm > 24°C

Statistical note on partial correlations
-----------------------------------------
Partial r can only be computed on rows where BOTH water_temp_c AND
race_day_wbgt are non-null simultaneously. After WBGT backfill (301/339 races,
88.8%) the shared subset is 53 events (n ≈ 1,548 finisher rows), substantially
larger than the pre-backfill subset (23 events, n ≈ 659). The expanded subset
is more representative; partial r estimates are attenuated (men +0.043 p=0.21,
women +0.068 p=0.07 — neither statistically significant).
Unadjusted r uses all rows with water_temp_c regardless of WBGT availability.
"""
from __future__ import annotations
import json
import pathlib
import numpy as np
import pandas as pd
from scipy import stats

ROOT   = pathlib.Path(__file__).resolve().parents[2]
RAW    = ROOT / "data" / "raw"
MASTER = ROOT / "data" / "processed" / "master.parquet"
TAB    = ROOT / "outputs" / "tables"

# Water temperature category boundaries (°C)
WATER_CATS = {
    "cold (<18°C)":       (0,  18),
    "moderate (18–24°C)": (18, 24),
    "warm (>24°C)":       (24, 50),
}


# ── Step 1: Extract water temperature from raw JSON ────────────────────────

def extract_water_temps(raw_dir: pathlib.Path) -> pd.DataFrame:
    """
    Scan every raw JSON result file and return a DataFrame with one row per
    race_id containing water_temp_c and wetsuit_allowed.

    JSON structure:
        results.meta.temperature_water  → water temperature in °C (float or None)
        results.meta.wetsuit            → True/False/None
    """
    records = []
    for fpath in sorted(raw_dir.glob("*.json")):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue

        # Support both root-level and nested result keys
        results = data.get("results") or data
        meta = (results.get("meta") or {}) if isinstance(results, dict) else {}

        race_id   = data.get("race_id") or fpath.stem
        water_raw = meta.get("temperature_water")
        wetsuit   = meta.get("wetsuit")

        try:
            water_c = float(water_raw) if water_raw is not None else np.nan
        except (ValueError, TypeError):
            water_c = np.nan

        if wetsuit is True:
            wetsuit_flag = 1
        elif wetsuit is False:
            wetsuit_flag = 0
        else:
            wetsuit_flag = np.nan

        records.append({
            "race_id":        race_id,
            "water_temp_c":   water_c,
            "wetsuit_allowed": wetsuit_flag,
        })

    df = pd.DataFrame(records)
    df["water_temp_c"]    = pd.to_numeric(df["water_temp_c"],    errors="coerce")
    df["wetsuit_allowed"] = pd.to_numeric(df["wetsuit_allowed"], errors="coerce")
    return df


# ── Step 2: Merge into master.parquet ─────────────────────────────────────

def merge_water_temp(
    master_path: pathlib.Path,
    raw_dir: pathlib.Path,
    overwrite: bool = True,
) -> pd.DataFrame:
    """
    Extract water temperature from raw JSON files and merge into master.parquet.
    Returns the updated DataFrame. Saves in place if overwrite=True.
    """
    df   = pd.read_parquet(master_path)
    wt   = extract_water_temps(raw_dir)

    # Drop old columns if re-running
    df = df.drop(columns=[c for c in ("water_temp_c", "wetsuit_allowed") if c in df.columns])

    # Deduplicate: one row per race_id (water temp is race-level, not athlete-level)
    wt_unique = wt.drop_duplicates("race_id")

    # Ensure matching dtypes for merge key
    df["race_id"]       = df["race_id"].astype(str)
    wt_unique["race_id"] = wt_unique["race_id"].astype(str)

    df = df.merge(wt_unique, on="race_id", how="left")

    if overwrite:
        df.to_parquet(master_path, index=False)
        print(f"  master.parquet updated — {master_path}")

    return df


# ── Step 3–7: Analysis ─────────────────────────────────────────────────────

def run_analysis(df: pd.DataFrame) -> None:
    """Full water temperature analysis pipeline."""

    # Normalise WBGT column name
    if "race_day_wbgt" not in df.columns and "wbgt_mean" in df.columns:
        df = df.rename(columns={"wbgt_mean": "race_day_wbgt"})

    # Valid finishers only
    fin = df[(df["dnf_flag"] == 0) & df["z_swim"].notna()].copy()
    wt_rows = fin[fin["water_temp_c"].notna()]

    print("\n══ WATER TEMPERATURE ANALYSIS ══════════════════════════════════")

    # ── 3. Descriptives ───────────────────────────────────────────────────
    n_events   = wt_rows["race_id"].nunique()
    wt_vals    = wt_rows["water_temp_c"]
    n_no_wet   = (wt_rows["wetsuit_allowed"] == 0).sum()
    n_wet      = (wt_rows["wetsuit_allowed"] == 1).sum()

    print(f"\n── Descriptives ──")
    print(f"  Events with water temp: {n_events}")
    print(f"  Finisher rows:          {len(wt_rows)}")
    print(f"  Water temp range:       {wt_vals.min():.1f}–{wt_vals.max():.1f}°C "
          f"(mean {wt_vals.mean():.1f}°C)")
    print(f"  Wetsuit forbidden:      {n_no_wet}")
    print(f"  Wetsuit permitted:      {n_wet}")

    # ── 4. Collinearity with WBGT (race level) ───────────────────────────
    both = (
        wt_rows[wt_rows["race_day_wbgt"].notna()]
        .groupby("race_id")
        .agg(water_temp_c=("water_temp_c", "first"),
             wbgt=("race_day_wbgt", "first"))
        .dropna()
    )
    r_col, p_col = stats.pearsonr(both["water_temp_c"], both["wbgt"])
    print(f"\n── Collinearity: water temp vs WBGT (race level, n={len(both)}) ──")
    print(f"  r = {r_col:.3f}, p = {p_col:.4f}")

    # ── 5. Unadjusted correlations ────────────────────────────────────────
    print(f"\n── Unadjusted correlation (water_temp vs z_swim) ──")
    for sex in ["men", "women"]:
        sub = wt_rows[wt_rows["sex"] == sex]
        r, p = stats.pearsonr(sub["water_temp_c"], sub["z_swim"])
        print(f"  {sex:6s}: r = {r:+.3f}, p = {p:.3f}, n = {len(sub)}")

    # ── 6. Partial correlations controlling for WBGT ─────────────────────
    print(f"\n── Partial correlation controlling for WBGT "
          f"(restricted to {len(both)} events with both measures) ──")
    restricted = wt_rows[wt_rows["race_day_wbgt"].notna()].copy()
    for sex in ["men", "women"]:
        sub = restricted[restricted["sex"] == sex][
            ["water_temp_c", "z_swim", "race_day_wbgt"]
        ].dropna()

        # Residualise both variables on WBGT via OLS
        def residuals(y: np.ndarray, x: np.ndarray) -> np.ndarray:
            slope, intercept, *_ = stats.linregress(x, y)
            return y - (slope * x + intercept)

        r_wt   = residuals(sub["water_temp_c"].values, sub["race_day_wbgt"].values)
        r_swim = residuals(sub["z_swim"].values,       sub["race_day_wbgt"].values)
        pr, pp = stats.pearsonr(r_wt, r_swim)
        print(f"  {sex:6s}: partial r = {pr:+.3f}, p = {pp:.3f}, n = {len(sub)}")

    # ── 7. One-way ANOVA by water temperature category ───────────────────
    print(f"\n── One-way ANOVA: z_swim by water temperature category ──")
    bins   = [v[0] for v in WATER_CATS.values()] + [99]
    labels = list(WATER_CATS.keys())
    wt_rows = wt_rows.copy()
    wt_rows["water_cat"] = pd.cut(wt_rows["water_temp_c"], bins=bins, labels=labels)

    for sex in ["men", "women"]:
        sub = wt_rows[wt_rows["sex"] == sex]
        groups = [sub[sub["water_cat"] == cat]["z_swim"].dropna().values
                  for cat in labels]
        groups = [g for g in groups if len(g) > 1]
        if len(groups) >= 2:
            F, p = stats.f_oneway(*groups)
        else:
            F, p = np.nan, np.nan
        print(f"  {sex:6s}: F = {F:.2f}, p = {p:.3f}")
        for cat in labels:
            g = sub[sub["water_cat"] == cat]["z_swim"].dropna()
            print(f"    {cat:25s}: n={len(g):4d}, mean z_swim={g.mean():+.3f}")

    print("\n══ END ══════════════════════════════════════════════════════════")


def main():
    TAB.mkdir(parents=True, exist_ok=True)
    print("Merging water temperature into master.parquet ...")
    df = merge_water_temp(MASTER, RAW)
    run_analysis(df)


if __name__ == "__main__":
    main()
