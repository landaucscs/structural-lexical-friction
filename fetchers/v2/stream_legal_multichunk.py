"""Re-stream the CourtListener bulk opinions CSV and produce sentence-aligned
multi-chunk passages from each opinion.

For each opinion:
  1. Drop caption / docket-header lines (heuristic: short ALL-CAPS lines, lines
     matching "v\\.", "No\\.\\s*\\d", "UNITED STATES", footnote markers).
  2. Sentence-segment with regex (lightweight, avoids spaCy overhead at this
     stage; spaCy will be applied later in the metrics pipeline).
  3. Build successive chunks of target_words ∈ [320, 460] by accumulating
     sentences until the budget is reached.
  4. Keep up to MAX_CHUNKS_PER_OPINION non-overlapping chunks per opinion.
  5. Stop once TOTAL target is reached.

Target ~5,000 total chunks.
"""
from __future__ import annotations

import bz2
import csv
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
csv.field_size_limit(50_000_000)


def log(label: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {label}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


URL = ("https://com-courtlistener-storage.s3.amazonaws.com/"
       "bulk-data/opinions-2026-03-31.csv.bz2")
TARGET_TOTAL = 5000
MIN_CHUNK_WC = 320
MAX_CHUNK_WC = 460
MAX_CHUNKS_PER_OPINION = 3

# Caption/header line heuristics (case-insensitive substring tests on the line)
HEADER_PATTERNS = [
    r"^\s*[IVX]+\.\s*$",                  # roman section heads
    r"^\s*[IVX]+\.\s+[A-Z\s]{2,30}\s*$",  # I. ANALYSIS
    r"^\s*\d+\.\s*$",                     # 1.
    r"^\s*FOOTNOTES?\s*$",
    r"^\s*BACKGROUND\s*$",
    r"^\s*DISCUSSION\s*$",
    r"^\s*ANALYSIS\s*$",
    r"^\s*CONCLUSION\s*$",
    r"^\s*OPINION\s*$",
    r"^\s*UNITED STATES",
    r"^\s*No\.\s*\d",
    r"v\.\s+[A-Z]",
    r"^\s*Appeal from",
    r"^\s*BEFORE",
    r"^\s*PER CURIAM",
]
HEADER_RES = [re.compile(p, re.IGNORECASE) for p in HEADER_PATTERNS]


SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")


def clean_lines(raw: str) -> str:
    """Return cleaned opinion body with caption/header lines removed."""
    if not raw:
        return ""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    # remove citation page-break artifacts like "Page 357" or "*371"
    text = re.sub(r"\n\s*\*\d+\s*\n", "\n", text)
    text = re.sub(r"\n\s*Page\s+\d+\s*\n", "\n", text, flags=re.IGNORECASE)
    # split lines, drop headers, drop very short lines, drop all-caps lines
    out_lines = []
    started_body = False
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            out_lines.append("")
            continue
        is_header = False
        for pat in HEADER_RES:
            if pat.search(s):
                is_header = True
                break
        if is_header:
            continue
        # all-caps short lines = headers/captions
        if len(s) < 80 and s == s.upper() and any(c.isalpha() for c in s):
            continue
        if not started_body:
            # require first kept line to look substantive
            if len(s.split()) >= 15 and not s.isupper():
                started_body = True
            else:
                continue
        out_lines.append(s)
    body = " ".join(out_lines)
    body = re.sub(r"\s+", " ", body).strip()
    return body


def chunk_opinion(body: str, n_chunks_max: int) -> list[str]:
    """Split body into up to n_chunks_max non-overlapping chunks within the
    target word range, each starting and ending on a sentence boundary."""
    if not body:
        return []
    sents = SENT_SPLIT_RE.split(body)
    # filter near-empty sentences
    sents = [s.strip() for s in sents if s and len(s.strip()) > 5]
    chunks = []
    buf = []
    buf_wc = 0
    for s in sents:
        sw = len(s.split())
        if sw < 4 or sw > 200:
            continue
        if buf_wc + sw > MAX_CHUNK_WC and buf_wc >= MIN_CHUNK_WC:
            # emit current chunk
            chunks.append(" ".join(buf))
            buf = [s]
            buf_wc = sw
            if len(chunks) >= n_chunks_max:
                return chunks
        else:
            buf.append(s)
            buf_wc += sw
    if buf and buf_wc >= MIN_CHUNK_WC and len(chunks) < n_chunks_max:
        chunks.append(" ".join(buf))
    return chunks


def main() -> int:
    log(f"step PHASE1/6 · legal multi-chunk stream begin · target {TARGET_TOTAL}")
    out_path = HERE / "data" / "high_density" / "legal_v2" / "passages.jsonl"
    fout = out_path.open("w", encoding="utf-8")

    decompressor = bz2.BZ2Decompressor()
    text_buffer = ""
    n_kept = 0
    n_opinions_seen = 0
    n_opinions_kept = 0
    n_empty = 0
    n_short = 0
    bytes_read = 0
    start_t = time.time()
    seen_text_hashes: set[int] = set()

    with requests.get(URL, stream=True, timeout=120) as r:
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            bytes_read += len(chunk)
            try:
                decompressed = decompressor.decompress(chunk)
            except Exception as exc:
                log(f"step PHASE1/6 · decompress err: {exc}")
                continue
            if not decompressed:
                continue
            try:
                text_buffer += decompressed.decode("utf-8")
            except UnicodeDecodeError:
                text_buffer += decompressed.decode("utf-8", errors="replace")

            # find last safe row boundary outside quoted strings
            in_quotes = False
            last_safe = 0
            buf = text_buffer
            i = 0
            n = len(buf)
            while i < n:
                ch = buf[i]
                if ch == '"':
                    if in_quotes and i + 1 < n and buf[i + 1] == '"':
                        i += 2
                        continue
                    in_quotes = not in_quotes
                elif ch == "\n" and not in_quotes:
                    last_safe = i + 1
                i += 1

            if last_safe == 0:
                continue
            complete = buf[:last_safe]
            text_buffer = buf[last_safe:]

            reader = csv.reader(io.StringIO(complete))
            for row in reader:
                if not row or row[0] == "id":
                    continue
                if len(row) < 12:
                    continue
                n_opinions_seen += 1
                plain = row[11] if len(row) > 11 else ""
                op_id = row[0]
                cluster_id = row[-1] if len(row) >= 1 else ""
                if not plain or len(plain.strip()) < 200:
                    n_empty += 1
                    continue
                ratio = sum(1 for c in plain if ord(c) < 128) / max(1, len(plain))
                if ratio < 0.92:
                    continue
                body = clean_lines(plain)
                if len(body.split()) < MIN_CHUNK_WC:
                    n_short += 1
                    continue
                chunks = chunk_opinion(body, MAX_CHUNKS_PER_OPINION)
                if not chunks:
                    n_short += 1
                    continue
                n_opinions_kept += 1
                for ci, ctxt in enumerate(chunks):
                    th = hash(ctxt[:200])
                    if th in seen_text_hashes:
                        continue
                    seen_text_hashes.add(th)
                    rec = {
                        "corpus_id": f"cl_v2_{op_id}_c{ci}",
                        "register": "judicial_opinion",
                        "bucket": "high_density",
                        "court": "various_federal",
                        "opinion_id": op_id,
                        "cluster_id": cluster_id,
                        "chunk_index": ci,
                        "text": ctxt,
                    }
                    fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n_kept += 1
                    if n_kept % 200 == 0:
                        el = time.time() - start_t
                        log(f"step PHASE1/6 · kept={n_kept} chunks "
                            f"from {n_opinions_kept} opinions · "
                            f"bytes={bytes_read//1024//1024}MB "
                            f"el={el:.0f}s")
                    if n_kept >= TARGET_TOTAL:
                        fout.close()
                        log(f"step PHASE1/6 · TARGET REACHED · {n_kept} chunks "
                            f"from {n_opinions_kept} opinions · "
                            f"opinions seen={n_opinions_seen} · "
                            f"bytes={bytes_read//1024//1024}MB · "
                            f"el={time.time()-start_t:.0f}s")
                        return 0

    fout.close()
    log(f"step PHASE1/6 · end · kept {n_kept} chunks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
