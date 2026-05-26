"""Multi-class register classification: how well do features discriminate
between the 9 individual registers (not just the binary bucket)?

Uses RandomForest and one-vs-rest LR; reports macro-AUC and per-class AUC.
"""
from __future__ import annotations

import datetime as _dt
import io
import sys
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (confusion_matrix, classification_report,
                              roc_auc_score)
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


FEATURES_T1 = ["FRE", "ARI", "WC", "TTR", "MLS"]
FEATURES_T3 = ["FRE", "ARI", "WC", "TTR", "MLS", "MTLD", "NomR",
               "MCD", "MaxCD", "DC_C", "CT_T", "MLC",
               "MAL", "MaxAL", "LeftBR", "MeanArcCross", "MaxArcCross"]


def main():
    df = pd.read_csv(HERE / "data" / "unified_v2" / "metrics_v3_sm.csv")
    df = df.dropna(subset=["register"])
    log(f"step REV/6 · multi-class on n={len(df)} · "
        f"{df['register'].nunique()} registers")

    y = df["register"].values
    reg_names = sorted(df["register"].unique())
    log(f"step REV/6 · registers: {reg_names}")

    rng = np.random.default_rng(2026)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=2026)

    results = []
    for tier_name, feats in [("T1_surface", FEATURES_T1),
                              ("T3_full",     FEATURES_T3)]:
        X = df[feats].fillna(0.0).values
        for model_name, factory in [
            ("LR_OvR", lambda: Pipeline([("scaler", StandardScaler()),
                                           ("clf", LogisticRegression(
                                               max_iter=2000,
                                               class_weight="balanced",
                                               random_state=2026,
                                               n_jobs=1))])),
            ("RF",    lambda: RandomForestClassifier(
                n_estimators=400, min_samples_leaf=2,
                class_weight="balanced", random_state=2026, n_jobs=1)),
        ]:
            log(f"step REV/6 · CV {model_name} {tier_name}")
            proba = cross_val_predict(factory(), X, y, cv=skf,
                                       method="predict_proba", n_jobs=1)
            preds = np.array([reg_names[i] for i in np.argmax(proba, axis=1)])
            # macro-average AUC (OvR)
            from sklearn.preprocessing import label_binarize
            y_bin = label_binarize(y, classes=reg_names)
            try:
                macro_auc = roc_auc_score(y_bin, proba,
                                          average="macro", multi_class="ovr")
            except ValueError:
                macro_auc = float("nan")
            acc = (preds == y).mean()
            log(f"step REV/6 · {model_name}/{tier_name} macro-AUC={macro_auc:.4f} "
                f"acc={acc:.4f}")
            # per-class AUC
            per_class = {}
            for i, reg in enumerate(reg_names):
                try:
                    per_class[reg] = roc_auc_score(y_bin[:, i], proba[:, i])
                except ValueError:
                    per_class[reg] = float("nan")
            results.append({
                "model": model_name, "tier": tier_name,
                "macro_AUC": round(macro_auc, 4), "accuracy": round(acc, 4),
                **{f"AUC_{r}": round(v, 4) for r, v in per_class.items()}
            })

    pd.DataFrame(results).to_csv(
        HERE / "data" / "unified_v2" / "classification_v3_multiclass.csv",
        index=False)

    md = ["# v2 Multi-Class Register Classification",
          "",
          f"N = {len(df)} · 9 registers (simple_wikipedia removed)",
          "",
          "## Macro and per-class AUC (5-fold CV)",
          "",
          "| Model | Tier | macro-AUC | Acc | " + " | ".join(reg_names) + " |",
          "|-------|------|-----------|-----|" + "|".join(["---"] * len(reg_names)) + "|"]
    for r in results:
        row = (f"| {r['model']} | {r['tier']} | {r['macro_AUC']:.4f} "
               f"| {r['accuracy']:.4f} | "
               + " | ".join(f"{r[f'AUC_{n}']:.4f}" for n in reg_names) + " |")
        md.append(row)
    (HERE / "data" / "unified_v2" / "classification_v3_multiclass.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8")
    log("step REV/6 · wrote multi-class summary")
    return 0


if __name__ == "__main__":
    sys.exit(main())
