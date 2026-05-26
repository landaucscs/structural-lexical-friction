"""Ingest CSAT jsonl files from ricemachine into a unified passages.jsonl."""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent
PROGRESS_LOG = HERE / "progress.log"


def log(label: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {label}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


CSAT_ROOT = Path(
    r"C:\Users\JH\Desktop\2026 Reboot\ricemachine\seed-data\passages"
)

FILES = [
    ("blank_wholepassagewithfilledblank.jsonl", "blank_filled"),
    ("irrelevant_onlypassages.jsonl",            "irrelevant"),
    ("claim.jsonl",        "claim"),
    ("gist.jsonl",         "gist"),
    ("topic.jsonl",        "topic"),
    ("title.jsonl",        "title"),
    ("implication.jsonl",  "implication"),
    ("summary.jsonl",      "summary"),
]


def main() -> int:
    log("step 2/13 · ingest_csat begin")
    out = HERE / "data" / "high_density" / "csat" / "passages.jsonl"
    total = 0
    by_type: dict[str, int] = {}
    with out.open("w", encoding="utf-8") as fout:
        for fname, label in FILES:
            src = CSAT_ROOT / fname
            if not src.exists():
                log(f"step 2/13 · missing {fname}")
                continue
            with src.open("r", encoding="utf-8") as fin:
                for lineno, line in enumerate(fin, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError as exc:
                        log(f"step 2/13 · SKIP malformed line {fname}:{lineno} "
                            f"({exc.msg} at col {exc.colno})")
                        continue
                    passage = rec.get("passage", "").strip()
                    if not passage:
                        continue
                    out_rec = {
                        "corpus_id": f"csat_{rec.get('question_code', total)}",
                        "register": "csat",
                        "bucket": "high_density",
                        "question_type": label,
                        "source_question_code": rec.get("question_code"),
                        "text": passage,
                    }
                    fout.write(json.dumps(out_rec, ensure_ascii=False) + "\n")
                    total += 1
                    by_type[label] = by_type.get(label, 0) + 1
            log(f"step 2/13 · ingested {fname}: {by_type.get(label, 0)} passages")
    log(f"step 2/13 · csat ingest complete · total={total} · by_type={by_type}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
