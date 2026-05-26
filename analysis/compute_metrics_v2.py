"""Compute extended linguistic metrics on the v2 corpus.

Adds (beyond the v1 set):
  MAL       Mean Arc Length (Gibson-style proxy for storage cost; standard
            dependency-tree complexity index).
  MaxAL     Mean per-sentence maximum arc length.
  LeftBR    Left-branching ratio (Frazier-style proxy; fraction of dependents
            whose head is to the right of the dependent).
  ArcCross  Mean per-token count of arcs that span across the token's position
            (Yngve-style embedded-dependency depth approximation).
  MaxArcCross Mean per-sentence maximum arc-crossing index.

Usage:
  python compute_metrics_v2.py [--parser sm|trf]
  Default parser is 'sm' (en_core_web_sm).
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import io
import json
import sys
import time
from pathlib import Path

import pandas as pd
import spacy
import textstat


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


CLAUSAL_DEPS = {"ccomp", "xcomp", "advcl", "relcl", "acl", "csubj"}
NOMINAL_SUFFIXES = ("tion", "ment", "ity", "ness", "ance", "ence", "sion")


def max_clausal_depth(token, depth: int = 0) -> int:
    if not list(token.children):
        return depth
    best = depth
    for child in token.children:
        inc = 1 if child.dep_ in CLAUSAL_DEPS else 0
        sub = max_clausal_depth(child, depth + inc)
        if sub > best:
            best = sub
    return best


def mtld(tokens: list[str], threshold: float = 0.72) -> float:
    if not tokens:
        return 0.0

    def fp(seq):
        types = set()
        factors = 0.0
        n = 0
        for t in seq:
            types.add(t)
            n += 1
            if len(types) / n <= threshold:
                factors += 1
                types.clear()
                n = 0
        if n > 0:
            ttr = len(types) / n
            factors += (1 - ttr) / (1 - threshold) if ttr < 1.0 else 0.0
        if factors == 0:
            return float(len(seq))
        return len(seq) / factors

    return (fp(tokens) + fp(list(reversed(tokens)))) / 2.0


def sentence_dep_metrics(sent) -> dict:
    """Per-sentence arc-based complexity metrics."""
    tokens = [t for t in sent if not t.is_punct]
    if not tokens:
        return {"arcs": 0, "mal": 0.0, "max_al": 0,
                "left_arcs": 0, "right_arcs": 0,
                "max_arc_cross": 0, "mean_arc_cross": 0.0}
    arc_lengths = []
    left_arcs = 0
    right_arcs = 0
    for t in tokens:
        if t.head == t:
            continue
        d = abs(t.i - t.head.i)
        arc_lengths.append(d)
        if t.head.i > t.i:
            left_arcs += 1  # dependent precedes head (left-branching attachment)
        else:
            right_arcs += 1
    if not arc_lengths:
        return {"arcs": 0, "mal": 0.0, "max_al": 0,
                "left_arcs": 0, "right_arcs": 0,
                "max_arc_cross": 0, "mean_arc_cross": 0.0}
    # arc crossing: for each token position, count arcs that strictly span over it
    cross_counts = []
    sent_start = sent.start
    sent_end = sent.end
    for pos in range(sent_start, sent_end):
        n = 0
        for t in tokens:
            if t.head == t:
                continue
            lo, hi = min(t.i, t.head.i), max(t.i, t.head.i)
            if lo < pos < hi:
                n += 1
        cross_counts.append(n)
    return {
        "arcs": len(arc_lengths),
        "mal": sum(arc_lengths) / len(arc_lengths),
        "max_al": max(arc_lengths),
        "left_arcs": left_arcs,
        "right_arcs": right_arcs,
        "max_arc_cross": max(cross_counts) if cross_counts else 0,
        "mean_arc_cross": (sum(cross_counts) / len(cross_counts)
                            if cross_counts else 0.0),
    }


def metrics_for_text(text: str, nlp) -> dict:
    flat = " ".join(text.split())
    wc = textstat.lexicon_count(flat, removepunct=True)
    fre = textstat.flesch_reading_ease(flat)
    ari = textstat.automated_readability_index(flat)

    raw_toks = [t for t in flat.lower().split() if any(c.isalpha() for c in t)]
    norm = ["".join(c for c in t if c.isalpha()) for t in raw_toks]
    norm = [t for t in norm if t]
    ttr = len(set(norm)) / len(norm) if norm else 0.0
    mtld_v = mtld(norm)

    doc = nlp(flat)
    depths = []
    sent_lens = []
    n_clauses = 0
    n_dep_clauses = 0
    n_t_units = 0
    n_complex_t_units = 0
    nominal_count = 0
    content_count = 0
    sent_metrics = []
    for sent in doc.sents:
        sent_tokens = [t for t in sent if not t.is_punct]
        sent_lens.append(len(sent_tokens))
        depths.append(max_clausal_depth(sent.root, 0))
        for token in sent:
            if token.pos_ == "VERB" or token.pos_ == "AUX":
                if token.dep_ in {"ROOT", "conj"}:
                    n_t_units += 1
                    if any(t.dep_ in CLAUSAL_DEPS for t in token.subtree):
                        n_complex_t_units += 1
            if token.dep_ in CLAUSAL_DEPS:
                n_dep_clauses += 1
            if (token.dep_ in CLAUSAL_DEPS) or (token.dep_ == "ROOT" and token.pos_ in {"VERB", "AUX"}):
                n_clauses += 1
            if token.pos_ in {"NOUN", "ADJ", "VERB", "ADV"}:
                content_count += 1
                lemma_lower = token.lemma_.lower()
                if any(lemma_lower.endswith(sfx) for sfx in NOMINAL_SUFFIXES):
                    nominal_count += 1
        sent_metrics.append(sentence_dep_metrics(sent))

    mcd = sum(depths) / len(depths) if depths else 0.0
    maxcd = max(depths) if depths else 0
    mls = sum(sent_lens) / len(sent_lens) if sent_lens else 0.0
    mlc = (sum(sent_lens) / n_clauses) if n_clauses else 0.0
    ct_t = (n_complex_t_units / n_t_units) if n_t_units else 0.0
    dc_c = (n_dep_clauses / n_clauses) if n_clauses else 0.0
    nomr = (nominal_count / content_count) if content_count else 0.0

    n = len(sent_metrics) or 1
    mal = sum(s["mal"] for s in sent_metrics) / n
    max_al = sum(s["max_al"] for s in sent_metrics) / n
    total_arcs = sum(s["arcs"] for s in sent_metrics) or 1
    total_left = sum(s["left_arcs"] for s in sent_metrics)
    leftbr = total_left / total_arcs
    mean_cross = sum(s["mean_arc_cross"] for s in sent_metrics) / n
    max_cross = sum(s["max_arc_cross"] for s in sent_metrics) / n

    return {
        "WC": wc, "FRE": round(fre, 3), "ARI": round(ari, 3),
        "TTR": round(ttr, 4), "MTLD": round(mtld_v, 2),
        "MCD": round(mcd, 4), "MaxCD": maxcd,
        "MLS": round(mls, 3), "MLC": round(mlc, 3),
        "CT_T": round(ct_t, 4), "DC_C": round(dc_c, 4),
        "NomR": round(nomr, 4),
        # Phase-2 additions
        "MAL": round(mal, 4),
        "MaxAL": round(max_al, 3),
        "LeftBR": round(leftbr, 4),
        "MeanArcCross": round(mean_cross, 4),
        "MaxArcCross": round(max_cross, 3),
        "n_sent": len(depths),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parser", default="sm", choices=["sm", "trf"],
                    help="spaCy English model: sm or trf")
    ap.add_argument("--corpus", default="data/unified_v2/corpus.jsonl")
    ap.add_argument("--out-stem", default=None,
                    help="output stem; defaults to metrics_v2_{parser}")
    args = ap.parse_args()

    model_name = {"sm": "en_core_web_sm",
                  "trf": "en_core_web_trf"}[args.parser]
    out_stem = args.out_stem or f"metrics_v2_{args.parser}"

    log(f"step PHASE2/2 · loading parser {model_name}")
    nlp = spacy.load(model_name)
    nlp.max_length = 500_000

    src = HERE / args.corpus
    records = []
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    log(f"step PHASE2/2 · loaded {len(records)} passages")

    rows = []
    t0 = time.time()
    for i, rec in enumerate(records):
        try:
            m = metrics_for_text(rec["text"], nlp)
        except Exception as exc:
            log(f"step PHASE2/2 · ERROR {rec.get('corpus_id')}: {exc}")
            continue
        rows.append({**{k: rec.get(k) for k in
                         ["corpus_id", "bucket", "register", "category",
                          "court", "question_type", "level"]},
                     **m})
        # progress logging
        if args.parser == "trf":
            # trf is slow; log every 50
            log_every = 50
        else:
            log_every = 200
        if (i + 1) % log_every == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(records) - i - 1) / rate
            log(f"step PHASE2/2 [{args.parser}] · parsed {i+1}/{len(records)} "
                f"({rate:.2f}/s, eta {eta/60:.1f}min)")

    df = pd.DataFrame(rows)
    out_csv = HERE / "data" / "unified_v2" / f"{out_stem}.csv"
    out_jsonl = HERE / "data" / "unified_v2" / f"{out_stem}.jsonl"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    log(f"step PHASE2/2 [{args.parser}] · DONE · n={len(rows)} · "
        f"elapsed={time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
