"""Build the baseline (general informational) corpus from three sources:

    1. NLTK Brown Corpus — news + editorial + reviews + lore + non-fiction
    2. Simple English Wikipedia — featured articles + random sample via API
    3. Project Gutenberg — modern public-domain fiction excerpts

Each source contributes a labelled jsonl section.  Texts are 150-450 words
to match the typical length of the high-density corpora; longer source
documents are chunked at paragraph boundaries.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import random
import re
import sys
import time
from pathlib import Path

import requests


# Force UTF-8 stdout on Windows (default PowerShell cp949 cannot encode é, ë, ...)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              line_buffering=True)


HERE = Path(__file__).resolve().parent.parent
PROGRESS_LOG = HERE / "progress.log"


def log(label: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {label}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------------------
# Brown Corpus via NLTK
# ---------------------------------------------------------------------------

BROWN_CATEGORIES = ["news", "editorial", "reviews", "lore", "learned",
                    "religion", "hobbies"]


def fetch_brown(target_n: int) -> list[dict]:
    log("step 5/13 · brown · downloading nltk brown corpus (~6MB)")
    import nltk
    nltk.download("brown", quiet=True)
    from nltk.corpus import brown
    out: list[dict] = []
    for cat in BROWN_CATEGORIES:
        for fileid in brown.fileids(categories=cat):
            paras = brown.paras(fileids=fileid)
            sentences_text = []
            for para in paras:
                p = " ".join(" ".join(w for w in s) for s in para)
                # restore basic typography
                p = re.sub(r"\s+([,.;:!?])", r"\1", p)
                p = re.sub(r"\s+'\s+", "'", p)
                p = re.sub(r"\s+", " ", p).strip()
                if 130 <= len(p.split()) <= 420:
                    out.append({
                        "corpus_id": f"brown_{fileid}_{len(out)}",
                        "register": "brown_news_general",
                        "bucket": "baseline",
                        "category": cat,
                        "source": f"NLTK Brown Corpus, file {fileid}",
                        "text": p,
                    })
                    if len(out) >= target_n:
                        return out
                else:
                    sentences_text.append(p)
            # also try chunking adjacent paragraphs
            if len(out) >= target_n:
                return out
    log(f"step 5/13 · brown · extracted {len(out)} passages")
    return out


# ---------------------------------------------------------------------------
# Simple English Wikipedia via API
# ---------------------------------------------------------------------------

def fetch_simple_wiki(target_n: int) -> list[dict]:
    log(f"step 5/13 · simple-wiki · target={target_n}")
    out: list[dict] = []
    api = "https://simple.wikipedia.org/w/api.php"
    seen_titles = set()
    consecutive_429 = 0
    while len(out) < target_n and consecutive_429 < 3:
        r = requests.get(api, params={
            "action": "query",
            "format": "json",
            "generator": "random",
            "grnnamespace": 0,
            "grnlimit": 20,
            "prop": "extracts",
            "explaintext": 1,
            "exsectionformat": "plain",
        }, headers={"User-Agent": "Manuscript/1.0 (academic research)"},
            timeout=30)
        if r.status_code == 429:
            consecutive_429 += 1
            wait = 30 * consecutive_429
            log(f"step 5/13 · simple-wiki 429 · backoff {wait}s "
                f"(strike {consecutive_429})")
            time.sleep(wait)
            continue
        if r.status_code != 200:
            log(f"step 5/13 · simple-wiki HTTP {r.status_code} · stopping")
            break
        consecutive_429 = 0
        data = r.json()
        pages = (data.get("query") or {}).get("pages") or {}
        for pid, page in pages.items():
            title = page.get("title", "")
            if title in seen_titles:
                continue
            seen_titles.add(title)
            extract = (page.get("extract") or "").strip()
            if not extract:
                continue
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
        log(f"step 5/13 · simple-wiki · running={len(out)}")
        time.sleep(3.0)
    return out[:target_n]


# ---------------------------------------------------------------------------
# Project Gutenberg modern fiction.  We pull a handful of long-form texts
# and chunk them into ~250-word paragraphs.  Public domain only.
# ---------------------------------------------------------------------------

GUTENBERG_URLS = [
    # Title, URL (UTF-8 plain text)
    ("Wuthering Heights, Brontë (1847)",
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
]


def fetch_gutenberg(target_n: int) -> list[dict]:
    log(f"step 5/13 · gutenberg · target={target_n}")
    out: list[dict] = []
    for title, url in GUTENBERG_URLS:
        if len(out) >= target_n:
            break
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
        except Exception as exc:
            log(f"step 5/13 · gutenberg · fetch FAIL {title}: {exc}")
            continue
        text = r.text
        # strip Project Gutenberg header and footer
        start = re.search(r"\*\*\*\s*START OF.*?\*\*\*", text, re.IGNORECASE)
        end = re.search(r"\*\*\*\s*END OF.*?\*\*\*", text, re.IGNORECASE)
        if start and end:
            body = text[start.end():end.start()]
        else:
            body = text
        # split into paragraphs by blank lines
        paras = re.split(r"\n\s*\n", body)
        kept_local = 0
        for i, p in enumerate(paras):
            if len(out) >= target_n:
                break
            p = re.sub(r"\s+", " ", p).strip()
            wc = len(p.split())
            if 130 <= wc <= 420 and not p.startswith("CHAPTER") and not p.isupper():
                # filter out illustrations / contents lines / front matter
                if any(x in p.lower() for x in ["produced by",
                                                  "the project gutenberg",
                                                  "transcriber's note"]):
                    continue
                out.append({
                    "corpus_id": f"gutenberg_{i}_{abs(hash(title)) % 100000}",
                    "register": "gutenberg_fiction",
                    "bucket": "baseline",
                    "source_title": title,
                    "source": f"Project Gutenberg: {title}",
                    "text": p,
                })
                kept_local += 1
        log(f"step 5/13 · gutenberg · {title}: kept {kept_local} chunks "
            f"(running total {len(out)})")
        time.sleep(0.5)
    return out[:target_n]


def write_jsonl(records: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8") as fout:
        for rec in records:
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> int:
    log("step 5/13 · baseline corpus build begin")
    random.seed(20260520)

    brown_recs = fetch_brown(400)
    log(f"step 5/13 · brown · final={len(brown_recs)} passages")
    write_jsonl(brown_recs, HERE / "data" / "baseline" / "brown.jsonl")

    wiki_recs = fetch_simple_wiki(300)
    log(f"step 5/13 · simple-wiki · final={len(wiki_recs)} passages")
    write_jsonl(wiki_recs, HERE / "data" / "baseline" / "simple_wiki.jsonl")

    gut_recs = fetch_gutenberg(250)
    log(f"step 5/13 · gutenberg · final={len(gut_recs)} passages")
    write_jsonl(gut_recs, HERE / "data" / "baseline" / "gutenberg.jsonl")

    all_recs = brown_recs + wiki_recs + gut_recs
    write_jsonl(all_recs, HERE / "data" / "baseline" / "passages.jsonl")
    total = len(all_recs)
    log(f"step 5/13 · baseline complete · brown={len(brown_recs)} "
        f"swiki={len(wiki_recs)} gutenberg={len(gut_recs)} total={total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
