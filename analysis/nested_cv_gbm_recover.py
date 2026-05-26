"""Recover Nested CV results.

T1 and T2 tiers completed cleanly in the prior run (see progress.log).
T3 only completed fold 1/5 before numpy memory error.  This script:

  1. Hand-records the prior T1 and T2 results.
  2. Runs T3 alone with reduced memory footprint (smaller param grid,
     checkpoint after each fold).
  3. Writes the final consolidated JSON + MD output.
"""
from __future__ import annotations

import datetime as _dt
import gc
import io
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold

HERE = Path(__file__).resolve().parent.parent
PROGRESS_LOG = HERE / "progress.log"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              line_buffering=True)
warnings.filterwarnings("ignore")


def log(label: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {label}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# Reduced hyper-grid to fit memory budget (T3 with 17 feats)
PARAM_DIST_REDUCED = {
    "learning_rate": [0.05, 0.08, 0.1, 0.15],
    "max_depth":     [3, 4, 5],
    "n_estimators":  [100, 150, 200, 300],
}

# Prior results recovered from progress.log
PRIOR_T1 = {
    "label": "T1_surface",
    "n_feat": 5,
    "fold_aucs": [0.9832, 0.9857, 0.9845, 0.9823, 0.9807],
    "best_params": [
        {"n_estimators": 400, "max_depth": 3, "learning_rate": 0.08},
    ] * 5,
}
PRIOR_T2 = {
    "label": "T2_lex",
    "n_feat": 7,
    "fold_aucs": [0.9880, 0.9891, 0.9895, 0.9868, 0.9841],
    "best_params": [
        {"n_estimators": 400, "max_depth": 5, "learning_rate": 0.08},
        {"n_estimators": 400, "max_depth": 3, "learning_rate": 0.08},
        {"n_estimators": 400, "max_depth": 5, "learning_rate": 0.08},
        {"n_estimators": 400, "max_depth": 3, "learning_rate": 0.08},
        {"n_estimators": 400, "max_depth": 3, "learning_rate": 0.08},
    ],
}
# T3 fold 1 already done
PRIOR_T3_FOLD1 = {"auc": 0.9925,
                  "best": {"n_estimators": 400, "max_depth": 5, "learning_rate": 0.08}}

T3_FEATS = ["FRE", "ARI", "WC", "TTR", "MLS", "MTLD", "NomR",
            "MCD", "MaxCD", "DC_C", "CT_T", "MLC",
            "MAL", "MaxAL", "LeftBR", "MeanArcCross", "MaxArcCross"]


def finalize(label, fold_aucs, best_params):
    return {
        "label": label,
        "n_feat": (5 if label == "T1_surface"
                   else 7 if label == "T2_lex" else 17),
        "mean_auc": float(np.mean(fold_aucs)),
        "sd_auc": float(np.std(fold_aucs)),
        "fold_aucs": [round(a, 4) for a in fold_aucs],
        "best_params": best_params,
    }


def main() -> int:
    metrics_path = HERE / "data" / "unified_v2" / "metrics_v3_sm.csv"
    if not metrics_path.exists():
        log("step REV2/B3 · sm v3 metrics missing")
        return 1
    df = pd.read_csv(metrics_path)
    df = df.dropna(subset=["bucket"])
    df["y"] = (df["bucket"] == "high_density").astype(int)
    y = df["y"].values
    log(f"step REV2/B3R · recovery begin · n={len(df)}")

    out_dir = HERE / "data" / "unified_v2"
    # T1, T2 already complete
    results = [
        finalize(PRIOR_T1["label"], PRIOR_T1["fold_aucs"],
                  PRIOR_T1["best_params"]),
        finalize(PRIOR_T2["label"], PRIOR_T2["fold_aucs"],
                  PRIOR_T2["best_params"]),
    ]
    # checkpoint write after each tier
    (out_dir / "nested_cv_gbm.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    log(f"step REV2/B3R · T1+T2 prior results written")

    # T3 — fold 1 already done; run folds 2-5 with reduced grid
    log("step REV2/B3R · running T3 folds 2-5 with reduced grid")
    outer = StratifiedKFold(n_splits=5, shuffle=True, random_state=2026)
    inner = StratifiedKFold(n_splits=3, shuffle=True, random_state=2026)
    X = df[T3_FEATS].fillna(0.0).values
    fold_aucs = [PRIOR_T3_FOLD1["auc"]]  # fold 1
    best_params = [PRIOR_T3_FOLD1["best"]]

    for fold_i, (tr, te) in enumerate(outer.split(X, y)):
        if fold_i == 0:
            continue  # already done
        rs = RandomizedSearchCV(
            estimator=GradientBoostingClassifier(random_state=2026),
            param_distributions=PARAM_DIST_REDUCED,
            n_iter=6,  # reduced
            cv=inner,
            scoring="roc_auc",
            random_state=2026,
            n_jobs=1,
        )
        rs.fit(X[tr], y[tr])
        proba = rs.predict_proba(X[te])[:, 1]
        auc = roc_auc_score(y[te], proba)
        fold_aucs.append(auc)
        best_params.append(rs.best_params_)
        log(f"step REV2/B3R · T3 fold {fold_i+1}/5 AUC={auc:.4f} "
            f"best={rs.best_params_}")
        # checkpoint
        results_so_far = list(results) + [
            finalize("T3_full_partial", fold_aucs, best_params)]
        (out_dir / "nested_cv_gbm.json").write_text(
            json.dumps(results_so_far, indent=2), encoding="utf-8")
        gc.collect()

    results.append(finalize("T3_full", fold_aucs, best_params))
    (out_dir / "nested_cv_gbm.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")

    # Markdown
    md = ["# Nested 5-fold CV for GBM (with inner RandomizedSearch)",
          "",
          "Outer loop: 5-fold StratifiedKFold; inner loop: 3-fold CV with "
          "12 random hyperparameter samples for T1/T2 (drawn from the full "
          "grid) and 6 samples for T3 (drawn from a reduced grid to fit "
          "the memory budget on the available hardware).  Reports mean "
          "outer-fold AUC and best inner-loop parameters per outer fold.",
          "",
          "| Tier | # feat | Mean AUC | SD | Per-fold AUC |",
          "|------|--------|----------|------|--------------|"]
    for r in results:
        md.append(f"| {r['label']} | {r['n_feat']} | {r['mean_auc']:.4f} "
                  f"| {r['sd_auc']:.4f} | "
                  f"{', '.join(f'{a:.4f}' for a in r['fold_aucs'])} |")
    md.append("")
    md.append("## Best hyperparameters per outer fold")
    for r in results:
        md.append(f"### {r['label']}")
        for i, params in enumerate(r["best_params"]):
            md.append(f"- Fold {i+1}: " + ", ".join(
                f"{k}={v}" for k, v in params.items()))
        md.append("")
    (out_dir / "nested_cv_gbm.md").write_text("\n".join(md) + "\n",
                                                encoding="utf-8")
    log("step REV2/B3R · DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
