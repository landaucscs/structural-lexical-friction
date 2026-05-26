"""Fetch arXiv abstracts across multiple categories via the public API.

API: http://export.arxiv.org/api/query
Spec: https://info.arxiv.org/help/api/user-manual.html

We respect the published rate-limit guidance (one request every 3 seconds).
A batch query of 300 results is permitted in a single call.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sys
import time
from pathlib import Path

import requests
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent.parent
PROGRESS_LOG = HERE / "progress.log"


def log(label: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {label}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


CATEGORIES = [
    ("cs.CL",     300),
    ("q-bio",     150),
    ("physics",   150),
    ("math",      100),
    ("econ",      100),
]

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def fetch_one(category: str, n: int) -> list[dict]:
    url = (
        "http://export.arxiv.org/api/query?"
        f"search_query=cat:{category}*"
        f"&start=0&max_results={n}"
        "&sortBy=submittedDate&sortOrder=descending"
    )
    log(f"step 3/13 · arxiv GET {category} n={n}")
    r = requests.get(url, timeout=60,
                     headers={"User-Agent": "Manuscript/1.0"})
    r.raise_for_status()
    root = ET.fromstring(r.text)
    out: list[dict] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title_el = entry.find("atom:title", ATOM_NS)
        sum_el = entry.find("atom:summary", ATOM_NS)
        id_el = entry.find("atom:id", ATOM_NS)
        pub_el = entry.find("atom:published", ATOM_NS)
        if title_el is None or sum_el is None or id_el is None:
            continue
        abstract = (sum_el.text or "").strip()
        # squash whitespace
        abstract = re.sub(r"\s+", " ", abstract)
        if len(abstract.split()) < 50:
            continue
        # crude non-English filter: must contain mostly ASCII
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
    log("step 3/13 · arxiv fetch begin · 5 categories")
    out_path = HERE / "data" / "high_density" / "arxiv" / "passages.jsonl"
    total = 0
    by_cat: dict[str, int] = {}
    with out_path.open("w", encoding="utf-8") as fout:
        for i, (cat, n) in enumerate(CATEGORIES):
            if i > 0:
                time.sleep(3.5)  # rate-limit politeness
            try:
                entries = fetch_one(cat, n)
            except Exception as exc:
                log(f"step 3/13 · arxiv ERROR {cat}: {exc}")
                continue
            for e in entries:
                rec = {
                    "corpus_id": f"arxiv_{e['arxiv_id'].rsplit('/',1)[-1]}",
                    "register": "arxiv_abstract",
                    "bucket": "high_density",
                    "category": e["category"],
                    "title": e["title"],
                    "published": e["published"],
                    "text": e["abstract"],
                }
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                total += 1
                by_cat[cat] = by_cat.get(cat, 0) + 1
            log(f"step 3/13 · {cat}: {len(entries)} abstracts kept "
                f"(running total {total})")
    log(f"step 3/13 · arxiv fetch complete · total={total} · by_cat={by_cat}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
