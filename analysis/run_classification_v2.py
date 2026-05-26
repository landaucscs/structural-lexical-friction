"""Classification on v2 corpus with extended feature set.

Three feature tiers (full and length-controlled variants):
  Surface (T1):   FRE, ARI, WC, TTR, MLS
  + Lex (T2):     T1 + MTLD, NomR
  + Syntactic (T3): T2 + MCD, MaxCD, DC_C, CT_T, MLC,
                          MAL, MaxAL, LeftBR, MeanArcCross, MaxArcCross

Length-controlled variants drop {WC, MLS} from every tier.

Models: LogisticRegression, RandomForest, GradientBoosting
CV: 5-fold stratified
CI: 500-resample bootstrap
Comparison: paired DeLong (T3 vs T1, both full and LC)

Usage:
  python run_classification_v2.py --metrics data/unified_v2/metrics_v2_sm.csv
"""
from __future__ import annotations

import argparse
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


FULL_FEATURES = {
    "T1_surface":   ["FRE", "ARI", "WC", "TTR", "MLS"],
    "T2_lexical":   ["FRE", "ARI", "WC", "TTR", "MLS", "MTLD", "NomR"],
    "T3_full":      ["FRE", "ARI", "WC", "TTR", "MLS", "MTLD", "NomR",
                     "MCD", "MaxCD", "DC_C", "CT_T", "MLC",
                     "MAL", "MaxAL", "LeftBR", "MeanArcCross", "MaxArcCross"],
}

LC_FEATURES = {
    "T1_surface_LC":  ["FRE", "ARI", "TTR"],
    "T2_lexical_LC":  ["FRE", "ARI", "TTR", "MTLD", "NomR"],
    "T3_full_LC":     ["FRE", "ARI", "TTR", "MTLD", "NomR",
                       "MCD", "MaxCD", "DC_C", "CT_T", "MLC",
                       "MAL", "MaxAL", "LeftBR", "MeanArcCross", "MaxArcCross"],
}

