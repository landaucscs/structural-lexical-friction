"""Fetch LogiQA passages via HuggingFace datasets.

LogiQA is a multi-choice logical reasoning dataset translated from China's
civil-servant exam.  Each item has a 'context' (passage), 'question', and
4 'options'.  We extract only the 'context' field.

Source: Liu et al. (2020), "LogiQA: A Challenge Dataset for Machine Reading
Comprehension with Logical Reasoning", IJCAI-PRICAI 2020 (arXiv:2007.08124)

This forms part of the "High-Stakes Academic Assessment Register" (HSAAR)
together with the CSAT passages.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import re
import sys
from pathlib import Path

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


import requests

URLS = [
    ("Train.txt",
     "https://raw.githubusercontent.com/lgw863/LogiQA-dataset/master/Train.txt"),
    ("Dev.txt",
     "https://raw.githubusercontent.com/lgw863/LogiQA-dataset/master/Eval.txt"),
    ("Test.txt",
     "https://raw.githubusercontent.com/lgw863/LogiQA-dataset/master/Test.txt"),
]


def parse_logiqa_block(text: str) -> list[str]:
    """Yield the context (2nd non-empty line) of each 5-line block."""
    lines = text.split("\n")
    contexts = []
    i = 0
    n = len(lines)
    while i < n:
        # find next answer letter line
        while i < n and not (lines[i].strip() and len(lines[i].strip()) == 1
                              and lines[i].strip().lower() in {"a","b","c","d"}):
            i += 1
        if i + 1 >= n:
            break
        ans = lines[i].strip()
        i += 1
        # next non-empty line is the context
        while i < n and not lines[i].strip():
            i += 1
        if i >= n:
            break
        context = lines[i].strip()
        # context can span multiple lines until question line; collect until we
        # see a line that looks like a question
        ctx_parts = [context]
        i += 1
        while i < n and lines[i].strip() and not lines[i].strip().endswith("?"):
            # only treat as continuation if not an option-style line
            s = lines[i].strip()
            if re.match(r"^[A-D]\.", s):
                break
            ctx_parts.append(s)
            i += 1
        full_ctx = " ".join(ctx_parts)
        full_ctx = re.sub(r"\s+", " ", full_ctx).strip()
        if full_ctx:
            contexts.append(full_ctx)
    return contexts


def main() -> int:
    log("step REV2/A2 · fetching LogiQA via GitHub raw")
    all_ctx = []
    for fname, url in URLS:
        try:
            r = requests.get(url, timeout=60)
            if r.status_code != 200:
                log(f"step REV2/A2 · {fname} HTTP {r.status_code} — skip")
                continue
            ctxs = parse_logiqa_block(r.text)
            log(f"step REV2/A2 · {fname}: parsed {len(ctxs)} contexts")
            all_ctx.extend(ctxs)
        except Exception as exc:
            log(f"step REV2/A2 · {fname} ERROR: {exc}")
    log(f"step REV2/A2 · total parsed: {len(all_ctx)}")

    out_dir = HERE / "data" / "high_density" / "logiqa"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "passages.jsonl"
    kept = 0
    seen_texts = set()
    with out.open("w", encoding="utf-8") as f:
        for i, context in enumerate(all_ctx):
            wc = len(context.split())
            if wc < 60 or wc > 350:
                continue
            ascii_ratio = sum(1 for c in context if ord(c) < 128) / max(1, len(context))
            if ascii_ratio < 0.95:
                continue
            if context in seen_texts:
                continue
            seen_texts.add(context)
            rec = {
                "corpus_id": f"logiqa_{i}",
                "register": "logiqa",
                "bucket": "high_density",
                "source": ("LogiQA (Liu et al. 2020, IJCAI-PRICAI; "
                           "arXiv:2007.08124): item " + str(i)),
                "text": context,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            kept += 1
    log(f"step REV2/A2 · LogiQA kept={kept} after filtering")
    return 0


if __name__ == "__main__":
    sys.exit(main())
