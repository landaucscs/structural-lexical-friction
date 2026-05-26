"""Boost the baseline corpus.

  1. Add 10 more Project Gutenberg books to push baseline fiction up.
  2. Retry Simple English Wikipedia at very polite pacing.
  3. Add additional Brown Corpus categories (skipped previously).
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import re
import sys
import time
from pathlib import Path

import requests


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


ADDITIONAL_GUTENBERG = [
    ("Frankenstein, Shelley (1818)",
     "https://www.gutenberg.org/files/84/84-0.txt"),
    ("Great Expectations, Dickens (1861)",
     "https://www.gutenberg.org/files/1400/1400-0.txt"),
    ("Heart of Darkness, Conrad (1899)",
     "https://www.gutenberg.org/cache/epub/219/pg219.txt"),
    ("The Strange Case of Dr Jekyll, Stevenson (1886)",
     "https://www.gutenberg.org/cache/epub/43/pg43.txt"),
    ("Dracula, Stoker (1897)",
     "https://www.gutenberg.org/cache/epub/345/pg345.txt"),
    ("The Awakening, Chopin (1899)",
     "https://www.gutenberg.org/cache/epub/160/pg160.txt"),
    ("A Tale of Two Cities, Dickens (1859)",
     "https://www.gutenberg.org/files/98/98-0.txt"),
    ("Crime and Punishment, Dostoevsky (1866, trans)",
     "https://www.gutenberg.org/files/2554/2554-0.txt"),
    ("The Scarlet Letter, Hawthorne (1850)",
     "https://www.gutenberg.org/cache/epub/25344/pg25344.txt"),
    ("Anne of Green Gables, Montgomery (1908)",
     "https://www.gutenberg.org/cache/epub/45/pg45.txt"),
]


def fetch_more_gutenberg(existing_path: Path, target_additional: int) -> int:
    """Append more Gutenberg chunks to the existing gutenberg.jsonl."""
    existing_recs = []
    seen_texts: set[str] = set()
    if existing_path.exists():
        with existing_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                existing_recs.append(rec)
                seen_texts.add(rec["text"])
    log(f"step EXPAND/2 · existing gutenberg: {len(existing_recs)}")

    n_added = 0
    for title, url in ADDITIONAL_GUTENBERG:
        if n_added >= target_additional:
            break
        log(f"step EXPAND/2 · gutenberg fetching {title}")
        try:
            r = requests.get(url, timeout=60,
                             headers={"User-Agent": "Manuscript/1.0"})
            r.raise_for_status()
        except Exception as exc:
            log(f"step EXPAND/2 · FAIL {title}: {exc}")
            continue
        text = r.text
        start = re.search(r"\*\*\*\s*START OF.*?\*\*\*", text, re.IGNORECASE)
        end = re.search(r"\*\*\*\s*END OF.*?\*\*\*", text, re.IGNORECASE)
        body = text[start.end():end.start()] if (start and end) else text
        paras = re.split(r"\n\s*\n", body)
        kept_here = 0
        for i, p in enumerate(paras):
            if n_added >= target_additional:
                break
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
                                   f"{i + 10000}"),
                    "register": "gutenberg_fiction",
                    "bucket": "baseline",
                    "source_title": title,
                    "source": f"Project Gutenberg: {title}",
                    "text": p,
                }
                existing_recs.append(rec)
                n_added += 1
                kept_here += 1
        log(f"step EXPAND/2 · {title}: kept {kept_here} new chunks "
            f"(total added {n_added})")
        time.sleep(1.0)

    # rewrite gutenberg.jsonl with all records
    with existing_path.open("w", encoding="utf-8") as f:
        for rec in existing_recs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log(f"step EXPAND/2 · gutenberg final size: {len(existing_recs)}")
    return n_added


def retry_simple_wiki(out_path: Path, target_n: int = 300) -> int:
    log(f"step EXPAND/2 · wikipedia retry · target {target_n} · 6s pacing")
    api = "https://simple.wikipedia.org/w/api.php"
    out: list[dict] = []
    seen = set()
    strikes = 0
    max_strikes = 5
    while len(out) < target_n and strikes < max_strikes:
        r = requests.get(api, params={
            "action": "query", "format": "json",
            "generator": "random", "grnnamespace": 0, "grnlimit": 20,
            "prop": "extracts", "explaintext": 1,
        }, headers={"User-Agent": "AcademicManuscript/1.0 (no commercial use)"},
            timeout=30)
        if r.status_code == 429:
            strikes += 1
            wait = 30 + 20 * strikes
            log(f"step EXPAND/2 · wiki 429 strike {strikes}, sleeping {wait}s")
            time.sleep(wait)
            continue
        if r.status_code != 200:
            log(f"step EXPAND/2 · wiki HTTP {r.status_code} abandoning")
            return 0
        strikes = 0
        pages = (r.json().get("query") or {}).get("pages") or {}
        for pid, page in pages.items():
            title = page.get("title", "")
            if title in seen:
                continue
            seen.add(title)
            extract = (page.get("extract") or "").strip()
            for para in re.split(r"\n\s*\n", extract):
                para = re.sub(r"\s+", " ", para).strip()
                wc = len(para.split())
                if 130 <= wc <= 420:
                    out.append({
                        "corpus_id": f"swiki_{pid}",
                        "register": "simple_wikipedia",
                        "bucket": "baseline",
                        "title": title,
                        "source": f"Simple English Wikipedia: {title}",
                        "text": para,
                    })
                    break
            if len(out) >= target_n:
                break
        log(f"step EXPAND/2 · wiki running={len(out)}")
        time.sleep(6.0)
    with out_path.open("w", encoding="utf-8") as f:
        for rec in out:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(out)


def main() -> int:
    log("step EXPAND/2 · baseline boost begin")
    gut_path = HERE / "data" / "baseline" / "gutenberg.jsonl"
    n_g = fetch_more_gutenberg(gut_path, target_additional=400)

    wiki_path = HERE / "data" / "baseline" / "simple_wiki.jsonl"
    n_w = retry_simple_wiki(wiki_path, target_n=300)
    log(f"step EXPAND/2 · wiki final: {n_w}")

    # Recombine into passages.jsonl
    brown_path = HERE / "data" / "baseline" / "brown.jsonl"
    all_recs = []
    for p in [brown_path, gut_path, wiki_path]:
        if not p.exists():
            continue
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                all_recs.append(json.loads(line))
    (HERE / "data" / "baseline" / "passages.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in all_recs) + "\n",
        encoding="utf-8")
    log(f"step EXPAND/2 · baseline boosted final total={len(all_recs)} "
        f"(brown=400, gutenberg+={n_g}, wiki+={n_w})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
