"""Re-chunk OneStopEnglish passages with sentence-aligned chunking to fix
the overlong-chunk artifact introduced by the original paragraph-based
chunking when OneStop articles consist of one long paragraph."""
from __future__ import annotations

import datetime as _dt
import io
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
PROGRESS_LOG = HERE / "progress.log"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              line_buffering=True)


def log(label: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {label}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")

TARGET_MIN = 180
TARGET_MAX = 400


def main() -> int:
    src = HERE / "data" / "baseline" / "onestop" / "passages.jsonl"
    recs = [json.loads(l) for l in src.open("r", encoding="utf-8") if l.strip()]
    log(f"step PHASE2.5 · onestop input: {len(recs)} records")

    new_recs = []
    for r in recs:
        text = re.sub(r"\s+", " ", r["text"]).strip()
        wc = len(text.split())
        if TARGET_MIN <= wc <= TARGET_MAX:
            # already acceptable
            new_recs.append(r)
            continue
        # re-chunk
        sents = SENT_SPLIT.split(text)
        sents = [s.strip() for s in sents if len(s.strip()) > 5]
        buf = []
        buf_wc = 0
        chunk_idx = 0
        base_id = r["corpus_id"].rsplit("_c", 1)[0]
        for s in sents:
            sw = len(s.split())
            if buf_wc + sw > TARGET_MAX and buf_wc >= TARGET_MIN:
                new_text = " ".join(buf)
                nr = dict(r)
                nr["corpus_id"] = f"{base_id}_rc{chunk_idx}"
                nr["text"] = new_text
                new_recs.append(nr)
                chunk_idx += 1
                buf = [s]
                buf_wc = sw
            else:
                buf.append(s)
                buf_wc += sw
        if buf and buf_wc >= TARGET_MIN:
            new_text = " ".join(buf)
            nr = dict(r)
            nr["corpus_id"] = f"{base_id}_rc{chunk_idx}"
            nr["text"] = new_text
            new_recs.append(nr)

    # dedupe by text
    seen = set()
    final = []
    for r in new_recs:
        t = r["text"]
        if t in seen:
            continue
        seen.add(t)
        final.append(r)

    with src.open("w", encoding="utf-8") as f:
        for r in final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    log(f"step PHASE2.5 · onestop fixed: {len(final)} records (was {len(recs)})")
    # quick summary
    wcs = [len(r["text"].split()) for r in final]
    if wcs:
        log(f"step PHASE2.5 · WC range [{min(wcs)},{max(wcs)}], "
            f"mean {sum(wcs)/len(wcs):.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
