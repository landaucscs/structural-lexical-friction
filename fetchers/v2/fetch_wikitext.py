"""Fetch wikitext-103 via HuggingFace datasets and chunk into ~150-400w
passage records.  Filters Wikipedia headers (= Title =, == Section ==).

Source: Merity et al. (2016), "Pointer Sentinel Mixture Models", arXiv:1609.07843
HF dataset: salesforce/wikitext config wikitext-103-raw-v1
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


TARGET = 2000


def is_header_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    # WikiText format headers look like "= Title =" or "== Section ==" etc.
    if re.match(r"^=+\s.+\s=+$", s):
        return True
    return False


def main() -> int:
    log(f"step PHASE1/2 · wikitext-103 fetch · target {TARGET}")
    from datasets import load_dataset
    log("step PHASE1/2 · loading wikitext-103-raw-v1 (cache or download)")
    ds = load_dataset("salesforce/wikitext", "wikitext-103-raw-v1",
                      split="train", streaming=True)
    log("step PHASE1/2 · streaming records · grouping by article")

    out_path = HERE / "data" / "baseline" / "wikitext" / "passages.jsonl"
    fout = out_path.open("w", encoding="utf-8")

    # WikiText: each split is one long sequence with article boundaries
    # at lines like " = Article Title = " (with surrounding blank lines).
    # We accumulate lines between top-level headers.
    current_title = None
    current_paragraphs: list[str] = []
    kept = 0
    n_examples_seen = 0
    article_count = 0

    def emit_passages_from_article(title: str, paragraphs: list[str]) -> int:
        added = 0
        # combine paragraphs into chunks of 150..400 words
        chunk_lines: list[str] = []
        chunk_wc = 0
        nonlocal kept
        for para in paragraphs:
            para = re.sub(r"\s+", " ", para).strip()
            if not para:
                continue
            wc = len(para.split())
            if wc < 30:
                continue
            chunk_lines.append(para)
            chunk_wc += wc
            if 150 <= chunk_wc <= 400:
                text = " ".join(chunk_lines)
                rec = {
                    "corpus_id": f"wikitext_{abs(hash(title)) % 1_000_000}_{kept}",
                    "register": "wikitext_modern_encyclopedic",
                    "bucket": "baseline",
                    "source_title": title,
                    "source": (f"WikiText-103 (Merity et al. 2016, "
                                f"arXiv:1609.07843): {title}"),
                    "text": text,
                }
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                kept += 1
                added += 1
                chunk_lines = []
                chunk_wc = 0
                if kept >= TARGET:
                    return added
            elif chunk_wc > 400:
                # current chunk overshoots; emit it if we already had content
                if chunk_wc - wc >= 150:
                    text = " ".join(chunk_lines[:-1])
                    rec = {
                        "corpus_id": f"wikitext_{abs(hash(title)) % 1_000_000}_{kept}",
                        "register": "wikitext_modern_encyclopedic",
                        "bucket": "baseline",
                        "source_title": title,
                        "source": (f"WikiText-103 (Merity et al. 2016): {title}"),
                        "text": text,
                    }
                    fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    kept += 1
                    added += 1
                    chunk_lines = [chunk_lines[-1]]
                    chunk_wc = wc
                else:
                    chunk_lines = []
                    chunk_wc = 0
                if kept >= TARGET:
                    return added
        return added

    for ex in ds:
        n_examples_seen += 1
        line = ex["text"]
        if is_header_line(line):
            # top-level title looks like " = Foo = "
            m = re.match(r"^=\s+(.+?)\s+=$", line.strip())
            if m:
                # emit previous article
                if current_title and current_paragraphs:
                    emit_passages_from_article(current_title, current_paragraphs)
                    article_count += 1
                    if article_count % 50 == 0:
                        log(f"step PHASE1/2 · processed {article_count} articles · "
                            f"kept {kept} passages")
                current_title = m.group(1)
                current_paragraphs = []
            else:
                # sub-section header; treat as paragraph break
                current_paragraphs.append("")
        else:
            current_paragraphs.append(line)
        if kept >= TARGET:
            break
    if current_title and current_paragraphs and kept < TARGET:
        emit_passages_from_article(current_title, current_paragraphs)

    fout.close()
    log(f"step PHASE1/2 · wikitext done · kept {kept} passages "
        f"from {article_count}+ articles, examples_seen={n_examples_seen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
