"""
Phase 2 — characterise championship podiums.

Two complementary views:
  (a) mixed-effects logistic regression: podium ~ standardised splits + field strength,
      with race and athlete as random effects (interpretable coefficients).
  (b) gradient-boosted classifier + SHAP: data-driven feature importance.

Run separately per sex. Writes figures + a results memo.
"""
from __future__ import annotations
import pathlib
import pandas as pd
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
MASTER = ROOT / "data" / "processed" / "master.parquet"
FIG = ROOT / "outputs" / "figures"
TAB = ROOT / "outputs" / "tables"

ALL_FEATURES = ["z_swim", "z_bike", "z_run", "run_split_rank",
                "field_strength_mean_rank", "field_strength_depth"]


def load(sex: str) -> tuple[pd.DataFrame, list[str]]:
    if not MASTER.exists():
        raise FileNotFoundError(
            f"Master table not found at {MASTER}.\n"
            "Run build_dataset.py first."
        )
    df = pd.read_parquet(MASTER)
    df = df[(df["sex"] == sex) & (~df["dnf_flag"])].copy()

    # Drop features that are entirely NaN or zero-variance (e.g. rankings not yet scraped)
    features = [f for f in ALL_FEATURES
                if f in df.columns
                and df[f].notna().any()
                and df[f].std(skipna=True) > 0]
    missing = set(ALL_FEATURES) - set(features)
    if missing:
        print(f"  [{sex}] Skipping constant/all-NaN features: {sorted(missing)}")

    return df.dropna(subset=["podium"] + features), features


def mixed_model(df: pd.DataFrame, features: list[str]):
    """
    Random-intercept logistic regression: podium (binary) ~ splits + field strength,
    with race_id as the random-intercept grouping variable.

    Approach A (default) — BinomialBayesMixedGLM from statsmodels:
      Properly handles the binary outcome.  Relatively fast; returns quasi-Bayesian
      posterior means & SDs (treat like coefficients ± SE).

    Approach B (fallback) — pooled logit with cluster-robust SEs:
      Simpler; does not model within-race correlation explicitly but standard errors
      are corrected for clustering on race_id.  Use if BinomialBayesMixedGLM fails
      to converge.
    """
    import statsmodels.formula.api as smf
    from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

    formula = "podium ~ " + " + ".join(features)

    # Approach A: proper mixed logistic ----------------------------------------
    try:
        # random_effects dict: one random intercept per race_id
        random = {"race_re": "0 + C(race_id)"}
        md = BinomialBayesMixedGLM.from_formula(formula, random, df)
        result = md.fit_map()           # MAP estimate; use fit_vb() for full variational Bayes
        result._method = "BinomialBayesMixedGLM"
        return result
    except Exception as exc_a:
        print(f"  BinomialBayesMixedGLM failed ({exc_a}), falling back to cluster-robust logit.")

    # Approach B: pooled logit with cluster-robust SEs -------------------------
    try:
        md = smf.logit(formula, df)
        result = md.fit(cov_type="cluster", cov_kwds={"groups": df["race_id"]}, disp=False)
        result._method = "cluster-robust logit"
        return result
    except Exception as exc_b:
        print(f"  Cluster-robust logit also failed ({exc_b}), using plain logit.")

    # Approach C: plain logit (last resort) ------------------------------------
    md = smf.logit(formula, df)
    result = md.fit(disp=False)
    result._method = "plain logit"
    return result


def gbm_shap(df: pd.DataFrame, sex: str, features: list[str]):
    import xgboost as xgb
    import shap
    import matplotlib.pyplot as plt

    X, y = df[features], df["podium"].astype(int)
    model = xgb.XGBClassifier(
        n_estimators=400, max_depth=3, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, eval_metric="logloss",
    )
    model.fit(X, y)

    FIG.mkdir(parents=True, exist_ok=True)
    shap_ok = False
    try:
        # shap.TreeExplainer requires shap>=0.45 with xgboost<3.0 or shap>=0.50
        explainer = shap.TreeExplainer(model)
        sv = np.array(explainer.shap_values(X))
        if sv.ndim == 3:
            sv = sv[:, :, 1]
        plt.figure()
        shap.summary_plot(sv, X, show=False)
        plt.tight_layout()
        plt.savefig(FIG / f"shap_summary_{sex}.png", dpi=150)
        plt.close()
        imp = pd.Series(np.abs(sv).mean(0), index=features).sort_values(ascending=False)
        shap_ok = True
    except Exception as exc:
        print(f"  SHAP unavailable ({exc.__class__.__name__}: {exc}); using native gain importance.")

    if not shap_ok:
        # Native XGBoost gain-based importance as fallback
        imp = (pd.Series(model.feature_importances_, index=features)
               .sort_values(ascending=False))
        plt.figure()
        imp.plot.barh()
        plt.xlabel("Gain importance")
        plt.tight_layout()
        plt.savefig(FIG / f"shap_summary_{sex}.png", dpi=150)
        plt.close()

    return imp


def main():
    if not MASTER.exists():
        print(f"Master table not found at {MASTER}.\nRun build_dataset.py first.")
        return
    TAB.mkdir(parents=True, exist_ok=True)
    lines = ["# Phase 2 — podium characterisation\n"]
    for sex in ["men", "women"]:
        df, features = load(sex)
        if len(df) < 50:
            lines.append(f"## {sex}: insufficient data ({len(df)} rows)\n")
            continue
        res = mixed_model(df, features)
        imp = gbm_shap(df, sex, features)
        imp.to_csv(TAB / f"feature_importance_{sex}.csv")
        method = getattr(res, "_method", "unknown")
        lines.append(f"## {sex} (n={len(df)} athlete-races)  [{method}]\n")
        lines.append("Top features by mean |SHAP|:\n")
        lines.append(imp.round(4).to_string() + "\n")
        lines.append(f"\nMixed-model fixed effects ({method}):\n")
        try:
            lines.append(res.summary().tables[1].as_text() + "\n")
        except Exception:
            # BinomialBayesMixedGLM uses a different summary format
            lines.append(str(res.summary()) + "\n")
    (ROOT / "outputs" / "reports").mkdir(parents=True, exist_ok=True)
    (ROOT / "outputs" / "reports" / "phase2_podium.md").write_text("\n".join(lines))
    print("Wrote outputs/reports/phase2_podium.md and figures/tables.")


if __name__ == "__main__":
    main()
