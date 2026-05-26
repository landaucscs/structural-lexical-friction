"""Fetch federal judicial opinions from CourtListener API v4.

Strategy:
    1. Use /search/?type=o&court={court} to retrieve opinion IDs (cheap).
    2. For each opinion ID, GET /opinions/{id}/ to retrieve plain_text.
    3. Clean the plain_text (strip header / caption, keep first ~400 words).

Rate-limit discipline:
    - Authenticated users: 5 req/min, 50/hour, 125/day.
    - We pace at 12.5 seconds between calls (= 4.8/min, strictly under cap).
    - Target ~100 opinions total ≈ 105 API calls ≈ 22 min wall-clock.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sys
import time
from pathlib import Path

import requests


HERE = Path(__file__).resolve().parent.parent
PROGRESS_LOG = HERE / "progress.log"

import os

TOKEN = os.environ.get("COURTLISTENER_TOKEN", "")
if not TOKEN:
    raise SystemExit(
        "Set the COURTLISTENER_TOKEN environment variable to a CourtListener "
        "API token (register at https://www.courtlistener.com to obtain one)."
    )
HEADERS = {
    "Authorization": f"Token {TOKEN}",
    "User-Agent": "structural-lexical-friction/1.0",
}

TARGET_COURTS = [
    ("scotus", 25),   # U.S. Supreme Court
    ("ca2",    25),   # 2nd Circuit
    ("ca9",    25),   # 9th Circuit
    ("cadc",   15),   # DC Circuit
    ("ca7",    15),   # 7th Circuit
]
RATE_DELAY = 12.5  # seconds between API calls


def log(label: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {label}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def clean_opinion_text(raw: str) -> str:
    """Strip headers (court name, caption, docket number lines) and keep the
    first ~400 words of substantive prose."""
    if not raw:
        return ""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{2,}", "\n\n", text)
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    body_paras = []
    started = False
    for p in paras:
        words = p.split()
        if not started:
            # heuristic: substantive paragraph >= 30 words, not all caps
            if len(words) >= 30 and not p.isupper():
                started = True
            else:
                continue
        body_paras.append(p)
        total_words = sum(len(bp.split()) for bp in body_paras)
        if total_words >= 600:
            break
    body = " ".join(body_paras)
    body = re.sub(r"\s+", " ", body).strip()
    words = body.split()
    if len(words) > 400:
        words = words[:400]
    return " ".join(words)


def safe_get(url: str, attempts: int = 3) -> dict | None:
    last_status = None
    for tries in range(attempts):
        try:
            r = requests.get(url, headers=HEADERS, timeout=45)
            last_status = r.status_code
            if r.status_code == 429:
                log(f"step 4/13 · 429 rate-limit · sleeping 75s")
                time.sleep(75)
                continue
            if r.status_code == 200:
                return r.json()
            log(f"step 4/13 · HTTP {r.status_code} · body[:200]={r.text[:200]}")
            return None
        except Exception as exc:
            log(f"step 4/13 · request error (attempt {tries+1}/{attempts}): {exc}")
            time.sleep(20)
    log(f"step 4/13 · gave up after {attempts} attempts (last status {last_status})")
    return None


def fetch_court(court_id: str, target_n: int) -> list[dict]:
    log(f"step 4/13 · SEARCH court={court_id} target={target_n}")
    url = (
        "https://www.courtlistener.com/api/rest/v4/search/"
        f"?type=o&court={court_id}&order_by=dateFiled%20desc"
        f"&page_size=20"
    )
    out: list[dict] = []
    page = 1
    while len(out) < target_n and page <= 3:
        search_data = safe_get(url)
        if not search_data:
            return out
        results = search_data.get("results", [])
        opinion_ids = []
        for r in results:
            for op in r.get("opinions", []):
                opinion_ids.append({
                    "opinion_id": op.get("id"),
                    "case_name": r.get("caseName"),
                    "court": court_id,
                    "date_filed": r.get("dateFiled"),
                })
        log(f"step 4/13 · {court_id} page={page} · collected "
            f"{len(opinion_ids)} opinion ids")
        time.sleep(RATE_DELAY)
        for oid in opinion_ids:
            if len(out) >= target_n:
                break
            if not oid["opinion_id"]:
                continue
            op_url = ("https://www.courtlistener.com/api/rest/v4/opinions/"
                      f"{oid['opinion_id']}/")
            op = safe_get(op_url)
            if not op:
                continue
            raw = op.get("plain_text") or op.get("html_with_citations") or ""
            cleaned = clean_opinion_text(raw)
            wc = len(cleaned.split())
            if wc < 150:
                log(f"step 4/13 · {court_id} skip id={oid['opinion_id']} wc={wc}")
                time.sleep(RATE_DELAY)
                continue
            out.append({
                "corpus_id": f"cl_{court_id}_{oid['opinion_id']}",
                "register": "judicial_opinion",
                "bucket": "high_density",
                "court": court_id,
                "case_name": oid["case_name"],
                "date_filed": oid["date_filed"],
                "text": cleaned,
            })
            log(f"step 4/13 · {court_id} kept id={oid['opinion_id']} wc={wc} "
                f"(running total {len(out)})")
            time.sleep(RATE_DELAY)
        page += 1
        next_url = search_data.get("next")
        if next_url:
            url = next_url
        else:
            break
    return out


def main() -> int:
    log(f"step 4/13 · courtlistener fetch begin · paced at {RATE_DELAY}s")
    out_path = HERE / "data" / "high_density" / "legal" / "passages.jsonl"
    total = 0
    by_court: dict[str, int] = {}
    with out_path.open("w", encoding="utf-8") as fout:
        for court_id, target_n in TARGET_COURTS:
            recs = fetch_court(court_id, target_n)
            for r in recs:
                fout.write(json.dumps(r, ensure_ascii=False) + "\n")
            total += len(recs)
            by_court[court_id] = len(recs)
            log(f"step 4/13 · {court_id} complete · kept={len(recs)} "
                f"(running total {total})")
    log(f"step 4/13 · courtlistener complete · total={total} · by_court={by_court}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
