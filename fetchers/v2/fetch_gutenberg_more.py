"""Add another 10+ Project Gutenberg books to broaden the baseline fiction
sample. Targets paragraphs of 130-420 words."""
from __future__ import annotations

import datetime as _dt
import io
import json
import re
import sys
import time
from pathlib import Path

import requests

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


ADDITIONAL = [
    ("The Time Machine, Wells (1895)",
     "https://www.gutenberg.org/cache/epub/35/pg35.txt"),
    ("The Adventures of Tom Sawyer, Twain (1876)",
     "https://www.gutenberg.org/cache/epub/74/pg74.txt"),
    ("Around the World in Eighty Days, Verne (1872)",
     "https://www.gutenberg.org/cache/epub/103/pg103.txt"),
    ("The Wonderful Wizard of Oz, Baum (1900)",
     "https://www.gutenberg.org/cache/epub/55/pg55.txt"),
    ("Walden, Thoreau (1854)",
     "https://www.gutenberg.org/cache/epub/205/pg205.txt"),
    ("The Adventures of Huckleberry Finn, Twain (1884)",
     "https://www.gutenberg.org/cache/epub/76/pg76.txt"),
    ("Adventures of Robinson Crusoe, Defoe (1719)",
     "https://www.gutenberg.org/cache/epub/521/pg521.txt"),
    ("Emma, Austen (1815)",
     "https://www.gutenberg.org/cache/epub/158/pg158.txt"),
    ("The Iliad, Homer (translated)",
     "https://www.gutenberg.org/cache/epub/2199/pg2199.txt"),
    ("The Republic, Plato (translated)",
     "https://www.gutenberg.org/cache/epub/1497/pg1497.txt"),
    ("Sense and Sensibility, Austen (1811)",
     "https://www.gutenberg.org/cache/epub/161/pg161.txt"),
    ("Don Quixote, Cervantes (translated)",
     "https://www.gutenberg.org/cache/epub/996/pg996.txt"),
]


def main() -> int:
    existing = HERE / "data" / "baseline" / "gutenberg.jsonl"
    existing_recs = []
    seen_texts: set[str] = set()
    if existing.exists():
        with existing.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                existing_recs.append(rec)
                seen_texts.add(rec["text"])
    log(f"step PHASE1/7 · gutenberg existing: {len(existing_recs)}")
    target_per_book = 100
    for title, url in ADDITIONAL:
        try:
            r = requests.get(url, timeout=60,
                             headers={"User-Agent": "Manuscript/2.0"})
            r.raise_for_status()
        except Exception as exc:
            log(f"step PHASE1/7 · FAIL {title}: {exc}")
            continue
        text = r.text
        start = re.search(r"\*\*\*\s*START OF.*?\*\*\*", text, re.IGNORECASE)
        end = re.search(r"\*\*\*\s*END OF.*?\*\*\*", text, re.IGNORECASE)
        body = text[start.end():end.start()] if (start and end) else text
        paras = re.split(r"\n\s*\n", body)
        kept_here = 0
        for i, p in enumerate(paras):
            p = re.sub(r"\s+", " ", p).strip()
            wc = len(p.split())
            if 130 <= wc <= 420 and not p.startswith("CHAPTER") and \
               not p.isupper():
                if any(x in p.lower() for x in [
                        "produced by", "the project gutenberg",
                        "transcriber's note", "*** start", "*** end"]):
                    continue
                if p in seen_texts:
                    continue
                seen_texts.add(p)
                rec = {
                    "corpus_id": (f"gutenberg_{abs(hash(title)) % 100000}_"
                                   f"{i + 20000}"),
                    "register": "gutenberg_fiction",
                    "bucket": "baseline",
                    "source_title": title,
                    "source": f"Project Gutenberg: {title}",
                    "text": p,
                }
                existing_recs.append(rec)
                kept_here += 1
                if kept_here >= target_per_book:
                    break
        log(f"step PHASE1/7 · {title}: +{kept_here}")
        time.sleep(0.8)
    with existing.open("w", encoding="utf-8") as f:
        for rec in existing_recs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log(f"step PHASE1/7 · gutenberg final size: {len(existing_recs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
