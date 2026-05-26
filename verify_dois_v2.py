"""Verify expanded citation list (~18 candidates) via CrossRef API."""
from __future__ import annotations

import datetime as _dt
import io
import json
import sys
from pathlib import Path

import requests


HERE = Path(__file__).resolve().parent
PROGRESS_LOG = HERE / "progress.log"


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              line_buffering=True)


def log(label: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {label}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


CANDIDATES = [
    # Foundational readability
    {"key": "flesch_1948",  "doi": "10.1037/h0057532",
     "authors_substr": ["Flesch"], "year": 1948,
     "title_substr": "readability", "journal_substr": "applied psychology"},
    {"key": "klare_1974",   "doi": "10.2307/747086",
     "authors_substr": ["Klare"], "year": 1974,
     "title_substr": "readability", "journal_substr": "reading research"},
    {"key": "dubay_2007",   "doi": "10.4135/9781452225999.n45",
     "authors_substr": ["DuBay"], "year": 2007,
     "title_substr": "readability", "journal_substr": "encyclopedia"},
    # Cognitive load & comprehension
    {"key": "kintsch_1988", "doi": "10.1037/0033-295X.95.2.163",
     "authors_substr": ["Kintsch"], "year": 1988,
     "title_substr": "discourse comprehension",
     "journal_substr": "psychological review"},
    {"key": "sweller_1988", "doi": "10.1207/s15516709cog1202_4",
     "authors_substr": ["Sweller"], "year": 1988,
     "title_substr": "cognitive load",
     "journal_substr": "cognitive science"},
    {"key": "just_carpenter_1992",
     "doi": "10.1037/0033-295X.99.1.122",
     "authors_substr": ["Just", "Carpenter"], "year": 1992,
     "title_substr": "capacity theory",
     "journal_substr": "psychological review"},
    {"key": "mcnamara_1996",
     "doi": "10.1207/s1532690xci1401_1",
     "authors_substr": ["McNamara", "Kintsch"], "year": 1996,
     "title_substr": "good texts",
     "journal_substr": "cognition and instruction"},
    # Syntactic load
    {"key": "gibson_1998",  "doi": "10.1016/S0010-0277(98)00034-1",
     "authors_substr": ["Gibson"], "year": 1998,
     "title_substr": "linguistic complexity",
     "journal_substr": "cognition"},
    {"key": "rayner_1998",  "doi": "10.1037/0033-2909.124.3.372",
     "authors_substr": ["Rayner"], "year": 1998,
     "title_substr": "eye movements",
     "journal_substr": "psychological bulletin"},
    # Computational complexity tools
    {"key": "graesser_2004_cohmetrix",
     "doi": "10.3758/BF03195564",
     "authors_substr": ["Graesser", "McNamara"], "year": 2004,
     "title_substr": "coh-metrix",
     "journal_substr": "behavior research methods"},
    {"key": "lu_2010",      "doi": "10.1075/ijcl.15.4.02lu",
     "authors_substr": ["Lu"], "year": 2010,
     "title_substr": "syntactic complexity",
     "journal_substr": "corpus linguistics"},
    {"key": "kyle_2018",    "doi": "10.1111/modl.12468",
     "authors_substr": ["Kyle", "Crossley"], "year": 2018,
     "title_substr": "syntactic complexity",
     "journal_substr": "modern language"},
    {"key": "crossley_2019",
     "doi": "10.1111/1467-9817.12283",
     "authors_substr": ["Crossley"], "year": 2019,
     "title_substr": "readability",
     "journal_substr": "research in reading"},
    # Statistical / methodology
    {"key": "barr_2013",    "doi": "10.1016/j.jml.2012.11.001",
     "authors_substr": ["Barr", "Levy"], "year": 2013,
     "title_substr": "random effects",
     "journal_substr": "memory and language"},
    # NLP / corpora
    {"key": "honnibal_2017",
     "doi": "10.5281/zenodo.1212303",
     "authors_substr": ["Honnibal", "Montani"], "year": 2017,
     "title_substr": "spacy",
     "journal_substr": ""},
    {"key": "lai_race_2017",
     "doi": "10.18653/v1/D17-1082",
     "authors_substr": ["Lai", "Xie"], "year": 2017,
     "title_substr": "race",
     "journal_substr": "emnlp"},
    {"key": "vajjala_2014",
     "doi": "10.3115/v1/W14-1804",
     "authors_substr": ["Vajjala"], "year": 2014,
     "title_substr": "readability",
     "journal_substr": ""},
    {"key": "schwarm_ostendorf_2005",
     "doi": "10.3115/1219840.1219888",
     "authors_substr": ["Schwarm"], "year": 2005,
     "title_substr": "reading level",
     "journal_substr": ""},
]


def fetch_crossref(doi: str) -> dict | None:
    url = f"https://api.crossref.org/works/{doi}"
    headers = {"User-Agent": "Manuscript/2.0"}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            return None
        return r.json().get("message")
    except Exception as exc:
        log(f"verify · crossref error for {doi}: {exc}")
        return None


def verify(entry: dict) -> dict:
    doi = entry.get("doi")
    res = {
        "key": entry["key"], "doi": doi,
        "expected_year": entry["year"],
        "expected_authors": entry["authors_substr"],
        "expected_title": entry["title_substr"],
        "expected_journal": entry["journal_substr"],
        "verdict": "PENDING", "notes": "",
        "crossref_url": f"https://api.crossref.org/works/{doi}",
        "doi_url": f"https://doi.org/{doi}",
        "scholar_url": ("https://scholar.google.com/scholar?q="
                        f"{entry['title_substr']}+{entry['authors_substr'][0]}"),
    }
    msg = fetch_crossref(doi)
    if not msg:
        res["verdict"] = "FAIL_RESOLVE"
        return res
    title = " ".join(msg.get("title") or [""]).lower()
    container = " ".join(msg.get("container-title") or [""]).lower()
    if not container:
        container = (msg.get("event") or {}).get("name", "").lower()
    authors = [f"{a.get('family','')} {a.get('given','')}".strip()
               for a in (msg.get("author") or [])]
    issued = msg.get("issued", {}).get("date-parts", [[None]])
    year = issued[0][0] if issued and issued[0] else None
    res["actual_title"] = title.strip()[:200]
    res["actual_authors"] = authors
    res["actual_year"] = year
    res["actual_journal"] = container.strip()[:160]

    author_ok = all(any(sub.lower() in a.lower() for a in authors)
                    for sub in entry["authors_substr"])
    title_ok = entry["title_substr"].lower() in title
    journal_ok = (entry["journal_substr"] == "" or
                  entry["journal_substr"].lower() in container)
    # tolerate ±1 year for online-first/print mismatch
    year_ok = (year is not None and
               abs(year - entry["year"]) <= 1)
    metadata_match = author_ok and title_ok and journal_ok and year_ok
    res["verdict"] = "PASS" if metadata_match else "FAIL_METADATA"
    if not author_ok:
        res["notes"] += "; author mismatch"
    if not title_ok:
        res["notes"] += "; title mismatch"
    if not journal_ok:
        res["notes"] += f"; journal mismatch (got '{container[:60]}')"
    if not year_ok:
        res["notes"] += f"; year mismatch (got {year})"
    res["notes"] = res["notes"].lstrip("; ")
    return res


def main() -> int:
    log(f"step 10/13 · verifying {len(CANDIDATES)} citations via CrossRef")
    results = [verify(c) for c in CANDIDATES]
    pass_n = sum(1 for r in results if r["verdict"] == "PASS")
    log(f"step 10/13 · {pass_n}/{len(results)} PASS")
    for r in results:
        log(f"step 10/13 · {r['key']} -> {r['verdict']} {r['notes'][:60]}")
    md = ["# DOI Verification Log v2",
          "",
          f"Generated: {_dt.datetime.now().isoformat(timespec='seconds')}",
          "",
          f"Result: **{pass_n} of {len(results)} PASS**",
          "",
          "Year tolerance: ±1 year (online-first/print mismatch).",
          "",
          "| Key | DOI | Verdict | CrossRef | DOI.org | Scholar | Notes |",
          "|-----|-----|---------|----------|---------|---------|-------|"]
    for r in results:
        md.append(f"| `{r['key']}` | `{r['doi']}` | **{r['verdict']}** "
                  f"| {r['crossref_url']} | {r['doi_url']} "
                  f"| {r['scholar_url']} | {r['notes'] or '(none)'} |")
    (HERE / "doi_verification_log.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8")
    (HERE / "verified_citations_v2.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8")
    log("step 10/13 · wrote doi_verification_log.md and verified_citations_v2.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
