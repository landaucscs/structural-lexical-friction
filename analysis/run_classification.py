"""Classification: can linguistic indices discriminate high-density
informational prose from baseline informational prose?

Three ablation tiers:
    surface       FRE, ARI, WC, TTR, MLS                         (5 features)
    + lexical     surface + MTLD, NomR                            (7 features)
    + syntactic   above + MCD, MaxCD, DC_C, CT_T, MLC             (12 features)

Models:
    LogisticRegression, RandomForest, GradientBoosting

Outputs:
    data/unified/classification_results.csv
    data/unified/classification_summary.md
    figures/feature_importance.png
    figures/roc_curves.png
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


FEATURE_TIERS = {
    "T1_surface":    ["FRE", "ARI", "WC", "TTR", "MLS"],
    "T2_lexical":    ["FRE", "ARI", "WC", "TTR", "MLS", "MTLD", "NomR"],
    "T3_full":       ["FRE", "ARI", "WC", "TTR", "MLS", "MTLD", "NomR",
                      "MCD", "MaxCD", "DC_C", "CT_T", "MLC"],
}

MODELS = {
    "LR":  lambda: Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=2000, C=1.0,
                                    class_weight="balanced",
                                    random_state=2026))
    ]),
    "RF":  lambda: RandomForestClassifier(n_estimators=300,
                                          max_depth=None,
                                          min_samples_leaf=2,
                                          class_weight="balanced",
                                          random_state=2026),
    "GBM": lambda: GradientBoostingClassifier(n_estimators=200,
                                              max_depth=3,
                                              learning_rate=0.08,
                                              random_state=2026),
}


def bootstrap_auc_ci(y_true: np.ndarray, y_pred: np.ndarray,
                     n_iter: int = 1000) -> tuple[float, float, float]:
    rng = np.random.default_rng(2026)
    n = len(y_true)
    aucs = []
    for _ in range(n_iter):
        idx = rng.integers(0, n, n)
        if len(np.unique(y_true[idx])) < 2:
            continue
        aucs.append(roc_auc_score(y_true[idx], y_pred[idx]))
    aucs = np.array(aucs)
    return float(np.mean(aucs)), float(np.percentile(aucs, 2.5)), float(
        np.percentile(aucs, 97.5))


def delong_var(y_true: np.ndarray, y_score: np.ndarray) -> tuple[float, float]:
    """DeLong's method for AUC variance (single-AUC)."""
    pos = y_score[y_true == 1]
    neg = y_score[y_true == 0]
    n1, n0 = len(pos), len(neg)
    auc = roc_auc_score(y_true, y_score)
    # placement values
    V10 = np.array([(np.sum(neg < p) + 0.5 * np.sum(neg == p)) / n0
                    for p in pos])
    V01 = np.array([(np.sum(pos > n) + 0.5 * np.sum(pos == n)) / n1
                    for n in neg])
    s10 = np.var(V10, ddof=1) / n1
    s01 = np.var(V01, ddof=1) / n0
    return auc, s10 + s01


def delong_test(y_true: np.ndarray, score_a: np.ndarray,
                score_b: np.ndarray) -> tuple[float, float, float]:
    """Compare two AUCs (paired same-sample DeLong).

    Returns (auc_a - auc_b, z, two-sided p-value).
    """
    from scipy import stats
    auc_a, var_a = delong_var(y_true, score_a)
    auc_b, var_b = delong_var(y_true, score_b)
    diff = auc_a - auc_b
    # cov term approximated by Hanley-McNeil shortcut (assume independent):
    # this is conservative.  For better paired DeLong, would need full covariance.
    se = np.sqrt(var_a + var_b)
    z = diff / se if se > 0 else 0.0
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    return diff, z, p


