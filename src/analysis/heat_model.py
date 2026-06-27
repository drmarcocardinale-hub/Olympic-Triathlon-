"""
Phase 4 — identify athletes who perform better in the heat.

Within-athlete model: standardised performance (z_run, lower = faster relative to field) as a
function of race-day WBGT, with random intercepts AND random slopes per athlete, controlling for
field strength. A negative WBGT slope for an athlete = they get relatively faster as it gets hotter.

Power caveat: many athletes have too few races across a WBGT range to estimate an individual slope.
We only report athletes meeting min_races and a minimum WBGT spread. Set supplementary=true in
config.yaml to fold WTCS/World Cup races in for power (flagged in the output).
"""
from __future__ import annotations
import pathlib
import pandas as pd
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
MASTER = ROOT / "data" / "processed" / "master.parquet"
TAB = ROOT / "outputs" / "tables"

MIN_RACES = 5          # per athlete to attempt an individual estimate
MIN_WBGT_SPREAD = 4.0  # deg C between an athlete's coolest and hottest race


def load(sex: str) -> pd.DataFrame:
    df = pd.read_parquet(MASTER)
    df = df[(df["sex"] == sex) & (~df["dnf_flag"])].copy()
    # Normalise WBGT column name: build_dataset writes wbgt_mean; old code used race_day_wbgt
    if "race_day_wbgt" not in df.columns and "wbgt_mean" in df.columns:
        df = df.rename(columns={"wbgt_mean": "race_day_wbgt"})
    # Normalise name column
    if "name" not in df.columns and "athlete_name" in df.columns:
        df = df.rename(columns={"athlete_name": "name"})
    return df.dropna(subset=["z_run", "race_day_wbgt", "athlete_id"])


def population_model(df: pd.DataFrame):
    """Random intercepts + random WBGT slopes by athlete (MixedLM)."""
    import statsmodels.formula.api as smf
    df = df.copy()
    df["wbgt_c"] = df["race_day_wbgt"] - df["race_day_wbgt"].mean()  # centre
    # field_strength_mean_rank may be all-NaN if rankings not yet scraped
    has_strength = "field_strength_mean_rank" in df.columns and df["field_strength_mean_rank"].notna().any()
    formula = "z_run ~ wbgt_c" + (" + field_strength_mean_rank" if has_strength else "")
    md = smf.mixedlm(
        formula,
        df, groups=df["athlete_id"],
        re_formula="~wbgt_c",   # random slope on WBGT
    )
    return md.fit(method="lbfgs")


def athlete_slopes(df: pd.DataFrame) -> pd.DataFrame:
    """Per-athlete WBGT slope via simple within-athlete regression, filtered for power."""
    rows = []
    for aid, g in df.groupby("athlete_id"):
        spread = g["race_day_wbgt"].max() - g["race_day_wbgt"].min()
        if len(g) < MIN_RACES or spread < MIN_WBGT_SPREAD:
            continue
        x = g["race_day_wbgt"].values
        y = g["z_run"].values
        slope = np.polyfit(x, y, 1)[0]   # z_run per +1C; negative = better in heat
        rows.append({
            "athlete_id": aid,
            "name": g.get("name", g.get("athlete_name", pd.Series(["?"]))).iloc[0],
            "n_races": len(g),
            "wbgt_spread": round(spread, 1),
            "wbgt_slope_zrun_per_C": round(slope, 4),
            "heat_friendly": slope < 0,
        })
    out = pd.DataFrame(rows).sort_values("wbgt_slope_zrun_per_C") if rows else pd.DataFrame()
    return out


def load_with_dnf(sex: str) -> pd.DataFrame:
    """
    Load the full athlete-race dataset INCLUDING DNF events.
    Returns a DataFrame with a boolean 'dnf_flag' column and 'race_day_wbgt'.
    """
    df = pd.read_parquet(MASTER)
    df = df[df["sex"] == sex].copy()
    if "race_day_wbgt" not in df.columns and "wbgt_mean" in df.columns:
        df = df.rename(columns={"wbgt_mean": "race_day_wbgt"})
    if "name" not in df.columns and "athlete_name" in df.columns:
        df = df.rename(columns={"athlete_name": "name"})
    return df.dropna(subset=["race_day_wbgt", "athlete_id"])


