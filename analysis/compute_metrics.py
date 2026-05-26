"""Compute per-text linguistic indices over the unified corpus.

Indices:
  WC      Word Count (textstat)
  FRE     Flesch Reading Ease (textstat)
  ARI     Automated Readability Index (textstat)
  TTR     Type-Token Ratio (alphabetic lowercased tokens)
  MTLD    Measure of Textual Lexical Diversity (length-robust)
  MCD     Mean Clausal Depth (this study; spaCy dependency-tree recursion
          over labels {ccomp, xcomp, advcl, relcl, acl, csubj})
  MaxCD   Maximum clausal depth across sentences
  MLS     Mean sentence length in words
  MLC     Mean clause length in words (Lu 2010-style approximation)
  CT_T    Complex T-units per T-unit (Lu 2010-style approximation)
  DC_C    Dependent clauses per clause (Lu 2010-style approximation)
  NomR    Nominalisation ratio (proportion of nominal -tion/-ment/-ity/-ness
          forms among content words)

Output:
  data/unified/metrics.csv
  data/unified/metrics.jsonl
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import re
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
    """Measure of Textual Lexical Diversity (McCarthy 2005).  Robust to
    text length; higher = more diverse."""
    if not tokens:
        return 0.0

    def factor_pass(seq: list[str]) -> float:
        types = set()
        factors = 0.0
        running_n = 0
        for tok in seq:
            types.add(tok)
            running_n += 1
            ttr = len(types) / running_n
            if ttr <= threshold:
                factors += 1
                types.clear()
                running_n = 0
        if running_n > 0:
            # partial factor
            ttr = len(types) / running_n
            if ttr < 1.0:
                pf = (1 - ttr) / (1 - threshold)
            else:
                pf = 0.0
            factors += pf
        if factors == 0:
            return float(len(seq))
        return len(seq) / factors

    forward = factor_pass(tokens)
    backward = factor_pass(list(reversed(tokens)))
    return (forward + backward) / 2.0


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

    for sent in doc.sents:
        sent_tokens = [t for t in sent if not t.is_punct]
        sent_lens.append(len(sent_tokens))
        depths.append(max_clausal_depth(sent.root, 0))
        # T-unit count = number of independent clauses in sentence; we use the
        # number of root-like verbs (heads of TOP-level VPs)
        has_independent = False
        for token in sent:
            if token.pos_ == "VERB" or token.pos_ == "AUX":
                if token.dep_ in {"ROOT", "conj"}:
                    n_t_units += 1
                    has_independent = True
                    # any embedded dependent clauses below this T-unit?
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
        if not has_independent and len(sent_tokens) > 0:
            n_t_units += 1
            n_clauses += 1

    mcd = sum(depths) / len(depths) if depths else 0.0
    maxcd = max(depths) if depths else 0
    mls = sum(sent_lens) / len(sent_lens) if sent_lens else 0.0
    mlc = (sum(sent_lens) / n_clauses) if n_clauses else 0.0
    ct_t = (n_complex_t_units / n_t_units) if n_t_units else 0.0
    dc_c = (n_dep_clauses / n_clauses) if n_clauses else 0.0
    nomr = (nominal_count / content_count) if content_count else 0.0

    return {
        "WC": wc, "FRE": round(fre, 3), "ARI": round(ari, 3),
        "TTR": round(ttr, 4), "MTLD": round(mtld_v, 2),
        "MCD": round(mcd, 4), "MaxCD": maxcd,
        "MLS": round(mls, 3), "MLC": round(mlc, 3),
        "CT_T": round(ct_t, 4), "DC_C": round(dc_c, 4),
        "NomR": round(nomr, 4),
        "n_sent": len(depths),
    }


def main() -> int:
    log("step 7/13 · compute metrics begin · loading spaCy")
    nlp = spacy.load("en_core_web_sm")
    nlp.max_length = 500_000

    src = HERE / "data" / "unified" / "corpus.jsonl"
    if not src.exists():
        log("step 7/13 · ERROR · unified corpus not found")
        return 1

    out_csv = HERE / "data" / "unified" / "metrics.csv"
    out_jsonl = HERE / "data" / "unified" / "metrics.jsonl"

    records = []
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    log(f"step 7/13 · loaded {len(records)} passages")

    rows = []
    t0 = time.time()
    for i, rec in enumerate(records):
        try:
            m = metrics_for_text(rec["text"], nlp)
        except Exception as exc:
            log(f"step 7/13 · ERROR at {rec.get('corpus_id')}: {exc}")
            continue
        rows.append({**{k: rec.get(k) for k in ["corpus_id", "bucket",
                                                  "register", "category",
                                                  "court", "question_type"]},
                     **m})
        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(records) - i - 1) / rate
            log(f"step 7/13 · parsed {i+1}/{len(records)} "
                f"({rate:.1f}/s, eta {eta:.0f}s)")

    df = pd.DataFrame(rows)
    df.to_csv(out_csv, index=False, encoding="utf-8")
    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    log(f"step 7/13 · metrics complete · n={len(rows)}")
    # summary
    if len(rows):
        ddf = df.copy()
        log("step 7/13 · summary by bucket:")
        sm = ddf.groupby("bucket")[
            ["WC", "FRE", "TTR", "MCD", "DC_C", "MTLD"]
        ].mean().round(3)
        print(sm.to_string(), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
