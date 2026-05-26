"""Expand arXiv corpus from 779 -> 2000+ by fetching more recent abstracts
from the same categories, then merging unique entries with existing file.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
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


# Aim for total ~2200 keeping balance similar across categories
CATEGORIES = [
    ("cs.CL",     500),
    ("q-bio",     300),
    ("physics",   300),
    ("math",      300),
    ("econ",      300),
    ("stat",      300),  # new category for diversity
    ("cs.LG",     500),  # new
]

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def fetch_one(category: str, n: int, start: int) -> list[dict]:
    url = (
        "http://export.arxiv.org/api/query?"
        f"search_query=cat:{category}*"
        f"&start={start}&max_results={n}"
        "&sortBy=submittedDate&sortOrder=descending"
    )
    log(f"step PHASE1/5 · arxiv GET {category} start={start} n={n}")
    r = requests.get(url, timeout=60,
                     headers={"User-Agent": "Manuscript/2.0"})
    r.raise_for_status()
    root = ET.fromstring(r.text)
    out = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title_el = entry.find("atom:title", ATOM_NS)
        sum_el = entry.find("atom:summary", ATOM_NS)
        id_el = entry.find("atom:id", ATOM_NS)
        pub_el = entry.find("atom:published", ATOM_NS)
        if title_el is None or sum_el is None or id_el is None:
            continue
        abstract = (sum_el.text or "").strip()
        abstract = re.sub(r"\s+", " ", abstract)
        if len(abstract.split()) < 50:
            continue
        ascii_ratio = sum(1 for c in abstract if ord(c) < 128) / max(1, len(abstract))
        if ascii_ratio < 0.95:
            continue
        out.append({
            "arxiv_id": (id_el.text or "").strip(),
            "category": category,
            "title": re.sub(r"\s+", " ", (title_el.text or "").strip()),
            "abstract": abstract,
            "published": (pub_el.text or "").strip() if pub_el is not None else "",
        })
    return out


def main() -> int:
    log("step PHASE1/5 · arxiv expansion begin")
    # load existing IDs to dedupe
    existing = set()
    existing_recs = []
    existing_path = HERE / "data" / "high_density" / "arxiv" / "passages.jsonl"
    if existing_path.exists():
        with existing_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                existing.add(rec["corpus_id"])
                existing_recs.append(rec)
    log(f"step PHASE1/5 · existing arxiv: {len(existing_recs)} records")

    out_path = HERE / "data" / "high_density" / "arxiv" / "passages.jsonl"
    new_recs = list(existing_recs)
    new_count = 0
    for i, (cat, n) in enumerate(CATEGORIES):
        if i > 0:
            time.sleep(3.5)
        # fetch with a higher start offset to get different papers from before
        try:
            entries = fetch_one(cat, n, start=300)
        except Exception as exc:
            log(f"step PHASE1/5 · arxiv ERROR {cat}: {exc}")
            continue
        kept_here = 0
        for e in entries:
            cid = f"arxiv_{e['arxiv_id'].rsplit('/',1)[-1]}"
            if cid in existing:
                continue
            existing.add(cid)
            rec = {
                "corpus_id": cid,
                "register": "arxiv_abstract",
                "bucket": "high_density",
                "category": e["category"],
                "title": e["title"],
                "published": e["published"],
                "text": e["abstract"],
            }
            new_recs.append(rec)
            new_count += 1
            kept_here += 1
        log(f"step PHASE1/5 · {cat}: +{kept_here} new (total {len(new_recs)})")
    with out_path.open("w", encoding="utf-8") as f:
        for r in new_recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    log(f"step PHASE1/5 · arxiv expansion done · total={len(new_recs)} "
        f"(added {new_count} new)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
