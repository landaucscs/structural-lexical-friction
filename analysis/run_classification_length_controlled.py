"""Supplementary classification that excludes length-coupled features
(WC, MLS) to address the length-confound concern raised by the bulk legal
expansion (mean WC ~385 vs baseline ~187).

Output: data/unified/classification_length_controlled.md
        data/unified/classification_length_controlled.csv
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
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve, f1_score, accuracy_score
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


# Length-controlled tiers: WC and MLS dropped from every tier
TIERS = {
    "T1_surface_LC":  ["FRE", "ARI", "TTR"],
    "T2_lexical_LC":  ["FRE", "ARI", "TTR", "MTLD", "NomR"],
    "T3_full_LC":     ["FRE", "ARI", "TTR", "MTLD", "NomR",
                       "MCD", "MaxCD", "DC_C", "CT_T", "MLC"],
}

MODELS = {
    "LR":  lambda: Pipeline([("scaler", StandardScaler()),
                             ("clf", LogisticRegression(max_iter=2000, C=1.0,
                                  class_weight="balanced", random_state=2026))]),
    "RF":  lambda: RandomForestClassifier(n_estimators=300, min_samples_leaf=2,
                                          class_weight="balanced",
                                          random_state=2026),
    "GBM": lambda: GradientBoostingClassifier(n_estimators=200, max_depth=3,
                                              learning_rate=0.08,
                                              random_state=2026),
}


def bootstrap_auc_ci(y_true, y_pred, n_iter=500):
    rng = np.random.default_rng(2026)
    n = len(y_true)
    aucs = []
    for _ in range(n_iter):
        idx = rng.integers(0, n, n)
        if len(np.unique(y_true[idx])) < 2:
            continue
        aucs.append(roc_auc_score(y_true[idx], y_pred[idx]))
    aucs = np.array(aucs)
    return float(np.mean(aucs)), float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5))


def delong_paired(y_true, score_a, score_b):
    from scipy import stats
    pos = score_a[y_true == 1]; neg = score_a[y_true == 0]
    n1, n0 = len(pos), len(neg)
    auc_a = roc_auc_score(y_true, score_a)
    auc_b = roc_auc_score(y_true, score_b)
    # Independent (conservative) approximation
    V10a = np.array([(np.sum(neg < p) + 0.5*np.sum(neg == p))/n0 for p in pos])
    V01a = np.array([(np.sum(pos > n) + 0.5*np.sum(pos == n))/n1 for n in neg])
    pb = score_b[y_true == 1]; nb = score_b[y_true == 0]
    V10b = np.array([(np.sum(nb < p) + 0.5*np.sum(nb == p))/n0 for p in pb])
    V01b = np.array([(np.sum(pb > n) + 0.5*np.sum(pb == n))/n1 for n in nb])
    var_a = np.var(V10a, ddof=1)/n1 + np.var(V01a, ddof=1)/n0
    var_b = np.var(V10b, ddof=1)/n1 + np.var(V01b, ddof=1)/n0
    se = np.sqrt(var_a + var_b)
    diff = auc_a - auc_b
    z = diff/se if se > 0 else 0.0
    p = 2*(1 - stats.norm.cdf(abs(z)))
    return diff, z, p


def main():
    df = pd.read_csv(HERE / "data" / "unified" / "metrics.csv")
    df = df.dropna(subset=["bucket"])
    df["y"] = (df["bucket"] == "high_density").astype(int)
    y = df["y"].values
    log(f"step 8b/13 · length-controlled classification on n={len(df)}")

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=2026)
    rows = []
    cache = {}
    for model_name, factory in MODELS.items():
        for tier_name, feats in TIERS.items():
            X = df[feats].fillna(0.0).values
            log(f"step 8b/13 · CV {model_name} {tier_name}")
            proba = cross_val_predict(factory(), X, y, cv=skf,
                                       method="predict_proba", n_jobs=-1)
            ps = proba[:, 1]
            cache[(model_name, tier_name)] = ps
            auc = roc_auc_score(y, ps)
            pl = (ps >= 0.5).astype(int)
            f1 = f1_score(y, pl); acc = accuracy_score(y, pl)
            mn, lo, hi = bootstrap_auc_ci(y, ps)
            rows.append({"model": model_name, "tier": tier_name,
                         "n_feat": len(feats),
                         "AUC": round(auc, 4),
                         "AUC_lo": round(lo, 4), "AUC_hi": round(hi, 4),
                         "F1": round(f1, 4), "Acc": round(acc, 4)})
            log(f"step 8b/13 · {model_name}/{tier_name} AUC={auc:.4f} "
                f"[{lo:.4f},{hi:.4f}]")
    delongs = []
    for m in MODELS:
        a = cache.get((m, "T1_surface_LC"))
        b = cache.get((m, "T3_full_LC"))
        if a is None or b is None: continue
        d, z, p = delong_paired(y, b, a)
        delongs.append({"model": m, "diff": round(d,4),
                        "z": round(z,3), "p": round(p,6)})
        log(f"step 8b/13 · DeLong LC {m} T3-T1 diff={d:.4f} z={z:.3f} p={p:.4f}")

    res = pd.DataFrame(rows)
    res.to_csv(HERE / "data" / "unified" / "classification_length_controlled.csv",
               index=False)

    md = ["# Length-Controlled Classification (supplementary)",
          "",
          "Word count (WC) and mean sentence length (MLS) excluded from every "
          "tier to address the length confound between legal opinions "
          "(mean WC ~ 385) and baseline texts (mean WC ~ 187).",
          "",
          f"N = {len(df)}.",
          "",
          "| Model | Tier | # feat | AUC | 95% CI | F1 | Acc |",
          "|-------|------|--------|-----|--------|-----|-----|"]
    for r in rows:
        md.append(f"| {r['model']} | {r['tier']} | {r['n_feat']} | "
                  f"{r['AUC']:.4f} | [{r['AUC_lo']:.4f}, {r['AUC_hi']:.4f}] "
                  f"| {r['F1']:.4f} | {r['Acc']:.4f} |")
    md.append("")
    md.append("## DeLong AUC comparison (T3 LC vs T1 LC)")
    md.append("")
    md.append("| Model | AUC diff | z | p |")
    md.append("|-------|----------|---|---|")
    for d in delongs:
        md.append(f"| {d['model']} | {d['diff']:+.4f} | {d['z']:.3f} | {d['p']:.6f} |")
    (HERE / "data" / "unified" / "classification_length_controlled.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8")
    log("step 8b/13 · wrote length_controlled outputs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
