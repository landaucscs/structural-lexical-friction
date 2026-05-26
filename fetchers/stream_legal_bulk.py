"""Stream the CourtListener bulk opinions CSV from public S3, decompress on
the fly, parse with `csv.reader`, and stop once we have N valid opinions.

Target: ~2,500 opinions with substantive plain_text (>= 150 words after
cleaning).  Output: data/high_density/legal/passages_bulk.jsonl
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


# Court opinion plain_text fields can run to hundreds of KB.  Raise the csv
# module's per-field cap to handle that.
csv.field_size_limit(50_000_000)


HERE = Path(__file__).resolve().parent.parent
PROGRESS_LOG = HERE / "progress.log"


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              line_buffering=True)


def log(label: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {label}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# Most recent quarterly snapshot
URL = ("https://com-courtlistener-storage.s3.amazonaws.com/"
       "bulk-data/opinions-2026-03-31.csv.bz2")
TARGET = 2500
WC_MIN = 200
WC_KEEP = 400  # truncate each opinion to this many words


def clean_opinion_text(raw: str) -> str:
    if not raw:
        return ""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{2,}", "\n\n", text)
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    body_paras: list[str] = []
    started = False
    for p in paras:
        words = p.split()
        if not started:
            if len(words) >= 30 and not p.isupper():
                started = True
            else:
                continue
        body_paras.append(p)
        if sum(len(bp.split()) for bp in body_paras) >= 600:
            break
    body = " ".join(body_paras)
    body = re.sub(r"\s+", " ", body).strip()
    words = body.split()
    if len(words) > WC_KEEP:
        words = words[:WC_KEEP]
    return " ".join(words)


def main() -> int:
    log(f"step EXPAND/1 · stream bulk opinions · target {TARGET}")
    log(f"step EXPAND/1 · source {URL}")
    out = HERE / "data" / "high_density" / "legal" / "passages_bulk.jsonl"
    fout = out.open("w", encoding="utf-8")

    decompressor = bz2.BZ2Decompressor()
    text_buffer = ""
    leftover = b""
    n_kept = 0
    n_seen = 0
    n_empty = 0
    n_short = 0
    bytes_read = 0
    start_t = time.time()

    # Stream the file
    with requests.get(URL, stream=True, timeout=120) as r:
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
            if not chunk:
                continue
            bytes_read += len(chunk)
            try:
                decompressed = decompressor.decompress(chunk)
            except Exception as exc:
                log(f"step EXPAND/1 · decompress error: {exc}")
                continue
            if not decompressed:
                continue
            try:
                text_buffer += decompressed.decode("utf-8")
            except UnicodeDecodeError:
                text_buffer += decompressed.decode("utf-8", errors="replace")

            # Parse complete CSV rows out of text_buffer.  Because plain_text
            # fields can contain newlines inside quoted strings, we use the
            # csv module on the buffered text and only consume bytes up to
            # the last complete row.
            #
            # We use the standard trick: scan forward through quoted state to
            # find the last line that ends OUTSIDE a quoted field.
            in_quotes = False
            last_safe_end = 0
            i = 0
            buf = text_buffer
            n = len(buf)
            while i < n:
                ch = buf[i]
                if ch == '"':
                    # toggle, with handling of escaped doubled-quote ""
                    if in_quotes and i + 1 < n and buf[i + 1] == '"':
                        i += 2
                        continue
                    in_quotes = not in_quotes
                elif ch == "\n" and not in_quotes:
                    last_safe_end = i + 1
                i += 1

            if last_safe_end == 0:
                continue
            complete = buf[:last_safe_end]
            text_buffer = buf[last_safe_end:]

            # Parse complete chunk
            reader = csv.reader(io.StringIO(complete))
            for row in reader:
                if not row:
                    continue
                # Skip header row if it appears (only once at start)
                if row and row[0] == "id":
                    continue
                if len(row) < 12:
                    continue
                n_seen += 1
                plain = row[11] if len(row) > 11 else ""
                cluster_id = row[-1] if len(row) >= 1 else ""
                op_id = row[0]
                if not plain or len(plain.strip()) < 50:
                    n_empty += 1
                    continue
                # ASCII filter
                if plain:
                    ratio = sum(1 for c in plain if ord(c) < 128) / max(1, len(plain))
                    if ratio < 0.92:
                        continue
                cleaned = clean_opinion_text(plain)
                wc = len(cleaned.split())
                if wc < WC_MIN:
                    n_short += 1
                    continue
                rec = {
                    "corpus_id": f"cl_bulk_{op_id}",
                    "register": "judicial_opinion",
                    "bucket": "high_density",
                    "court": "various_federal",
                    "opinion_id": op_id,
                    "cluster_id": cluster_id,
                    "text": cleaned,
                }
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_kept += 1
                if n_kept % 100 == 0:
                    elapsed = time.time() - start_t
                    log(f"step EXPAND/1 · kept={n_kept} seen={n_seen} "
                        f"empty={n_empty} short={n_short} "
                        f"bytes_streamed={bytes_read//1024//1024}MB "
                        f"elapsed={elapsed:.0f}s")
                if n_kept >= TARGET:
                    fout.close()
                    log(f"step EXPAND/1 · TARGET REACHED · kept={n_kept} "
                        f"seen={n_seen} bytes={bytes_read//1024//1024}MB "
                        f"elapsed={time.time()-start_t:.0f}s")
                    return 0

    fout.close()
    log(f"step EXPAND/1 · stream ended · kept={n_kept} seen={n_seen} "
        f"bytes={bytes_read//1024//1024}MB elapsed={time.time()-start_t:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
