"""Unify v2 corpus: merge all source jsonl files into corpus_v2.jsonl/csv."""
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


def log(label: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {label}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


SOURCES = [
    # high_density
    HERE / "data" / "high_density" / "csat"       / "passages.jsonl",
    HERE / "data" / "high_density" / "arxiv"      / "passages.jsonl",
    HERE / "data" / "high_density" / "legal_v2"   / "passages.jsonl",   # v2!
    # baseline
    HERE / "data" / "baseline" / "brown.jsonl",
    HERE / "data" / "baseline" / "gutenberg.jsonl",
    HERE / "data" / "baseline" / "simple_wiki.jsonl",
    HERE / "data" / "baseline" / "wikitext"   / "passages.jsonl",
    HERE / "data" / "baseline" / "reuters"    / "passages.jsonl",
    HERE / "data" / "baseline" / "onestop"    / "passages.jsonl",
]


def main() -> int:
    log("step PHASE2/1 · unifying v2 corpus")
    out_jsonl = HERE / "data" / "unified_v2" / "corpus.jsonl"
    out_csv = HERE / "data" / "unified_v2" / "corpus.csv"

    seen_ids = set()
    seen_texts = set()
    all_recs = []
    for src in SOURCES:
        if not src.exists():
            log(f"step PHASE2/1 · WARN missing {src}")
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
        log(f"step PHASE2/1 · {src.parent.name}/{src.name} kept={n_kept} skip={n_skip}")

    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in all_recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    fields = ["corpus_id", "bucket", "register", "text",
              "category", "court", "question_type", "case_name",
              "title", "source_title", "level",
              "date_filed", "published", "source", "chunk_index",
              "opinion_id"]
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore",
                                quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for r in all_recs:
            writer.writerow({k: r.get(k, "") for k in fields})

    from collections import Counter
    by_register = Counter(r["register"] for r in all_recs)
    by_bucket = Counter(r["bucket"] for r in all_recs)
    log(f"step PHASE2/1 · v2 unified · total={len(all_recs)}")
    log(f"step PHASE2/1 · by_bucket = {dict(by_bucket)}")
    log(f"step PHASE2/1 · by_register = {dict(by_register)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
