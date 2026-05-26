"""Nested 5-fold CV for GBM hyperparameter tuning.

Outer loop: 5-fold CV reports generalisation AUC.
Inner loop: RandomizedSearch on training fold tunes learning_rate, max_depth,
n_estimators within reviewer-specified ranges.

Computes for T1 (surface), T2 (+ lexical), T3 (full) feature tiers.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import (RandomizedSearchCV, StratifiedKFold)

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


PARAM_DIST = {
    "learning_rate": [0.01, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2],
    "max_depth": [3, 4, 5, 6, 7],
    "n_estimators": [100, 150, 200, 300, 400, 500],
}

T1 = ["FRE", "ARI", "WC", "TTR", "MLS"]
T2 = T1 + ["MTLD", "NomR"]
T3 = T2 + ["MCD", "MaxCD", "DC_C", "CT_T", "MLC",
            "MAL", "MaxAL", "LeftBR", "MeanArcCross", "MaxArcCross"]


def nested_cv(df, feats, y, label, n_inner_iter=12):
    outer = StratifiedKFold(n_splits=5, shuffle=True, random_state=2026)
    inner = StratifiedKFold(n_splits=3, shuffle=True, random_state=2026)
    X = df[feats].fillna(0.0).values
    fold_aucs = []
    best_params_per_fold = []
    for fold_i, (tr, te) in enumerate(outer.split(X, y)):
        rs = RandomizedSearchCV(
            estimator=GradientBoostingClassifier(random_state=2026),
            param_distributions=PARAM_DIST,
            n_iter=n_inner_iter,
            cv=inner,
            scoring="roc_auc",
            random_state=2026,
            n_jobs=1,
        )
        rs.fit(X[tr], y[tr])
        proba = rs.predict_proba(X[te])[:, 1]
        auc = roc_auc_score(y[te], proba)
        fold_aucs.append(auc)
        best_params_per_fold.append(rs.best_params_)
        log(f"step REV2/B3 · {label} outer fold {fold_i+1}/5 AUC={auc:.4f} "
            f"best={rs.best_params_}")
    return {
        "label": label,
        "n_feat": len(feats),
        "mean_auc": float(np.mean(fold_aucs)),
        "sd_auc": float(np.std(fold_aucs)),
        "fold_aucs": [round(a, 4) for a in fold_aucs],
        "best_params": best_params_per_fold,
    }


def main() -> int:
    metrics_path = HERE / "data" / "unified_v2" / "metrics_v3_sm.csv"
    if not metrics_path.exists():
        log("step REV2/B3 · ERROR · v3 metrics missing")
        return 1
    log("step REV2/B3 · nested CV begin")
    df = pd.read_csv(metrics_path)
    df = df.dropna(subset=["bucket"])
    df["y"] = (df["bucket"] == "high_density").astype(int)
    y = df["y"].values
    log(f"step REV2/B3 · n={len(df)} (high={int(y.sum())} base={int((1-y).sum())})")

    results = []
    for tier_name, feats in [("T1_surface", T1), ("T2_lex", T2), ("T3_full", T3)]:
        log(f"step REV2/B3 · tier {tier_name} ({len(feats)} feats)")
        results.append(nested_cv(df, feats, y, tier_name))

    out_dir = HERE / "data" / "unified_v2"
    with (out_dir / "nested_cv_gbm.json").open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    md = ["# Nested 5-fold CV for GBM (with inner RandomizedSearch)",
          "",
          "Outer loop: 5-fold StratifiedKFold; inner loop: 3-fold CV with 12 "
          "random hyperparameter samples drawn from "
          f"`{json.dumps(PARAM_DIST)}`.  Reports mean outer-fold AUC and the "
          "best inner-loop parameters per outer fold.",
          "",
          "| Tier | # feat | Mean AUC | SD | Per-fold AUC |",
          "|------|--------|----------|------|--------------|"]
    for r in results:
        md.append(f"| {r['label']} | {r['n_feat']} | {r['mean_auc']:.4f} "
                  f"| {r['sd_auc']:.4f} | {', '.join(f'{a:.4f}' for a in r['fold_aucs'])} |")
    md.append("")
    md.append("## Best hyperparameters per outer fold (T3-full)")
    for i, params in enumerate(results[-1]["best_params"]):
        md.append(f"- Fold {i+1}: " + ", ".join(f"{k}={v}" for k, v in params.items()))
    (out_dir / "nested_cv_gbm.md").write_text("\n".join(md) + "\n",
                                                encoding="utf-8")
    log("step REV2/B3 · nested CV done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
