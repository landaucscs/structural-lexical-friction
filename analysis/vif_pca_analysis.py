"""VIF (Variance Inflation Factor) + PCA supplementary analysis.

Step 1: compute VIF for all 17 features.  Identify multicollinearity
(VIF > 5) and report.

Step 2: run PCA on the 10 syntactic indices to project to two orthogonal
components (PC1 = "Clausal Embedding Complexity", PC2 = "Dependency Arc
Trajectory" by post-hoc inspection of loadings).  Re-run binary
classification using only surface (T1) + PC1 + PC2 and compare AUC against
the full-tier T3 to verify that the syntactic family's information is
substantially captured by two components.
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
from sklearn.decomposition import PCA
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
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


ALL_FEATS = ["FRE", "ARI", "WC", "TTR", "MLS", "MTLD", "NomR",
             "MCD", "MaxCD", "DC_C", "CT_T", "MLC",
             "MAL", "MaxAL", "LeftBR", "MeanArcCross", "MaxArcCross"]
SYNTACTIC = ["MCD", "MaxCD", "DC_C", "CT_T", "MLC",
             "MAL", "MaxAL", "LeftBR", "MeanArcCross", "MaxArcCross"]
T1_SURFACE = ["FRE", "ARI", "WC", "TTR", "MLS"]


def compute_vif(df, feats):
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    X = df[feats].fillna(0.0).values.astype(float)
    # add constant column for VIF
    X_aug = np.column_stack([np.ones(X.shape[0]), X])
    vifs = []
    for i in range(1, X_aug.shape[1]):
        try:
            v = variance_inflation_factor(X_aug, i)
        except Exception:
            v = float("nan")
        vifs.append((feats[i-1], v))
    return vifs


def main() -> int:
    metrics_path = HERE / "data" / "unified_v2" / "metrics_v3_sm.csv"
    if not metrics_path.exists():
        log("step REV2/B4 · ERROR · v3 metrics missing")
        return 1
    df = pd.read_csv(metrics_path)
    df = df.dropna(subset=["bucket"])
    df["y"] = (df["bucket"] == "high_density").astype(int)
    log(f"step REV2/B4 · loaded {len(df)}")

    # VIF
    log("step REV2/B4 · computing VIF on 17 features")
    try:
        import statsmodels  # noqa
    except ImportError:
        log("step REV2/B4 · installing statsmodels...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                                "--quiet", "statsmodels"])
    vifs = compute_vif(df, ALL_FEATS)
    flag = [(f, v) for f, v in vifs if v > 5.0]
    for f, v in vifs:
        log(f"step REV2/B4 · VIF[{f}] = {v:.2f}"
            + ("  ⚠FLAG" if v > 5.0 else ""))

    # PCA on syntactic
    log("step REV2/B4 · PCA on 10 syntactic indices")
    scaler = StandardScaler()
    X_syn = scaler.fit_transform(df[SYNTACTIC].fillna(0.0).values)
    pca = PCA(n_components=4, random_state=2026)
    pca.fit(X_syn)
    log(f"step REV2/B4 · explained variance ratio: "
        f"{[round(x, 4) for x in pca.explained_variance_ratio_]}")
    components_df = pd.DataFrame(pca.components_[:4],
                                  columns=SYNTACTIC,
                                  index=["PC1", "PC2", "PC3", "PC4"])
    log("step REV2/B4 · PC1 loadings (top 5):")
    pc1_loadings = components_df.loc["PC1"].abs().sort_values(ascending=False)
    for name, val in pc1_loadings.head(5).items():
        log(f"    {name}: |{components_df.loc['PC1', name]:.3f}|")
    log("step REV2/B4 · PC2 loadings (top 5):")
    pc2_loadings = components_df.loc["PC2"].abs().sort_values(ascending=False)
    for name, val in pc2_loadings.head(5).items():
        log(f"    {name}: |{components_df.loc['PC2', name]:.3f}|")

    # Add PC1, PC2 as features and re-classify
    pcs = pca.transform(X_syn)
    df["PC1_syn"] = pcs[:, 0]
    df["PC2_syn"] = pcs[:, 1]

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=2026)
    y = df["y"].values
    tiers = {
        "T1_surface": T1_SURFACE,
        "T1+PC1": T1_SURFACE + ["PC1_syn"],
        "T1+PC1+PC2": T1_SURFACE + ["PC1_syn", "PC2_syn"],
        "T3_full": ALL_FEATS,
    }
    auc_results = []
    for tier_name, feats in tiers.items():
        X = df[feats].fillna(0.0).values
        gbm = GradientBoostingClassifier(n_estimators=200, max_depth=3,
                                          learning_rate=0.08,
                                          random_state=2026)
        proba = cross_val_predict(gbm, X, y, cv=skf,
                                   method="predict_proba", n_jobs=1)[:, 1]
        auc = roc_auc_score(y, proba)
        auc_results.append({"tier": tier_name, "n_feat": len(feats),
                             "AUC": round(auc, 4)})
        log(f"step REV2/B4 · {tier_name} ({len(feats)} feats) GBM AUC={auc:.4f}")

    out_dir = HERE / "data" / "unified_v2"
    pd.DataFrame(vifs, columns=["feature", "VIF"]).to_csv(
        out_dir / "vif_table.csv", index=False)
    components_df.T.to_csv(out_dir / "pca_loadings.csv")
    pd.DataFrame(auc_results).to_csv(out_dir / "pca_classification.csv",
                                       index=False)

    md = ["# Multicollinearity (VIF) and PCA on Syntactic Indices",
          "",
          "## VIF (linear regression auxiliary; full feature set)",
          "",
          "| Feature | VIF | Flag |",
          "|---------|-----|------|"]
    for f, v in vifs:
        flagged = "⚠ collinear" if v > 5.0 else ""
        md.append(f"| {f} | {v:.2f} | {flagged} |")
    md.extend(["",
                "## PCA on 10 syntactic indices",
                "",
                f"Explained variance ratio: PC1 = {pca.explained_variance_ratio_[0]:.3f}, "
                f"PC2 = {pca.explained_variance_ratio_[1]:.3f}, "
                f"PC3 = {pca.explained_variance_ratio_[2]:.3f}, "
                f"PC4 = {pca.explained_variance_ratio_[3]:.3f}. "
                f"Cumulative top-2 = {sum(pca.explained_variance_ratio_[:2]):.3f}.",
                "",
                "## Classification with PCA-compressed syntactic features",
                "",
                "| Tier | # feat | GBM AUC |",
                "|------|--------|---------|"])
    for r in auc_results:
        md.append(f"| {r['tier']} | {r['n_feat']} | {r['AUC']:.4f} |")
    (out_dir / "vif_pca_summary.md").write_text("\n".join(md) + "\n",
                                                  encoding="utf-8")
    log("step REV2/B4 · VIF+PCA done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
