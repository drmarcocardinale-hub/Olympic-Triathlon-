"""
Phase 5 — digital twin.

Two layers:
  1. Predictive layer: given an athlete's race history + course + WBGT scenario, project expected
     splits and finishing position (gradient boosting trained on the master table).
  2. Strain layer: estimate physiological heat strain (core temperature trajectory, sustainable
     pacing) for the scenario using a predicted-heat-strain / thermoregulation model.

Be explicit in any interface built on this: it is an archetype-plus-history model personalised by
observed race history, NOT an individual physiological clone (the public data has no per-athlete
VO2max, sweat rate, etc.). Validate on a temporal hold-out (train earlier years, test latest).
"""
from __future__ import annotations
import pathlib
import pandas as pd
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
MASTER = ROOT / "data" / "processed" / "master.parquet"
MODELS = ROOT / "outputs" / "tables"

PRED_FEATURES_WBGT = ["z_swim_hist", "z_bike_hist", "z_run_hist", "z_total_hist", "race_day_wbgt"]
PRED_FEATURES_NO_WBGT = ["z_swim_hist", "z_bike_hist", "z_run_hist", "z_total_hist"]

# Empirically-derived discipline weights from OLS regression of z_total on z_swim + z_bike + z_run
# (normalised to sum to 1). Derived from n=3,726 men / n=2,520 women finisher-race observations.
# Men:   swim=0.101, bike=0.433, run=0.412  → normalised: swim=0.107, bike=0.456, run=0.434  (Σ≈0.946)
# Women: swim=0.095, bike=0.459, run=0.401  → normalised: swim=0.099, bike=0.479, run=0.419  (Σ≈0.954)
# Note: intercept ~0.05 (slightly positive mean z_total reflects faster-finishing survivors).
DISCIPLINE_WEIGHTS: dict[str, dict[str, float]] = {
    "men":   {"swim": 0.107, "bike": 0.456, "run": 0.434},
    "women": {"swim": 0.099, "bike": 0.479, "run": 0.419},
}


def _get_pred_features(df: pd.DataFrame) -> list[str]:
    """Use WBGT feature only if we have data; gracefully degrade otherwise."""
    feats = list(PRED_FEATURES_NO_WBGT)
    if "race_day_wbgt" in df.columns and df["race_day_wbgt"].notna().any():
        feats.append("race_day_wbgt")
    if "field_strength_mean_rank" in df.columns and df["field_strength_mean_rank"].notna().any():
        feats.append("field_strength_mean_rank")
    return feats


# ---- predictive layer ----------------------------------------------------------
def build_history_features(df: pd.DataFrame) -> pd.DataFrame:
    """Athlete rolling history (expanding mean of prior z-scores), strictly past races only."""
    # Normalise column names from build_dataset
    if "race_day_wbgt" not in df.columns and "wbgt_mean" in df.columns:
        df = df.rename(columns={"wbgt_mean": "race_day_wbgt"})
    df = df.sort_values(["athlete_id", "date"]).copy()
    for seg in ["z_swim", "z_bike", "z_run", "z_total"]:
        df[f"{seg}_hist"] = (df.groupby("athlete_id")[seg]
                               .apply(lambda s: s.shift().expanding().mean())
                               .reset_index(level=0, drop=True))
    return df


def train_predictive(sex: str):
    import xgboost as xgb
    df = build_history_features(pd.read_parquet(MASTER))
    df = df[(df["sex"] == sex) & (~df["dnf_flag"])].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Determine feature set (with/without WBGT)
    feats = _get_pred_features(df)

    # Drop only rows where z_total is missing — impute history NaNs with 0
    # (0 = population mean z-score: correct Bayesian prior for athletes with no prior history)
    df = df.dropna(subset=["z_total"])
    for f in feats:
        if f in df.columns:
            df[f] = df[f].fillna(0.0)

    # temporal hold-out: last 20% of dates
    cut = df["date"].quantile(0.8)
    train, test = df[df["date"] <= cut], df[df["date"] > cut]

    model = xgb.XGBRegressor(n_estimators=400, max_depth=3, learning_rate=0.05,
                             subsample=0.8, colsample_bytree=0.8, random_state=42)
    model.fit(train[feats], train["z_total"])
    preds = model.predict(test[feats])
    mae = float(np.abs(preds - test["z_total"]).mean())
    r = float(np.corrcoef(preds, test["z_total"])[0, 1])
    baseline_mae = float(np.abs(train["z_total"].mean() - test["z_total"]).mean())
    print(f"{sex}: MAE={mae:.3f}  r={r:.3f}  baseline_MAE={baseline_mae:.3f}  "
          f"train_n={len(train)}  test_n={len(test)}  [features: {feats}]")
    return model, feats, {"mae": mae, "r": r, "baseline_mae": baseline_mae,
                          "n_train": len(train), "n_test": len(test)}