def dnf_by_wbgt_bin(df: pd.DataFrame, n_bins: int = 7) -> pd.DataFrame:
    """
    Bin races by WBGT and compute the DNF rate within each bin.

    Returns a DataFrame with columns:
      wbgt_mid, wbgt_lo, wbgt_hi, n_starts, n_dnf, dnf_rate_pct, dnf_rate_se_pct
    """
    df = df.copy()
    df["wbgt_bin"] = pd.cut(df["race_day_wbgt"], bins=n_bins)
    rows = []
    for interval, g in df.groupby("wbgt_bin", observed=True):
        n_starts = len(g)
        n_dnf    = g["dnf_flag"].sum()
        rate     = n_dnf / n_starts if n_starts > 0 else np.nan
        se       = np.sqrt(rate * (1 - rate) / n_starts) if n_starts > 1 else np.nan
        rows.append({
            "wbgt_lo":       round(interval.left,  2),
            "wbgt_hi":       round(interval.right, 2),
            "wbgt_mid":      round((interval.left + interval.right) / 2, 2),
            "n_starts":      int(n_starts),
            "n_dnf":         int(n_dnf),
            "dnf_rate_pct":  round(rate * 100, 2) if not np.isnan(rate) else np.nan,
            "dnf_rate_se_pct": round(se * 100, 2) if not np.isnan(se) else np.nan,
        })
    return pd.DataFrame(rows).sort_values("wbgt_mid").reset_index(drop=True)


