"""Fetch OneStopEnglish ELE + INT levels from the official GitHub repo
(Vajjala & Lucic 2018, EMNLP BEA-13).
Repo: https://github.com/nishkalavallabhi/OneStopEnglishCorpus
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


REPO = "nishkalavallabhi/OneStopEnglishCorpus"
BRANCH = "master"
LEVELS = [("Texts-SeparatedByReadingLevel/Ele-Txt", "ELE"),
          ("Texts-SeparatedByReadingLevel/Int-Txt", "INT")]
# (we exclude Adv per project decision)


def list_dir(path: str) -> list[str]:
    url = f"https://api.github.com/repos/{REPO}/contents/{path}?ref={BRANCH}"
    r = requests.get(url, timeout=30,
                     headers={"User-Agent": "Manuscript/2.0",
                               "Accept": "application/vnd.github.v3+json"})
    if r.status_code != 200:
        log(f"step PHASE1/4 · github list FAIL {path}: {r.status_code} {r.text[:200]}")
        return []
    return [item["name"] for item in r.json() if item["type"] == "file"]


def fetch_file(path: str, name: str) -> str:
    url = (f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{path}/{name}")
    r = requests.get(url, timeout=30, headers={"User-Agent": "Manuscript/2.0"})
    if r.status_code != 200:
        return ""
    return r.text


def main() -> int:
    log("step PHASE1/4 · OneStopEnglish ELE+INT fetch begin")
    out_path = HERE / "data" / "baseline" / "onestop" / "passages.jsonl"
    kept = 0
    with out_path.open("w", encoding="utf-8") as fout:
        for path, level in LEVELS:
            files = list_dir(path)
            log(f"step PHASE1/4 · listed {level}: {len(files)} files")
            for fname in files:
                if not fname.lower().endswith(".txt"):
                    continue
                text = fetch_file(path, fname)
                if not text:
                    continue
                # clean BOM, normalize whitespace
                text = text.replace("﻿", "")
                paragraphs = [p.strip() for p in
                              re.split(r"\n\s*\n", text) if p.strip()]
                # chunk into ~150-400w pieces
                chunk = []
                chunk_wc = 0
                chunk_idx = 0
                for para in paragraphs:
                    para = re.sub(r"\s+", " ", para).strip()
                    wc = len(para.split())
                    if wc < 5:
                        continue
                    chunk.append(para)
                    chunk_wc += wc
                    if 150 <= chunk_wc <= 400:
                        text_out = " ".join(chunk)
                        rec = {
                            "corpus_id": f"onestop_{level}_{fname.rsplit('.',1)[0]}_c{chunk_idx}",
                            "register": f"onestop_{level.lower()}",
                            "bucket": "baseline",
                            "level": level,
                            "source_file": fname,
                            "source": ("OneStopEnglish (Vajjala & Lucic 2018, "
                                        "EMNLP BEA-13): " + fname),
                            "text": text_out,
                        }
                        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        kept += 1
                        chunk_idx += 1
                        chunk = []
                        chunk_wc = 0
                    elif chunk_wc > 400:
                        # emit previous content if substantial
                        if chunk_wc - wc >= 150:
                            text_out = " ".join(chunk[:-1])
                            rec = {
                                "corpus_id": f"onestop_{level}_{fname.rsplit('.',1)[0]}_c{chunk_idx}",
                                "register": f"onestop_{level.lower()}",
                                "bucket": "baseline",
                                "level": level,
                                "source_file": fname,
                                "source": ("OneStopEnglish (Vajjala & Lucic 2018, "
                                            "EMNLP BEA-13): " + fname),
                                "text": text_out,
                            }
                            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                            kept += 1
                            chunk_idx += 1
                        chunk = [para]
                        chunk_wc = wc
                # remainder: emit if 150+ words
                if chunk_wc >= 150:
                    text_out = " ".join(chunk)
                    rec = {
                        "corpus_id": f"onestop_{level}_{fname.rsplit('.',1)[0]}_c{chunk_idx}",
                        "register": f"onestop_{level.lower()}",
                        "bucket": "baseline",
                        "level": level,
                        "source_file": fname,
                        "source": ("OneStopEnglish (Vajjala & Lucic 2018, "
                                    "EMNLP BEA-13): " + fname),
                        "text": text_out,
                    }
                    fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    kept += 1
                if kept % 100 == 0 and kept > 0:
                    log(f"step PHASE1/4 · running={kept}")
                time.sleep(0.15)  # be polite to GitHub
    log(f"step PHASE1/4 · onestop done · kept {kept}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