# ---- strain layer --------------------------------------------------------------
def heat_strain(temp_c, rh_pct, wind_ms, solar_wm2, run_minutes=30, met=14.0):
    """
    Estimate heat strain for the run leg using the Predicted Heat Strain (PHS, ISO 7933) model
    from pythermalcomfort. met ~14 approximates elite 10 km running metabolic rate.
    Returns the model output (includes predicted rectal/core temperature rise and water loss).
    """
    from pythermalcomfort.models import phs
    return phs(
        tdb=temp_c, tr=temp_c + 0.0,  # use globe temp for tr in a full run
        v=wind_ms, rh=rh_pct, met=met, clo=0.2,
        posture=2, duration=run_minutes,
    )


def weighted_composite_z(z_swim: float, z_bike: float, z_run: float,
                          sex: str) -> float:
    """
    Compute a weighted composite performance z-score using empirically-derived
    discipline weights (OLS regression coefficients normalised to unit sum).

    Parameters
    ----------
    z_swim, z_bike, z_run : individual-discipline z-scores for this start
    sex : 'men' or 'women'

    Returns
    -------
    Weighted composite z (higher = slower / worse performance, consistent with z_total sign)
    """
    w = DISCIPLINE_WEIGHTS[sex]
    total_w = w["swim"] + w["bike"] + w["run"]
    return (w["swim"] * z_swim + w["bike"] * z_bike + w["run"] * z_run) / total_w


def scenario(model, athlete_hist: dict, course: dict, wbgt_inputs: dict, sex: str = "men"):
    """Combine both layers for one what-if. Wire to an interactive UI in Cowork (sliders for
    venue/WBGT/athlete) for the coach-facing tool.

    Parameters
    ----------
    model       : trained XGBRegressor from train_predictive(sex)
    athlete_hist: dict with keys z_swim_hist, z_bike_hist, z_run_hist, z_total_hist
    course      : dict with key field_strength_mean_rank
    wbgt_inputs : dict with keys wbgt, temp_c, rh_pct, wind_ms, solar_wm2
    sex         : 'men' or 'women' (needed for empirical discipline weights)
    """
    feats = PRED_FEATURES_WBGT if "wbgt" in wbgt_inputs else PRED_FEATURES_NO_WBGT
    row = {**athlete_hist, "race_day_wbgt": wbgt_inputs.get("wbgt", 0.0)}
    X = pd.DataFrame([row])[feats]
    pred_z_total = float(model.predict(X)[0])
    # Decompose projected z_total into discipline contributions using empirical weights
    w = DISCIPLINE_WEIGHTS[sex]
    discipline_contrib = {
        "swim": w["swim"] * athlete_hist.get("z_swim_hist", 0.0),
        "bike": w["bike"] * athlete_hist.get("z_bike_hist", 0.0),
        "run":  w["run"]  * athlete_hist.get("z_run_hist",  0.0),
    }
    strain = heat_strain(**{k: wbgt_inputs[k] for k in
                            ["temp_c", "rh_pct", "wind_ms", "solar_wm2"]
                            if k in wbgt_inputs})
    return {
        "predicted_z_total": pred_z_total,
        "discipline_weights": w,
        "discipline_contributions": discipline_contrib,
        "strain": strain,
    }


if __name__ == "__main__":
    print("Train the predictive layer once master.parquet has WBGT joined:")
    print("  model = train_predictive('men')")
    print("Then call scenario(model, athlete_hist, course, wbgt_inputs) for what-ifs.")
    print("Build the coach-facing slider UI as an artifact in Cowork on top of scenario().")