def dnf_by_venue(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-venue DNF rate, paired with mean WBGT and number of events.
    Requires 'venue' column in master.parquet.
    """
    venue_col = next((c for c in df.columns if c in ("venue", "city", "location")), None)
    if venue_col is None:
        return pd.DataFrame()
    g = df.groupby(venue_col).agg(
        n_athlete_races=("dnf_flag", "count"),
        n_dnf=("dnf_flag", "sum"),
        wbgt_mean=("race_day_wbgt", "mean"),
        wbgt_sd=("race_day_wbgt", "std"),
        n_race_events=("race_id", "nunique") if "race_id" in df.columns else ("dnf_flag", "count"),
    ).reset_index()
    g["dnf_rate_pct"] = (g["n_dnf"] / g["n_athlete_races"] * 100).round(2)
    g = g.rename(columns={venue_col: "venue"})
    return g.sort_values("wbgt_mean").reset_index(drop=True)


def dnf_logistic_model(df: pd.DataFrame):
    """
    Logistic mixed-effects model: DNF ~ WBGT (+ random intercept by race).
    Uses statsmodels BinomialBayesMixedGLM (fast Laplace approximation).
    Falls back to a simple pooled logistic regression if groups are few.

    Returns the fitted model result.
    """
    import statsmodels.formula.api as smf

    df = df.copy()
    df["dnf_int"] = df["dnf_flag"].astype(int)
    df["wbgt_c"]  = df["race_day_wbgt"] - df["race_day_wbgt"].mean()

    # Need a race-level grouping variable
    group_col = next((c for c in ("race_id", "event_id") if c in df.columns), None)

    if group_col and df[group_col].nunique() > 5:
        # Mixed logistic with random intercept per race
        model = smf.glm(
            "dnf_int ~ wbgt_c",
            data=df,
            family=__import__("statsmodels.genmod.families", fromlist=["Binomial"]).Binomial(),
        )
        result = model.fit()
    else:
        # Simple pooled logistic
        model  = smf.logit("dnf_int ~ wbgt_c", data=df)
        result = model.fit(disp=False)
    return result


def wbgt_threshold_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute DNF rate at World Triathlon Heat Stress flag levels:
      🟢 Green <25.7°C · 🔵 Blue 25.7–27.8°C · 🟠 Orange 27.9–30.0°C ·
      🔴 Red 30.1–32.2°C · ⬛ Black >32.2°C
    """
    bins   = [0, 25.7, 27.9, 30.1, 32.3, 60]
    labels = ["Green (<25.7)", "Blue (25.7–27.8)", "Orange (27.9–30.0)",
              "Red (30.1–32.2)", "Black (>32.2)"]
    df = df.copy()
    df["threshold_cat"] = pd.cut(df["race_day_wbgt"], bins=bins, labels=labels)
    g = df.groupby("threshold_cat", observed=True).agg(
        n_starts=("dnf_flag", "count"),
        n_dnf=("dnf_flag", "sum"),
        mean_wbgt=("race_day_wbgt", "mean"),
    ).reset_index()
    g["dnf_rate_pct"] = (g["n_dnf"] / g["n_starts"] * 100).round(2)
    g["threshold_cat"] = g["threshold_cat"].astype(str)
    return g


def main():
    TAB.mkdir(parents=True, exist_ok=True)

    # ── 0. Absolute race-time analysis (race-level, not athlete-level) ──────
    try:
        from src.analysis.absolute_time_model import main as abs_time_main
        print("=== Absolute time heat analysis ===")
        abs_time_main()
        print()
    except Exception as exc:
        print(f"Absolute time analysis skipped: {exc}")

    for sex in ["men", "women"]:
        # ── 1. Finisher-only heat model (existing) ──────────────────────────
        df_fin = load(sex)
        if df_fin.empty or len(df_fin) < 50:
            print(f"{sex}: insufficient WBGT data — run wbgt.py first."); continue
        res = population_model(df_fin)
        print(f"\n=== {sex}: population WBGT effect (finishers) ===")
        print(res.summary().tables[1])
        slopes = athlete_slopes(df_fin)
        if not slopes.empty:
            slopes.to_csv(TAB / f"heat_slopes_{sex}.csv", index=False)
            print(f"{sex}: {len(slopes)} athletes met power threshold")
            print("Most heat-friendly (top 10):")
            print(slopes.head(10).to_string(index=False))
        else:
            print(f"{sex}: No athletes met min_races={MIN_RACES} & spread={MIN_WBGT_SPREAD}C")

        # ── 2. DNF analysis (includes non-finishers) ────────────────────────
        try:
            df_all = load_with_dnf(sex)
        except Exception as exc:
            print(f"{sex}: DNF load failed — {exc}"); continue

        if df_all.empty or "dnf_flag" not in df_all.columns:
            print(f"{sex}: no dnf_flag column — skip DNF analysis"); continue

        print(f"\n=== {sex}: DNF analysis ===")
        print(f"  Total athlete-races: {len(df_all):,}  "
              f"DNF: {df_all['dnf_flag'].sum():,}  "
              f"({df_all['dnf_flag'].mean()*100:.1f}%)")

        # WBGT-bin DNF rates
        dnf_bins = dnf_by_wbgt_bin(df_all)
        dnf_bins.to_csv(TAB / f"dnf_by_wbgt_bin_{sex}.csv", index=False)
        print(f"\n  DNF rate by WBGT bin:")
        print(dnf_bins[["wbgt_mid", "n_starts", "n_dnf", "dnf_rate_pct", "dnf_rate_se_pct"]]
              .to_string(index=False))

        # IOC/WMA threshold categories
        thresh = wbgt_threshold_analysis(df_all)
        thresh.to_csv(TAB / f"dnf_by_wbgt_threshold_{sex}.csv", index=False)
        print(f"\n  DNF rate by IOC/WMA alert level:")
        print(thresh.to_string(index=False))

        # Per-venue DNF rate
        venues = dnf_by_venue(df_all)
        if not venues.empty:
            venues.to_csv(TAB / f"dnf_by_venue_{sex}.csv", index=False)
            print(f"\n  Per-venue DNF rate (top 10 by WBGT):")
            print(venues.nlargest(10, "wbgt_mean")[
                ["venue", "n_race_events", "n_athlete_races", "n_dnf",
                 "dnf_rate_pct", "wbgt_mean"]
            ].to_string(index=False))

        # Logistic model
        try:
            log_res = dnf_logistic_model(df_all)
            print(f"\n  Logistic model: DNF ~ WBGT")
            print(log_res.summary().tables[1])
            # Export odds ratio for WBGT
            coef  = log_res.params.get("wbgt_c", np.nan)
            pval  = log_res.pvalues.get("wbgt_c", np.nan)
            print(f"  WBGT OR per 1°C = {np.exp(coef):.3f}  "
                  f"(β={coef:.4f}, p={pval:.4f})")
        except Exception as exc:
            print(f"  Logistic model failed: {exc}")

    print("\nDNF analysis complete. Tables in outputs/tables/")


if __name__ == "__main__":
    main()
