"""Finalize trf metrics: top up the trf coverage for the 237 onestop chunks
that were added after the trf parse started, then merge into a complete
metrics_v2_trf_full.csv covering all 12,243 passages.

Usage: python finalize_trf.py
Pre-requirement: data/unified_v2/metrics_v2_trf.csv already produced by the
background trf parse (on the original 12,006-record corpus).
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import sys
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


def main() -> int:
    trf_csv = HERE / "data" / "unified_v2" / "metrics_v2_trf.csv"
    if not trf_csv.exists():
        log("step PHASE5/1 · trf metrics file not yet available — abort")
        return 1
    df_trf = pd.read_csv(trf_csv)
    trf_ids = set(df_trf["corpus_id"].astype(str).tolist())
    log(f"step PHASE5/1 · trf coverage: {len(trf_ids)} corpus_ids")

    # find missing corpus_ids relative to unified v2 corpus
    corp = []
    with (HERE / "data" / "unified_v2" / "corpus.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                corp.append(json.loads(line))
    log(f"step PHASE5/1 · v2 corpus size: {len(corp)}")

    missing = [r for r in corp if r["corpus_id"] not in trf_ids]
    log(f"step PHASE5/1 · missing from trf: {len(missing)}")
    if not missing:
        log("step PHASE5/1 · trf already covers everything; nothing to top up")
        out_csv = HERE / "data" / "unified_v2" / "metrics_v2_trf_full.csv"
        df_trf.to_csv(out_csv, index=False)
        return 0

    # compute trf metrics on missing records using the same metrics function
    sys.path.insert(0, str(HERE / "analysis"))
    from compute_metrics_v2 import metrics_for_text
    import spacy
    log("step PHASE5/1 · loading en_core_web_trf")
    nlp = spacy.load("en_core_web_trf")
    nlp.max_length = 500_000
    new_rows = []
    for i, rec in enumerate(missing):
        try:
            m = metrics_for_text(rec["text"], nlp)
        except Exception as exc:
            log(f"step PHASE5/1 · ERROR {rec.get('corpus_id')}: {exc}")
            continue
        new_rows.append({**{k: rec.get(k) for k in
                             ["corpus_id", "bucket", "register", "category",
                              "court", "question_type", "level"]},
                         **m})
        if (i + 1) % 25 == 0:
            log(f"step PHASE5/1 · topup {i+1}/{len(missing)}")
    df_new = pd.DataFrame(new_rows)
    log(f"step PHASE5/1 · topup done: {len(df_new)} new rows")

    df_full = pd.concat([df_trf, df_new], ignore_index=True)
    out_csv = HERE / "data" / "unified_v2" / "metrics_v2_trf_full.csv"
    df_full.to_csv(out_csv, index=False)
    log(f"step PHASE5/1 · wrote metrics_v2_trf_full.csv · n={len(df_full)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
