"""Permutation importance complement to the RF impurity-based importance.

Permutation importance is robust to multicollinearity in a different way
than impurity importance: a feature's importance is the drop in held-out
score when its values are randomly shuffled.  Correlated features can
each show high importance if both carry independent signal at the model
margin, whereas impurity importance tends to split-vote across them.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import sys
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.model_selection import StratifiedKFold

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


T3_FEATS = ["FRE", "ARI", "WC", "TTR", "MLS", "MTLD", "NomR",
            "MCD", "MaxCD", "DC_C", "CT_T", "MLC",
            "MAL", "MaxAL", "LeftBR", "MeanArcCross", "MaxArcCross"]
DISPLAY = {"DC_C": "DC/C", "CT_T": "CT/T"}


def main() -> int:
    log("step PERM/0 · permutation importance begin")
    df = pd.read_csv(HERE / "data" / "unified_v2" / "metrics_v3_sm.csv")
    df = df.dropna(subset=["bucket"])
    df["y"] = (df["bucket"] == "high_density").astype(int)
    X = df[T3_FEATS].fillna(0.0).values
    y = df["y"].values
    log(f"step PERM/0 · n={len(df)}")

    # Hold out 20% test set for permutation
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=2026)
    tr_idx, te_idx = next(iter(skf.split(X, y)))
    log(f"step PERM/0 · train={len(tr_idx)} test={len(te_idx)}")

    rf = RandomForestClassifier(n_estimators=300, min_samples_leaf=2,
                                 class_weight="balanced", random_state=2026,
                                 n_jobs=1)
    log("step PERM/0 · fitting RF")
    rf.fit(X[tr_idx], y[tr_idx])
    log(f"step PERM/0 · RF test AUC = "
        f"{rf.score(X[te_idx], y[te_idx]):.4f}")

    log("step PERM/0 · computing permutation importance (n_repeats=15)")
    pi = permutation_importance(rf, X[te_idx], y[te_idx],
                                 n_repeats=15, random_state=2026,
                                 scoring="roc_auc", n_jobs=1)

    rows = []
    for i, feat in enumerate(T3_FEATS):
        rows.append({
            "feature": DISPLAY.get(feat, feat),
            "rf_impurity": float(rf.feature_importances_[i]),
            "perm_mean": float(pi.importances_mean[i]),
            "perm_sd": float(pi.importances_std[i]),
        })
    df_out = pd.DataFrame(rows).sort_values("perm_mean",
                                              ascending=False).reset_index(drop=True)
    df_out["rank_perm"] = df_out.index + 1
    df_out["rank_impurity"] = df_out["rf_impurity"].rank(
        method="dense", ascending=False).astype(int)
    df_out.to_csv(HERE / "data" / "unified_v2" /
                   "permutation_importance.csv", index=False)
    log("step PERM/0 · wrote permutation_importance.csv")

    log("step PERM/0 · top-5 permutation importance:")
    for _, r in df_out.head(8).iterrows():
        log(f"   {r['feature']:>16s}  perm={r['perm_mean']:.4f} "
            f"(sd {r['perm_sd']:.4f})  impurity={r['rf_impurity']:.4f} "
            f"(impurity-rank {int(r['rank_impurity'])})")

    # Side-by-side bar plot
    syn = {"MCD", "MaxCD", "DC/C", "CT/T", "MLC",
           "MAL", "MaxAL", "LeftBR", "MeanArcCross", "MaxArcCross"}
    lex = {"MTLD", "NomR"}

    def col_for(f):
        return "#c0392b" if f in syn else "#1f77b4" if f in lex else "#888888"

    fig, axes = plt.subplots(1, 2, figsize=(13, 6), dpi=160, sharey=False)
    # by impurity
    by_imp = df_out.sort_values("rf_impurity")
    axes[0].barh(by_imp["feature"], by_imp["rf_impurity"],
                  color=[col_for(f) for f in by_imp["feature"]])
    axes[0].set_xlabel("Random Forest impurity-based importance")
    axes[0].set_title("(a) Impurity importance\n"
                       "(sensitive to multicollinearity)", fontsize=10)
    axes[0].grid(True, axis="x", linestyle=":", alpha=0.4)
    # by permutation
    by_pi = df_out.sort_values("perm_mean")
    axes[1].barh(by_pi["feature"], by_pi["perm_mean"],
                  xerr=by_pi["perm_sd"],
                  color=[col_for(f) for f in by_pi["feature"]])
    axes[1].set_xlabel("Permutation importance (Δ test AUC, mean over 15 repeats)")
    axes[1].set_title("(b) Permutation importance\n"
                       "(robust to multicollinearity)", fontsize=10)
    axes[1].grid(True, axis="x", linestyle=":", alpha=0.4)

    fig.suptitle("Random Forest feature importance — impurity vs permutation\n"
                  "red = syntactic, blue = lexical, gray = surface",
                  fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(HERE / "figures" / "permutation_importance.png",
                 dpi=180, bbox_inches="tight")
    plt.close(fig)
    log("step PERM/0 · wrote figures/permutation_importance.png")

    # Markdown
    md = ["# Permutation Importance Complement to RF Impurity",
          "",
          "Permutation importance is computed by shuffling each feature on "
          "the held-out test split (20% stratified) and measuring the drop "
          "in test ROC-AUC, averaged over 15 random shuffles per feature. "
          "Unlike impurity importance, it is not split-vote-diluted by "
          "feature collinearity.",
          "",
          "| Rank (perm) | Feature | Perm Δ AUC (mean ± SD) | RF impurity | Rank (impurity) |",
          "|------|---------|------------------------|-------------|-----------------|"]
    for _, r in df_out.iterrows():
        md.append(f"| {int(r['rank_perm'])} | {r['feature']} "
                  f"| {r['perm_mean']:.4f} ± {r['perm_sd']:.4f} "
                  f"| {r['rf_impurity']:.4f} "
                  f"| {int(r['rank_impurity'])} |")
    (HERE / "data" / "unified_v2" /
     "permutation_importance.md").write_text("\n".join(md) + "\n",
                                              encoding="utf-8")
    log("step PERM/0 · DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
