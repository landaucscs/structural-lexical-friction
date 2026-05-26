"""Merge all per-corpus jsonl files into one unified jsonl and CSV with
provenance.  Then validate.
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent
PROGRESS_LOG = HERE / "progress.log"


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              line_buffering=True)


def log(label: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {label}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


SOURCES = [
    HERE / "data" / "high_density" / "csat"   / "passages.jsonl",
    HERE / "data" / "high_density" / "arxiv"  / "passages.jsonl",
    HERE / "data" / "high_density" / "legal"  / "passages.jsonl",
    HERE / "data" / "baseline" / "passages.jsonl",
]


def main() -> int:
    log("step 6/13 · unifying corpus")
    out_jsonl = HERE / "data" / "unified" / "corpus.jsonl"
    out_csv = HERE / "data" / "unified" / "corpus.csv"

    seen_ids = set()
    seen_texts = set()
    all_recs = []

    for src in SOURCES:
        if not src.exists():
            log(f"step 6/13 · WARN missing source {src}")
            continue
        n_kept = 0
        n_skip = 0
        with src.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    n_skip += 1
                    continue
                cid = rec.get("corpus_id")
                txt = (rec.get("text") or "").strip()
                if not cid or not txt:
                    n_skip += 1
                    continue
                if cid in seen_ids:
                    n_skip += 1
                    continue
                if txt in seen_texts:
                    n_skip += 1
                    continue
                seen_ids.add(cid)
                seen_texts.add(txt)
                all_recs.append(rec)
                n_kept += 1
        log(f"step 6/13 · {src.parent.name}/{src.name} kept={n_kept} skip={n_skip}")

    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in all_recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # CSV with normalized columns
    fields = ["corpus_id", "bucket", "register", "text",
              "category", "court", "question_type", "case_name", "title",
              "date_filed", "published", "source"]
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore",
                                quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for r in all_recs:
            writer.writerow({k: r.get(k, "") for k in fields})

    # Summary by register
    by_register: dict[str, int] = {}
    by_bucket: dict[str, int] = {}
    for r in all_recs:
        by_register[r["register"]] = by_register.get(r["register"], 0) + 1
        by_bucket[r["bucket"]] = by_bucket.get(r["bucket"], 0) + 1
    log(f"step 6/13 · unified corpus · total={len(all_recs)}")
    log(f"step 6/13 · by_bucket = {by_bucket}")
    log(f"step 6/13 · by_register = {by_register}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