def main() -> int:
    metrics_csv = HERE / "data" / "unified" / "metrics.csv"
    if not metrics_csv.exists():
        log("step 8/13 · ERROR · metrics.csv missing")
        return 1
    df = pd.read_csv(metrics_csv)
    log(f"step 8/13 · loaded metrics · n={len(df)}")
    log(f"step 8/13 · bucket counts: "
        f"{df['bucket'].value_counts().to_dict()}")

    df = df.dropna(subset=["bucket"])
    df["y"] = (df["bucket"] == "high_density").astype(int)
    n_pos, n_neg = int(df["y"].sum()), int((1 - df["y"]).sum())
    log(f"step 8/13 · n_pos(high_density)={n_pos}, n_neg(baseline)={n_neg}")

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=2026)

    results = []
    cv_scores_cache: dict[tuple[str, str], np.ndarray] = {}
    y = df["y"].values

    for model_name, model_factory in MODELS.items():
        for tier_name, feats in FEATURE_TIERS.items():
            X = df[feats].fillna(0.0).values
            log(f"step 8/13 · CV {model_name} {tier_name} (k=5)")
            try:
                proba = cross_val_predict(model_factory(), X, y, cv=skf,
                                          method="predict_proba",
                                          n_jobs=-1)
                pred_score = proba[:, 1]
            except Exception as exc:
                log(f"step 8/13 · ERROR {model_name}/{tier_name}: {exc}")
                continue
            pred_label = (pred_score >= 0.5).astype(int)

            auc = roc_auc_score(y, pred_score)
            f1 = f1_score(y, pred_label)
            acc = accuracy_score(y, pred_label)
            mean_auc, lo, hi = bootstrap_auc_ci(y, pred_score, n_iter=500)

            cv_scores_cache[(model_name, tier_name)] = pred_score

            results.append({
                "model": model_name,
                "tier": tier_name,
                "n_features": len(feats),
                "AUC": round(auc, 4),
                "AUC_lo": round(lo, 4),
                "AUC_hi": round(hi, 4),
                "F1": round(f1, 4),
                "Acc": round(acc, 4),
            })
            log(f"step 8/13 · {model_name}/{tier_name} AUC={auc:.4f} "
                f"[{lo:.4f}, {hi:.4f}], F1={f1:.4f}, Acc={acc:.4f}")

    # DeLong T1 vs T3 within each model
    delong_results = []
    for model_name in MODELS:
        s_t1 = cv_scores_cache.get((model_name, "T1_surface"))
        s_t3 = cv_scores_cache.get((model_name, "T3_full"))
        if s_t1 is None or s_t3 is None:
            continue
        d, z, p = delong_test(y, s_t3, s_t1)
        delong_results.append({
            "model": model_name,
            "comparison": "T3_full vs T1_surface",
            "AUC_diff": round(d, 4), "z": round(z, 3),
            "p_two_sided": round(p, 6),
        })
        log(f"step 8/13 · DeLong {model_name} T3-T1 diff={d:.4f} "
            f"z={z:.3f} p={p:.4f}")

    res_df = pd.DataFrame(results)
    res_df.to_csv(HERE / "data" / "unified" / "classification_results.csv",
                  index=False)
    if delong_results:
        pd.DataFrame(delong_results).to_csv(
            HERE / "data" / "unified" / "delong_results.csv", index=False)

    # ROC curves figure
    fig, ax = plt.subplots(figsize=(7, 5.5), dpi=160)
    palette = {"T1_surface": "#888888", "T2_lexical": "#1f77b4",
               "T3_full": "#c0392b"}
    for tier_name, color in palette.items():
        s = cv_scores_cache.get(("GBM", tier_name))
        if s is None:
            continue
        fpr, tpr, _ = roc_curve(y, s)
        auc = roc_auc_score(y, s)
        ax.plot(fpr, tpr, color=color,
                label=f"GBM {tier_name} (AUC={auc:.3f})",
                linewidth=2.0)
    ax.plot([0, 1], [0, 1], color="#cccccc", linestyle="--", linewidth=1)
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_title("ROC curves: discriminating high-density vs baseline\n"
                 "(GBM, 5-fold cross-validation)")
    ax.legend(loc="lower right")
    ax.grid(True, linestyle=":", alpha=0.4)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1.02)
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "roc_curves.png",
                dpi=180, bbox_inches="tight")
    plt.close(fig)
    log("step 8/13 · wrote figures/roc_curves.png")

    # Feature importance figure (RandomForest T3)
    fimp_model = RandomForestClassifier(
        n_estimators=400, max_depth=None, min_samples_leaf=2,
        class_weight="balanced", random_state=2026, n_jobs=-1
    )
    X_full = df[FEATURE_TIERS["T3_full"]].fillna(0.0).values
    fimp_model.fit(X_full, y)
    importances = pd.Series(fimp_model.feature_importances_,
                            index=FEATURE_TIERS["T3_full"])
    importances = importances.sort_values()
    fig, ax = plt.subplots(figsize=(7, 5), dpi=160)
    colors = ["#c0392b" if f in {"MCD", "MaxCD", "DC_C", "CT_T", "MLC"}
              else "#1f77b4" if f in {"MTLD", "NomR"}
              else "#888888"
              for f in importances.index]
    ax.barh(importances.index, importances.values, color=colors)
    ax.set_xlabel("Random Forest impurity-based importance")
    ax.set_title("Feature importance (Random Forest, T3-full feature set)\n"
                 "red=syntactic, blue=lexical, gray=surface")
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "feature_importance.png",
                dpi=180, bbox_inches="tight")
    plt.close(fig)
    log("step 8/13 · wrote figures/feature_importance.png")

    # Markdown summary
    md = ["# Classification Results",
          "",
          f"N = {len(df)} passages  ({n_pos} high-density · {n_neg} baseline)",
          "",
          "## 5-fold cross-validation AUC by model and feature tier",
          "",
          "| Model | Tier | # feat | AUC | 95% CI | F1 | Acc |",
          "|-------|------|--------|-----|--------|-----|-----|"]
    for r in results:
        md.append(f"| {r['model']} | {r['tier']} | {r['n_features']} "
                  f"| {r['AUC']:.4f} | "
                  f"[{r['AUC_lo']:.4f}, {r['AUC_hi']:.4f}] "
                  f"| {r['F1']:.4f} | {r['Acc']:.4f} |")
    if delong_results:
        md.extend(["", "## DeLong AUC comparison (T3 vs T1)",
                   "",
                   "| Model | AUC diff | z | p (two-sided) |",
                   "|-------|----------|----|---------------|"])
        for r in delong_results:
            md.append(f"| {r['model']} | {r['AUC_diff']:+.4f} | "
                      f"{r['z']:.3f} | {r['p_two_sided']:.6f} |")
    (HERE / "data" / "unified" / "classification_summary.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8")
    log("step 8/13 · wrote classification_summary.md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
