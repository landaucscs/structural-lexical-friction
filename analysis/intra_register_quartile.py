"""Intra-register difficulty quartile classification.

Per register (each of WikiText-103, Brown, Gutenberg, Reuters), rank the
passages by Flesch Reading Ease, take the lowest-quartile (= "hardest" in
the FRE direction, lowest FRE) and the highest-quartile passages, and train
a classifier to distinguish them.  The classification proxy (FRE) is excluded
from the feature set to keep the task non-circular.

If syntactic indices add value even within a single register where lexical
register is held constant, that is unambiguous evidence that they carry
information beyond FRE-driven readability.
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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, f1_score, accuracy_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

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


# Drop FRE from features to keep the task non-circular: we used FRE to define
# the quartiles, so we must not let the classifier use it.
T1_NOFRE = ["ARI", "WC", "TTR", "MLS"]
T3_NOFRE = ["ARI", "WC", "TTR", "MLS", "MTLD", "NomR",
            "MCD", "MaxCD", "DC_C", "CT_T", "MLC",
            "MAL", "MaxAL", "LeftBR", "MeanArcCross", "MaxArcCross"]

TARGET_REGISTERS = ["wikitext_modern_encyclopedic",
                    "brown_news_general",
                    "gutenberg_fiction",
                    "reuters_newswire"]


def run_block(df, feats, y, name):
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=2026)
    X = df[feats].fillna(0.0).values
    # LR
    lr = Pipeline([("s", StandardScaler()),
                    ("c", LogisticRegression(max_iter=2000, C=1.0,
                                              class_weight="balanced",
                                              random_state=2026, n_jobs=1))])
    proba_lr = cross_val_predict(lr, X, y, cv=skf,
                                  method="predict_proba", n_jobs=1)[:, 1]
    auc_lr = roc_auc_score(y, proba_lr)
    # GBM
    gbm = GradientBoostingClassifier(n_estimators=200, max_depth=3,
                                      learning_rate=0.08, random_state=2026)
    proba_gbm = cross_val_predict(gbm, X, y, cv=skf,
                                   method="predict_proba", n_jobs=1)[:, 1]
    auc_gbm = roc_auc_score(y, proba_gbm)
    return {"name": name, "auc_lr": round(auc_lr, 4),
            "auc_gbm": round(auc_gbm, 4)}


def main() -> int:
    metrics_path = HERE / "data" / "unified_v2" / "metrics_v3_sm.csv"
    if not metrics_path.exists():
        log("step REV2/B2 · v3 metrics not yet available")
        return 1
    log("step REV2/B2 · intra-register quartile classification begin")
    df = pd.read_csv(metrics_path)
    rows = []
    for reg in TARGET_REGISTERS:
        sub = df[df["register"] == reg].copy()
        if len(sub) < 80:
            log(f"step REV2/B2 · skip {reg} (n={len(sub)})")
            continue
        # quartile split by FRE
        q_low = sub["FRE"].quantile(0.25)
        q_high = sub["FRE"].quantile(0.75)
        bottom = sub[sub["FRE"] <= q_low].copy()  # lowest FRE = hardest
        top = sub[sub["FRE"] >= q_high].copy()    # highest FRE = easiest
        bottom["y"] = 1  # hardest
        top["y"] = 0     # easiest
        comb = pd.concat([bottom, top], ignore_index=True)
        log(f"step REV2/B2 · {reg} · n_hard={len(bottom)} n_easy={len(top)} "
            f"FRE thresholds: <={q_low:.1f} or >={q_high:.1f}")
        y = comb["y"].values
        for tier_name, feats in [("T1_noFRE", T1_NOFRE), ("T3_noFRE", T3_NOFRE)]:
            r = run_block(comb, feats, y, f"{reg}_{tier_name}")
            r["register"] = reg
            r["tier"] = tier_name
            r["n"] = len(comb)
            rows.append(r)
            log(f"step REV2/B2 · {reg} {tier_name} AUC_LR={r['auc_lr']:.4f} "
                f"AUC_GBM={r['auc_gbm']:.4f}")

    df_out = pd.DataFrame(rows)
    df_out.to_csv(HERE / "data" / "unified_v2" / "classification_v3_intra.csv",
                  index=False)
    md = ["# Intra-Register Difficulty Quartile Classification",
          "",
          "Within each register, the lowest-FRE quartile (hardest, $y=1$) is "
          "compared against the highest-FRE quartile (easiest, $y=0$) using "
          "5-fold cross-validation.  FRE is excluded from the feature set to "
          "keep the task non-circular (FRE defined the labels).",
          "",
          "| Register | Tier | n | AUC (*LR*) | AUC (*GBM*) |",
          "|----------|------|----|-----------|-------------|"]
    for r in rows:
        md.append(f"| {r['register']} | {r['tier']} | {r['n']} | "
                  f"{r['auc_lr']:.4f} | {r['auc_gbm']:.4f} |")
    (HERE / "data" / "unified_v2" / "classification_v3_intra.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8")
    log("step REV2/B2 · intra-register classification done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
