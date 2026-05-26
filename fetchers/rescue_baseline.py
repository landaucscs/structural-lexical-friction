"""Rescue baseline: skip simple-wiki (rate-limited at our IP) and just
add Project Gutenberg fiction chunks to the existing Brown corpus.
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


GUTENBERG_URLS = [
    ("Wuthering Heights, Bronte (1847)",
     "https://www.gutenberg.org/files/768/768-0.txt"),
    ("The Adventures of Sherlock Holmes, Doyle (1892)",
     "https://www.gutenberg.org/files/1661/1661-0.txt"),
    ("Pride and Prejudice, Austen (1813)",
     "https://www.gutenberg.org/files/1342/1342-0.txt"),
    ("Moby-Dick, Melville (1851)",
     "https://www.gutenberg.org/files/2701/2701-0.txt"),
    ("Treasure Island, Stevenson (1883)",
     "https://www.gutenberg.org/files/120/120-0.txt"),
    ("The Picture of Dorian Gray, Wilde (1890)",
     "https://www.gutenberg.org/files/174/174-0.txt"),
    ("Frankenstein, Shelley (1818)",
     "https://www.gutenberg.org/files/84/84-0.txt"),
    ("Great Expectations, Dickens (1861)",
     "https://www.gutenberg.org/files/1400/1400-0.txt"),
]

TARGET_GUTENBERG = 350


def fetch_gutenberg(target_n: int) -> list[dict]:
    out: list[dict] = []
    for title, url in GUTENBERG_URLS:
        if len(out) >= target_n:
            break
        log(f"step 5b/13 · gutenberg fetching {title}")
        try:
            r = requests.get(url, timeout=60,
                             headers={"User-Agent": "Manuscript/1.0"})
            r.raise_for_status()
        except Exception as exc:
            log(f"step 5b/13 · FAIL {title}: {exc}")
            continue
        text = r.text
        start = re.search(r"\*\*\*\s*START OF.*?\*\*\*", text, re.IGNORECASE)
        end = re.search(r"\*\*\*\s*END OF.*?\*\*\*", text, re.IGNORECASE)
        body = text[start.end():end.start()] if (start and end) else text
        paras = re.split(r"\n\s*\n", body)
        kept_local = 0
        for i, p in enumerate(paras):
            if len(out) >= target_n:
                break
            p = re.sub(r"\s+", " ", p).strip()
            wc = len(p.split())
            if 130 <= wc <= 420 and not p.startswith("CHAPTER") \
               and not p.isupper():
                if any(x in p.lower() for x in [
                        "produced by", "the project gutenberg",
                        "transcriber's note", "*** start", "*** end"]):
                    continue
                out.append({
                    "corpus_id": (f"gutenberg_{abs(hash(title)) % 100000}_"
                                   f"{i}"),
                    "register": "gutenberg_fiction",
                    "bucket": "baseline",
                    "source_title": title,
                    "source": f"Project Gutenberg: {title}",
                    "text": p,
                })
                kept_local += 1
        log(f"step 5b/13 · {title}: kept {kept_local} chunks "
            f"(running total {len(out)})")
        time.sleep(1.0)
    return out[:target_n]


def fetch_simple_wiki_one(target_n: int, max_attempts: int = 6) -> list[dict]:
    """Light retry attempt; abandons on persistent rate-limit."""
    log(f"step 5b/13 · simple-wiki attempt · target={target_n}")
    out: list[dict] = []
    api = "https://simple.wikipedia.org/w/api.php"
    seen = set()
    attempts_used = 0
    while len(out) < target_n and attempts_used < max_attempts:
        attempts_used += 1
        r = requests.get(api, params={
            "action": "query", "format": "json",
            "generator": "random", "grnnamespace": 0, "grnlimit": 20,
            "prop": "extracts", "explaintext": 1,
        }, headers={"User-Agent": "Manuscript/1.0 (research)"},
            timeout=30)
        if r.status_code != 200:
            log(f"step 5b/13 · swiki HTTP {r.status_code}, abandoning")
            return out
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
        log(f"step 5b/13 · swiki running={len(out)} (attempt {attempts_used})")
        time.sleep(5.0)
    return out[:target_n]


def main() -> int:
    log("step 5b/13 · rescue baseline · gutenberg + opportunistic wiki")

    # 1. carry forward existing brown
    brown_path = HERE / "data" / "baseline" / "brown.jsonl"
    brown_recs = []
    if brown_path.exists():
        with brown_path.open("r", encoding="utf-8") as f:
            brown_recs = [json.loads(l) for l in f if l.strip()]
        log(f"step 5b/13 · brown carried forward: {len(brown_recs)}")

    # 2. gutenberg
    gut_recs = fetch_gutenberg(TARGET_GUTENBERG)
    (HERE / "data" / "baseline" / "gutenberg.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in gut_recs) + "\n",
        encoding="utf-8")
    log(f"step 5b/13 · gutenberg final={len(gut_recs)}")

    # 3. opportunistic wiki
    wiki_recs = fetch_simple_wiki_one(150)
    (HERE / "data" / "baseline" / "simple_wiki.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in wiki_recs) + "\n"
        if wiki_recs else "",
        encoding="utf-8")
    log(f"step 5b/13 · swiki final={len(wiki_recs)}")

    # 4. combine
    all_recs = brown_recs + gut_recs + wiki_recs
    (HERE / "data" / "baseline" / "passages.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in all_recs) + "\n",
        encoding="utf-8")
    log(f"step 5b/13 · baseline FINAL total={len(all_recs)} "
        f"(brown={len(brown_recs)} gutenberg={len(gut_recs)} "
        f"swiki={len(wiki_recs)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
