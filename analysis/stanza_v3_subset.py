"""Stanza-based MCD on a stratified subset of v3 to extend the parser
robustness check to the new v3 registers (LogiQA, cleaned legal opinions).

Stanza shares no code with spaCy and uses a different parser architecture
(BiLSTM with biaffine attention), so high MCD correlation is non-trivial
evidence of cross-framework robustness.
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


STANZA_CLAUSAL = {"ccomp", "xcomp", "advcl", "acl:relcl", "acl", "csubj"}
TARGET_N = 500


def mcd_stanza(text: str, nlp) -> float:
    doc = nlp(" ".join(text.split()))
    sent_depths = []
    for sent in doc.sentences:
        children = {}
        root_word = None
        for w in sent.words:
            children.setdefault(w.head, []).append(w)
            if w.head == 0:
                root_word = w
        if root_word is None:
            continue

        def dfs(word, depth):
            best = depth
            for ch in children.get(word.id, []):
                inc = 1 if ch.deprel in STANZA_CLAUSAL else 0
                d = dfs(ch, depth + inc)
                if d > best:
                    best = d
            return best
        sent_depths.append(dfs(root_word, 0))
    return sum(sent_depths) / len(sent_depths) if sent_depths else 0.0


def main() -> int:
    log("step REV2/C2 · Stanza v3 subset begin")
    metrics_path = HERE / "data" / "unified_v2" / "metrics_v3_sm.csv"
    if not metrics_path.exists():
        log("step REV2/C2 · sm v3 metrics missing")
        return 1
    sm_df = pd.read_csv(metrics_path)
    sm_index = {r["corpus_id"]: r for _, r in sm_df.iterrows()}
    corpus_path = HERE / "data" / "unified_v3" / "corpus.jsonl"
    recs = [json.loads(l) for l in corpus_path.open("r", encoding="utf-8") if l.strip()]

    # stratified sample with overlap with sm metrics
    by_reg = {}
    for r in recs:
        if r["corpus_id"] in sm_index:
            by_reg.setdefault(r["register"], []).append(r)
    rng = random.Random(2026)
    sample = []
    per_reg = max(40, TARGET_N // max(1, len(by_reg)))
    for reg, lst in by_reg.items():
        rng.shuffle(lst)
        sample.extend(lst[:per_reg])
    log(f"step REV2/C2 · sample n={len(sample)} from {len(by_reg)} registers")

    log("step REV2/C2 · loading Stanza en pipeline")
    import stanza
    nlp = stanza.Pipeline("en", processors="tokenize,pos,lemma,depparse",
                           verbose=False, use_gpu=False)
    log("step REV2/C2 · Stanza loaded")

    rows = []
    t0 = time.time()
    for i, rec in enumerate(sample):
        try:
            m_st = mcd_stanza(rec["text"], nlp)
        except Exception as exc:
            log(f"step REV2/C2 · ERROR {rec.get('corpus_id')}: {exc}")
            continue
        sm_row = sm_index.get(rec["corpus_id"], None)
        if sm_row is None:
            continue
        rows.append({
            "corpus_id": rec["corpus_id"],
            "register": rec["register"],
            "MCD_sm": float(sm_row["MCD"]),
            "MCD_stanza": round(m_st, 4),
        })
        if (i + 1) % 25 == 0:
            el = time.time() - t0
            log(f"step REV2/C2 · processed {i+1}/{len(sample)} "
                f"({(i+1)/el:.2f}/s)")

    df = pd.DataFrame(rows)
    df.to_csv(HERE / "data" / "unified_v2" / "stanza_v3_subset.csv",
              index=False)

    from scipy import stats
    r, p = stats.pearsonr(df["MCD_sm"], df["MCD_stanza"])
    log(f"step REV2/C2 · MCD sm vs Stanza on v3 subset: r={r:.4f} p={p:.2e}")
    md = ["# Stanza Parser Robustness on v3 Subset",
          "",
          f"Stratified subset of {len(df)} passages from the v3 corpus, "
          "parsed with Stanford *Stanza* and compared against the primary "
          "`en_core_web_sm` results.",
          "",
          "| Pair | Pearson $r$ | $p$ |",
          "|------|-----------|-----|",
          f"| MCD (sm) vs MCD (Stanza) | {r:.4f} | {p:.2e} |",
          "",
          "## Per-register means"]
    md.append("")
    md.append("| Register | n | mean MCD (sm) | mean MCD (Stanza) | diff |")
    md.append("|----------|---|---------------|-------------------|------|")
    for reg, sub in df.groupby("register"):
        d = sub["MCD_sm"].mean() - sub["MCD_stanza"].mean()
        md.append(f"| {reg} | {len(sub)} | {sub['MCD_sm'].mean():.3f} "
                  f"| {sub['MCD_stanza'].mean():.3f} | {d:+.3f} |")
    (HERE / "data" / "unified_v2" / "stanza_v3_subset.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8")
    log(f"step REV2/C2 · DONE · n={len(df)} r={r:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
