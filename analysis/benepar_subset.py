"""Constituent-parser robustness check via Berkeley Neural Parser (benepar).

Computes phrase-structure-based indices on a stratified subset (n ≈ 500) of
the v3 corpus:
  - SBAR_count      — number of subordinate clause constituents per sentence
                       (subordinating-conjunction-headed clauses, the genuine
                       SBAR node from a constituent parse).
  - SubTreeDepth    — height of the constituent parse tree (root to deepest
                       terminal).
  - NP_in_VP        — count of noun-phrase constituents nested within a
                       verb-phrase constituent (deep argument structure
                       indicator).
Pearson correlations between these constituent-parse measures and the
dependency-parse-based MCD / MaxArcCross / MAL on the same passages are
reported as a complementary robustness check; we predict that MCD will
correlate strongly with SBAR_count and SubTreeDepth.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import random
import sys
import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent.parent
PROGRESS_LOG = HERE / "progress.log"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              line_buffering=True)


def log(label: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {label}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


TARGET_N = 500


def count_constituents(tree, target_labels):
    """Count occurrences of `target_labels` labels in the constituent tree."""
    if hasattr(tree, "label") and tree.label() in target_labels:
        c = 1
    else:
        c = 0
    if hasattr(tree, "__iter__"):
        for child in tree:
            c += count_constituents(child, target_labels)
    return c


def tree_depth(tree):
    if not hasattr(tree, "__iter__"):
        return 0
    if isinstance(tree, str):
        return 0
    sub = [tree_depth(child) for child in tree if hasattr(child, "label")
           or isinstance(child, str)]
    if not sub:
        return 1
    return 1 + max(sub) if sub else 1


def count_np_in_vp(tree):
    """Recursively count NP constituents nested under a VP."""
    if not hasattr(tree, "label"):
        return 0
    n = 0
    label = tree.label()
    if label == "VP":
        # count NPs in the subtree rooted at this VP
        def count_np(t):
            if not hasattr(t, "label"):
                return 0
            c = 1 if t.label() == "NP" else 0
            for ch in t:
                c += count_np(ch)
            return c
        n += count_np(tree) - (1 if label == "NP" else 0)
    for child in tree:
        n += count_np_in_vp(child)
    return n


def parse_sentence_metrics(sent_text, nlp):
    """Use spaCy + benepar.  Returns aggregated constituent metrics for the
    sentence."""
    import nltk
    doc = nlp(sent_text)
    sent = list(doc.sents)
    if not sent:
        return None
    s = sent[0]
    try:
        tree_str = s._.parse_string
    except AttributeError:
        return None
    tree = nltk.Tree.fromstring(tree_str)
    sbar = count_constituents(tree, {"SBAR"})
    sinv = count_constituents(tree, {"SBARQ", "SINV"})
    depth = tree_depth(tree)
    np_in_vp = count_np_in_vp(tree)
    return {"SBAR": sbar, "SBARQ_SINV": sinv,
            "ConstHeight": depth, "NP_in_VP": np_in_vp}


def main() -> int:
    corpus_path = HERE / "data" / "unified_v3" / "corpus.jsonl"
    metrics_path = HERE / "data" / "unified_v2" / "metrics_v3_sm.csv"
    if not corpus_path.exists() or not metrics_path.exists():
        log("step REV2/C1 · ERROR · v3 corpus or sm metrics missing")
        return 1
    recs = [json.loads(l) for l in corpus_path.open("r", encoding="utf-8") if l.strip()]
    metrics_df = pd.read_csv(metrics_path)
    metrics_index = {row["corpus_id"]: row for _, row in metrics_df.iterrows()}

    # stratified sample by register, ~55 per register (9 registers ≈ 495)
    by_reg = {}
    for r in recs:
        by_reg.setdefault(r["register"], []).append(r)
    per_reg = max(50, TARGET_N // len(by_reg))
    rng = random.Random(2026)
    sample = []
    for reg, lst in by_reg.items():
        rng.shuffle(lst)
        sample.extend(lst[:per_reg])
    log(f"step REV2/C1 · benepar sample n={len(sample)} from "
        f"{len(by_reg)} registers")

    # load benepar via spaCy
    import spacy
    import benepar
    log("step REV2/C1 · loading benepar_en3 (~512MB)")
    nlp = spacy.load("en_core_web_sm")
    if "benepar" not in nlp.pipe_names:
        nlp.add_pipe("benepar", config={"model": "benepar_en3"})
    nlp.max_length = 500_000
    log("step REV2/C1 · benepar ready")

    rows = []
    t0 = time.time()
    for i, rec in enumerate(sample):
        text = " ".join(rec["text"].split())
        try:
            doc = nlp(text)
            sbar_sum = 0
            sinv_sum = 0
            depths = []
            np_in_vp_sum = 0
            for sent in doc.sents:
                try:
                    ts = sent._.parse_string
                except AttributeError:
                    continue
                import nltk
                tree = nltk.Tree.fromstring(ts)
                sbar_sum += count_constituents(tree, {"SBAR"})
                sinv_sum += count_constituents(tree, {"SBARQ", "SINV"})
                depths.append(tree_depth(tree))
                np_in_vp_sum += count_np_in_vp(tree)
            metric_row = metrics_index.get(rec["corpus_id"], None)
            if metric_row is None:
                continue
            rows.append({
                "corpus_id": rec["corpus_id"],
                "register": rec["register"],
                "SBAR_per_sent": sbar_sum / max(1, len(depths)),
                "SBARQ_per_sent": sinv_sum / max(1, len(depths)),
                "ConstHeight_avg": sum(depths) / max(1, len(depths)),
                "ConstHeight_max": max(depths) if depths else 0,
                "NP_in_VP_per_sent": np_in_vp_sum / max(1, len(depths)),
                # carry over dependency-parse metrics for correlation
                "MCD": metric_row["MCD"],
                "MaxCD": metric_row["MaxCD"],
                "MAL": metric_row["MAL"],
                "MeanArcCross": metric_row["MeanArcCross"],
                "FRE": metric_row["FRE"],
                "WC": metric_row["WC"],
            })
        except Exception as exc:
            log(f"step REV2/C1 · ERROR {rec.get('corpus_id')}: {exc}")
            continue
        if (i + 1) % 50 == 0:
            el = time.time() - t0
            rate = (i + 1) / el
            log(f"step REV2/C1 · parsed {i+1}/{len(sample)} "
                f"({rate:.2f}/s eta {(len(sample)-i-1)/rate:.0f}s)")

    out = pd.DataFrame(rows)
    out.to_csv(HERE / "data" / "unified_v2" / "benepar_subset.csv",
                index=False)

    # Correlations
    from scipy import stats
    corr_rows = []
    md_rows = []
    for a in ["SBAR_per_sent", "ConstHeight_avg", "ConstHeight_max",
              "NP_in_VP_per_sent"]:
        for b in ["MCD", "MaxCD", "MAL", "MeanArcCross"]:
            r, p = stats.pearsonr(out[a], out[b])
            corr_rows.append({"constituent": a, "dependency": b,
                               "pearson_r": round(r, 4), "p": float(p)})
            md_rows.append(f"| {a} | {b} | {r:.4f} | {p:.2e} |")
            log(f"step REV2/C1 · {a} vs {b}: r={r:.4f} p={p:.2e}")

    md = ["# Berkeley Neural Parser (benepar) Constituent-Parse Robustness "
          "Check",
          "",
          f"Stratified subset of {len(out)} passages from the v3 corpus; "
          "constituent-tree-based indices computed and cross-correlated with "
          "the dependency-parse-based primary indices.",
          "",
          "## Per-register means (constituent indices)"]
    summary = out.groupby("register")[
        ["SBAR_per_sent", "ConstHeight_avg", "NP_in_VP_per_sent"]
    ].mean().round(3)
    md.append("")
    md.append("| Register | SBAR/sent | ConstHeight | NP-in-VP/sent |")
    md.append("|----------|-----------|-------------|---------------|")
    for reg, row in summary.iterrows():
        md.append(f"| {reg} | {row['SBAR_per_sent']:.3f} "
                  f"| {row['ConstHeight_avg']:.3f} "
                  f"| {row['NP_in_VP_per_sent']:.3f} |")
    md.extend(["",
                "## Pearson correlations · constituent vs dependency",
                "",
                "| Constituent index | Dependency index | Pearson $r$ | $p$ |",
                "|-------------------|------------------|-----------|-----|"])
    md.extend(md_rows)
    (HERE / "data" / "unified_v2" / "benepar_subset.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8")
    pd.DataFrame(corr_rows).to_csv(
        HERE / "data" / "unified_v2" / "benepar_corr.csv", index=False)
    log("step REV2/C1 · benepar subset done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