MODELS = {
    "LR":  lambda: Pipeline([("scaler", StandardScaler()),
                             ("clf", LogisticRegression(max_iter=2000, C=1.0,
                                  class_weight="balanced", random_state=2026))]),
    "RF":  lambda: RandomForestClassifier(n_estimators=300, min_samples_leaf=2,
                                          class_weight="balanced",
                                          random_state=2026, n_jobs=1),
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
    return float(np.mean(aucs)), float(np.percentile(aucs, 2.5)), \
           float(np.percentile(aucs, 97.5))


def delong_paired(y_true, score_a, score_b):
    from scipy import stats
    y_true = np.asarray(y_true)
    score_a = np.asarray(score_a); score_b = np.asarray(score_b)
    pos_idx = (y_true == 1)
    neg_idx = (y_true == 0)
    p_a = score_a[pos_idx]; n_a = score_a[neg_idx]
    p_b = score_b[pos_idx]; n_b = score_b[neg_idx]
    n1, n0 = len(p_a), len(n_a)
    auc_a = roc_auc_score(y_true, score_a)
    auc_b = roc_auc_score(y_true, score_b)
    V10a = np.array([(np.sum(n_a < x) + 0.5 * np.sum(n_a == x))/n0 for x in p_a])
    V01a = np.array([(np.sum(p_a > x) + 0.5 * np.sum(p_a == x))/n1 for x in n_a])
    V10b = np.array([(np.sum(n_b < x) + 0.5 * np.sum(n_b == x))/n0 for x in p_b])
    V01b = np.array([(np.sum(p_b > x) + 0.5 * np.sum(p_b == x))/n1 for x in n_b])
    var_a = np.var(V10a, ddof=1)/n1 + np.var(V01a, ddof=1)/n0
    var_b = np.var(V10b, ddof=1)/n1 + np.var(V01b, ddof=1)/n0
    cov = (np.cov(V10a, V10b, ddof=1)[0, 1] / n1 +
           np.cov(V01a, V01b, ddof=1)[0, 1] / n0)
    diff = auc_a - auc_b
    var = var_a + var_b - 2 * cov
    se = np.sqrt(var) if var > 0 else 1e-12
    z = diff / se
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    return diff, z, p


def run_block(df, tiers_dict, y, label):
    rows = []
    cache = {}
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=2026)
    for model_name, factory in MODELS.items():
        for tier_name, feats in tiers_dict.items():
            X = df[feats].fillna(0.0).values
            log(f"step PHASE3/CLF [{label}] · CV {model_name} {tier_name}")
            proba = cross_val_predict(factory(), X, y, cv=skf,
                                       method="predict_proba", n_jobs=1)
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
            log(f"step PHASE3/CLF · {model_name}/{tier_name} AUC={auc:.4f} "
                f"[{lo:.4f},{hi:.4f}] F1={f1:.4f} Acc={acc:.4f}")
    return rows, cache


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", default="data/unified_v2/metrics_v2_sm.csv")
    ap.add_argument("--out-stem", default=None)
    args = ap.parse_args()
    metrics_path = HERE / args.metrics
    stem = args.out_stem or f"classification_v2_{Path(args.metrics).stem.split('_v2_')[-1]}"

    df = pd.read_csv(metrics_path)
    df = df.dropna(subset=["bucket"])
    df["y"] = (df["bucket"] == "high_density").astype(int)
    y = df["y"].values
    log(f"step PHASE3/CLF · loaded {len(df)} rows · "
        f"high={int(y.sum())} base={int((1-y).sum())}")

    full_rows, full_cache = run_block(df, FULL_FEATURES, y, "FULL")
    lc_rows, lc_cache = run_block(df, LC_FEATURES, y, "LC")

    # DeLong T3 vs T1 within each model, both blocks
    delong_rows = []
    for m in MODELS:
        # Full
        a = full_cache.get((m, "T3_full"))
        b = full_cache.get((m, "T1_surface"))
        if a is not None and b is not None:
            d, z, p = delong_paired(y, a, b)
            delong_rows.append({"model": m, "block": "full",
                                "diff": round(d, 4), "z": round(z, 3),
                                "p": round(p, 6)})
            log(f"step PHASE3/CLF · DeLong FULL {m} T3-T1 diff={d:.4f} "
                f"z={z:.3f} p={p:.4f}")
        # LC
        a = lc_cache.get((m, "T3_full_LC"))
        b = lc_cache.get((m, "T1_surface_LC"))
        if a is not None and b is not None:
            d, z, p = delong_paired(y, a, b)
            delong_rows.append({"model": m, "block": "LC",
                                "diff": round(d, 4), "z": round(z, 3),
                                "p": round(p, 6)})
            log(f"step PHASE3/CLF · DeLong LC {m} T3-T1 diff={d:.4f} "
                f"z={z:.3f} p={p:.4f}")

    all_rows = full_rows + lc_rows
    res_df = pd.DataFrame(all_rows)
    res_df.to_csv(HERE / "data" / "unified_v2" / f"{stem}_results.csv",
                  index=False)
    pd.DataFrame(delong_rows).to_csv(
        HERE / "data" / "unified_v2" / f"{stem}_delong.csv", index=False)

    # ROC fig (GBM)
    fig, ax = plt.subplots(figsize=(7, 5.5), dpi=160)
    for tier_name, color in [("T1_surface", "#888888"),
                               ("T2_lexical", "#1f77b4"),
                               ("T3_full", "#c0392b")]:
        s = full_cache.get(("GBM", tier_name))
        if s is None:
            continue
        fpr, tpr, _ = roc_curve(y, s)
        auc = roc_auc_score(y, s)
        ax.plot(fpr, tpr, color=color, linewidth=2.0,
                label=f"GBM {tier_name} (AUC={auc:.3f})")
    ax.plot([0, 1], [0, 1], "--", color="#ccc", linewidth=1)
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_title(f"ROC curves (full features, GBM)\n"
                 f"n={len(df)}, parser={Path(args.metrics).stem}")
    ax.legend(loc="lower right")
    ax.grid(True, linestyle=":", alpha=0.4)
    fig.tight_layout()
    fig.savefig(HERE / "figures" / f"{stem}_roc.png",
                dpi=180, bbox_inches="tight")
    plt.close(fig)
    log(f"step PHASE3/CLF · wrote figures/{stem}_roc.png")

    # Feature importance (RF, full tier)
    rf = RandomForestClassifier(n_estimators=400, min_samples_leaf=2,
                                 class_weight="balanced", random_state=2026,
                                 n_jobs=1)
    X_full = df[FULL_FEATURES["T3_full"]].fillna(0.0).values
    rf.fit(X_full, y)
    # Map internal feature names to display labels matching manuscript prose
    display_map = {
        "DC_C": "DC/C", "CT_T": "CT/T",
        "MaxCD": "MaxCD", "MaxAL": "MaxAL",
        "MeanArcCross": "MeanArcCross", "MaxArcCross": "MaxArcCross",
        "LeftBR": "LeftBR",
    }
    imp_raw = pd.Series(rf.feature_importances_,
                         index=FULL_FEATURES["T3_full"]).sort_values()
    imp = imp_raw.rename(index=lambda x: display_map.get(x, x))
    fig, ax = plt.subplots(figsize=(7, 6), dpi=160)
    syn_set = {"MCD", "MaxCD", "DC/C", "CT/T", "MLC",
               "MAL", "MaxAL", "LeftBR", "MeanArcCross", "MaxArcCross"}
    colors = ["#c0392b" if f in syn_set
              else "#1f77b4" if f in {"MTLD", "NomR"}
              else "#888888" for f in imp.index]
    ax.barh(imp.index, imp.values, color=colors)
    ax.set_xlabel("Random Forest impurity-based importance")
    ax.set_title(f"Feature importance (T3 full)\n"
                 f"red=syntactic, blue=lexical, gray=surface")
    fig.tight_layout()
    fig.savefig(HERE / "figures" / f"{stem}_feature_importance.png",
                dpi=180, bbox_inches="tight")
    plt.close(fig)
    log(f"step PHASE3/CLF · wrote figures/{stem}_feature_importance.png")

    # Markdown summary
    md = [f"# v2 Classification Results ({Path(args.metrics).stem})",
          "",
          f"N = {len(df)}  (high={int(y.sum())}, baseline={int((1-y).sum())})",
          "",
          "## Full features",
          "",
          "| Model | Tier | # feat | AUC | 95% CI | F1 | Acc |",
          "|-------|------|--------|------|---------|------|-------|"]
    for r in full_rows:
        md.append(f"| {r['model']} | {r['tier']} | {r['n_feat']} "
                  f"| {r['AUC']:.4f} | [{r['AUC_lo']:.4f}, {r['AUC_hi']:.4f}] "
                  f"| {r['F1']:.4f} | {r['Acc']:.4f} |")
    md.extend(["", "## Length-controlled (WC and MLS removed)", "",
                "| Model | Tier | # feat | AUC | 95% CI | F1 | Acc |",
                "|-------|------|--------|------|---------|------|-------|"])
    for r in lc_rows:
        md.append(f"| {r['model']} | {r['tier']} | {r['n_feat']} "
                  f"| {r['AUC']:.4f} | [{r['AUC_lo']:.4f}, {r['AUC_hi']:.4f}] "
                  f"| {r['F1']:.4f} | {r['Acc']:.4f} |")
    md.extend(["", "## DeLong AUC comparison (T3 vs T1)", "",
                "| Model | Block | AUC diff | z | p |",
                "|-------|-------|----------|---|---|"])
    for r in delong_rows:
        md.append(f"| {r['model']} | {r['block']} | {r['diff']:+.4f} "
                  f"| {r['z']:.3f} | {r['p']:.6f} |")
    (HERE / "data" / "unified_v2" / f"{stem}_summary.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8")
    log(f"step PHASE3/CLF · wrote {stem}_summary.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
