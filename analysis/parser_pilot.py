"""Three-way parser pilot: compute MCD (Mean Clausal Depth) with spaCy-sm,
spaCy-trf, and Stanza on a stratified 50-passage sample.  Report pairwise
Pearson correlations.  This is the gate that decides whether we can use sm
as primary parser with subset trf as supplementary, or whether we must
re-run on the full corpus with trf as primary.

Threshold (per design): r >= 0.85 across all three pairs → sm acceptable.
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


# Universal Dependencies clause labels (used by both spaCy and Stanza)
SPACY_CLAUSAL = {"ccomp", "xcomp", "advcl", "relcl", "acl", "csubj"}
STANZA_CLAUSAL = {"ccomp", "xcomp", "advcl", "acl:relcl", "acl", "csubj"}


def max_depth_spacy(token, deps, depth=0):
    if not list(token.children):
        return depth
    best = depth
    for child in token.children:
        inc = 1 if child.dep_ in deps else 0
        sub = max_depth_spacy(child, deps, depth + inc)
        if sub > best:
            best = sub
    return best


def mcd_spacy(text: str, nlp) -> float:
    doc = nlp(" ".join(text.split()))
    depths = [max_depth_spacy(s.root, SPACY_CLAUSAL, 0) for s in doc.sents]
    return sum(depths) / len(depths) if depths else 0.0


def mcd_stanza(text: str, nlp) -> float:
    """Walk Stanza's dependency tree.  Stanza word ids start at 1; head 0 = root."""
    doc = nlp(" ".join(text.split()))
    sent_depths = []
    for sent in doc.sentences:
        # build children map: parent_id (1-based) -> [child_word]
        children: dict[int, list] = {}
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
    log("step PHASE3/PILOT · loading 50-passage stratified sample")
    src = HERE / "data" / "unified_v2" / "corpus.jsonl"
    records = [json.loads(l) for l in src.open("r", encoding="utf-8") if l.strip()]
    by_reg = {}
    for r in records:
        by_reg.setdefault(r["register"], []).append(r)
    rng = random.Random(2026)
    sample = []
    # take ~5 from each major register
    target_per_reg = max(5, 50 // max(1, len(by_reg)))
    for reg, recs in by_reg.items():
        rng.shuffle(recs)
        sample.extend(recs[:target_per_reg])
    rng.shuffle(sample)
    sample = sample[:50]
    log(f"step PHASE3/PILOT · sample n={len(sample)} from "
        f"{len(by_reg)} registers")

    log("step PHASE3/PILOT · loading parsers")
    import spacy
    nlp_sm = spacy.load("en_core_web_sm")
    nlp_sm.max_length = 500_000

    log("step PHASE3/PILOT · loading trf (~466MB)")
    nlp_trf = spacy.load("en_core_web_trf")
    nlp_trf.max_length = 500_000

    log("step PHASE3/PILOT · loading stanza pipeline")
    import stanza
    stanza.download("en", verbose=False)
    nlp_st = stanza.Pipeline("en", processors="tokenize,pos,lemma,depparse",
                              verbose=False, use_gpu=False)

    rows = []
    for i, rec in enumerate(sample):
        text = rec["text"]
        try:
            t0 = time.time()
            m_sm = mcd_spacy(text, nlp_sm)
            t_sm = time.time() - t0
            t0 = time.time()
            m_trf = mcd_spacy(text, nlp_trf)
            t_trf = time.time() - t0
            t0 = time.time()
            m_st = mcd_stanza(text, nlp_st)
            t_st = time.time() - t0
        except Exception as exc:
            log(f"step PHASE3/PILOT · ERROR {rec.get('corpus_id')}: {exc}")
            continue
        rows.append({"corpus_id": rec["corpus_id"],
                     "register": rec["register"],
                     "MCD_sm": round(m_sm, 4),
                     "MCD_trf": round(m_trf, 4),
                     "MCD_stanza": round(m_st, 4),
                     "t_sm": round(t_sm, 3),
                     "t_trf": round(t_trf, 3),
                     "t_stanza": round(t_st, 3)})
        if (i + 1) % 10 == 0:
            log(f"step PHASE3/PILOT · processed {i+1}/{len(sample)}")

    df = pd.DataFrame(rows)
    df.to_csv(HERE / "data" / "unified_v2" / "parser_pilot.csv",
              index=False)
    log("step PHASE3/PILOT · wrote parser_pilot.csv")

    # Pearson correlations
    pairs = [("MCD_sm", "MCD_trf"),
             ("MCD_sm", "MCD_stanza"),
             ("MCD_trf", "MCD_stanza")]
    from scipy import stats
    out_md = ["# Parser Pilot — 3-way MCD Correlation (n=50)",
              "",
              f"Stratified sample across {len(by_reg)} registers.",
              "",
              "| Pair | Pearson r | p | mean diff |",
              "|------|-----------|---|-----------|"]
    summary = {}
    for a, b in pairs:
        r, p = stats.pearsonr(df[a], df[b])
        mdiff = (df[a] - df[b]).mean()
        out_md.append(f"| {a} vs {b} | {r:.4f} | {p:.4e} | {mdiff:+.4f} |")
        summary[f"{a}_vs_{b}"] = {"pearson_r": round(r, 4),
                                    "p_value": float(p),
                                    "mean_diff": round(mdiff, 4)}
        log(f"step PHASE3/PILOT · {a} vs {b}: r={r:.4f} p={p:.4e}")
    # parser speed
    out_md.extend(["", "## Speed (mean seconds per passage)",
                    "",
                    f"- sm: {df['t_sm'].mean():.3f}s",
                    f"- trf: {df['t_trf'].mean():.3f}s",
                    f"- stanza: {df['t_stanza'].mean():.3f}s"])
    (HERE / "data" / "unified_v2" / "parser_pilot_summary.md").write_text(
        "\n".join(out_md) + "\n", encoding="utf-8")
    (HERE / "data" / "unified_v2" / "parser_pilot_summary.json").write_text(
        json.dumps({"n": len(df), "registers": list(by_reg.keys()),
                     "correlations": summary,
                     "mean_time": {"sm": df["t_sm"].mean(),
                                   "trf": df["t_trf"].mean(),
                                   "stanza": df["t_stanza"].mean()}},
                    indent=2),
        encoding="utf-8")

    # Decision
    all_r = [stats.pearsonr(df[a], df[b])[0] for a, b in pairs]
    min_r = min(all_r)
    if min_r >= 0.85:
        log(f"step PHASE3/PILOT · DECISION: sm is acceptable as primary "
            f"(min pairwise r = {min_r:.4f} >= 0.85)")
    else:
        log(f"step PHASE3/PILOT · DECISION: min pairwise r = {min_r:.4f} "
            f"< 0.85 → escalate to full trf as primary")
    return 0


if __name__ == "__main__":
    sys.exit(main())
