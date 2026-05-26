"""Build a length-matched sub-corpus where every passage has WC in the
narrow band [150, 190] (the CSAT distribution).  Long passages are
sentence-split and re-chunked; short passages are dropped.

This isolates structural signal from register-typical length differences.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import random
import re
import sys
from pathlib import Path

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


TARGET_MIN = 150
TARGET_MAX = 190
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
PER_REGISTER_CAP = 1500  # cap per register to keep balance


def chunk_to_target(text: str) -> list[str]:
    """Sentence-align and produce chunks within target band."""
    text = re.sub(r"\s+", " ", text).strip()
    wc = len(text.split())
    if TARGET_MIN <= wc <= TARGET_MAX:
        return [text]
    if wc < TARGET_MIN:
        return []
    sents = SENT_SPLIT.split(text)
    sents = [s.strip() for s in sents if len(s.strip()) > 4]
    chunks = []
    buf = []
    buf_wc = 0
    for s in sents:
        sw = len(s.split())
        if sw > TARGET_MAX:
            # single oversized sentence — drop, can't fit
            continue
        if buf_wc + sw > TARGET_MAX and buf_wc >= TARGET_MIN:
            chunks.append(" ".join(buf))
            buf = [s]
            buf_wc = sw
        else:
            buf.append(s)
            buf_wc += sw
    if buf and TARGET_MIN <= buf_wc <= TARGET_MAX:
        chunks.append(" ".join(buf))
    return chunks


def main() -> int:
    log(f"step REV/4 · build length-matched sub-corpus · target [{TARGET_MIN},{TARGET_MAX}]")
    rng = random.Random(2026)
    src = HERE / "data" / "unified_v2" / "corpus.jsonl"
    recs = [json.loads(l) for l in src.open("r", encoding="utf-8") if l.strip()]
    log(f"step REV/4 · input: {len(recs)} passages")

    by_register: dict[str, list] = {}
    for r in recs:
        by_register.setdefault(r["register"], []).append(r)

    out_recs = []
    summary: dict[str, int] = {}
    for reg, rs in by_register.items():
        kept = []
        rng.shuffle(rs)
        for r in rs:
            chunks = chunk_to_target(r["text"])
            for ci, c in enumerate(chunks):
                if len(kept) >= PER_REGISTER_CAP:
                    break
                new_id = f"{r['corpus_id']}_lm{ci}"
                new_rec = dict(r)
                new_rec["corpus_id"] = new_id
                new_rec["text"] = c
                kept.append(new_rec)
            if len(kept) >= PER_REGISTER_CAP:
                break
        summary[reg] = len(kept)
        out_recs.extend(kept)
        log(f"step REV/4 · {reg}: {len(kept)} length-matched chunks")

    out_path = HERE / "data" / "unified_v2" / "corpus_length_matched.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for r in out_recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    by_bucket = Counter(r["bucket"] for r in out_recs)
    log(f"step REV/4 · DONE · n={len(out_recs)} · by_bucket={dict(by_bucket)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
