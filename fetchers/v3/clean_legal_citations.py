"""Strip reporter and statutory citations from the legal sub-corpus.

Patterns removed:
  - Reporter citations: '410 F.3d 102', '545 U.S. 123', '123 S. Ct. 456'
  - Statutory: '28 U.S.C. § 1291', '42 U.S.C. § 1983'
  - Federal Rules: 'Fed. R. Civ. P. 12(b)(6)'
  - State citations: '123 N.Y.2d 456'
  - "Id." and "Ibid." style cross-references
  - Parenthetical citation packs: '(citing X, 123 U.S. 456 (1980))'

After cleaning, recompute all 17 indices with sm.  Output:
  data/high_density/legal_v2_clean/passages.jsonl
  data/unified_v2/corpus_clean.jsonl
  data/unified_v2/metrics_v2_sm_clean.csv
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


# Order matters: more specific first.
CITATION_PATTERNS = [
    # parenthetical citation pack with see/citing/quoting prefix
    re.compile(r"\(\s*(?:see|citing|quoting|accord|cf|but see|see also)[^)]*\)",
                re.IGNORECASE),
    # parenthetical that contains a reporter or section symbol
    re.compile(r"\((?:[^()]*\d+\s+(?:U\.?S\.?|F\.?\s?\d?[a-z]*|S\.?\s?Ct\.?|"
                r"N\.?[YE]\.?\d*|Cal\.?\s?\d*|Pa\.?\s?\d*)[^()]*)\)"),
    # Reporter citations: 410 F.3d 102, 545 U.S. 123, 123 S. Ct. 456
    re.compile(r"\b\d+\s+(?:U\.?\s?S\.?|F\.?\s?\d?[a-z]*|F\.?\s?Supp\.?\s?\d*|"
                r"S\.?\s?Ct\.?|L\.?\s?Ed\.?\s?\d*|"
                r"N\.?[YE]\.?\d*[a-z]*|Cal\.?\s?\d*[a-z]*|"
                r"Pa\.?\s?\d*|Tex\.?\s?\d*|Mass\.?\s?\d*)\s+"
                r"\d+(?:,\s*\d+)*(?:\s*\([^)]+\))?"),
    # Statutory: 28 U.S.C. § 1291; 42 U.S.C. §§ 1981-83
    re.compile(r"\b\d+\s*U\.?\s?S\.?\s?C\.?\s*§+\s*\d+[\w\-(),. ]*"),
    re.compile(r"\b\d+\s*C\.?\s?F\.?\s?R\.?\s*§+\s*[\d.]+[\w\-(),. ]*"),
    # Federal Rules of Civil Procedure
    re.compile(r"Fed\.?\s+R\.?\s+(?:Civ|Crim|App|Evid|Bankr)\.?\s+P\.?\s+"
                r"\d+[\w\-(),. ]*"),
    # pinpoint citations: "at 102", "at 102-04"
    re.compile(r",?\s*at\s+\d+(?:[-–]\d+)?(?:,\s*\d+)*\b"),
    # Id. / Ibid. cross-references
    re.compile(r"\bId\.?(?:\s+at\s+\d+(?:[-–]\d+)?)?", re.IGNORECASE),
    re.compile(r"\bIbid\.?", re.IGNORECASE),
    # supra and infra
    re.compile(r"\bsupra(?:\s+note\s+\d+)?", re.IGNORECASE),
    re.compile(r"\binfra(?:\s+note\s+\d+)?", re.IGNORECASE),
    # __ U.S. ___ slip-opinion style
    re.compile(r"\b\d+\s+U\.?\s?S\.?\s+\b_+\b"),
    # bare section reference: § 1291
    re.compile(r"§+\s*\d+(?:\.\d+)?(?:\([\w]+\))*"),
]

WHITESPACE_FIX = re.compile(r"\s+")
EMPTY_PARENS = re.compile(r"\(\s*[,;\s]*\s*\)")


def clean_citation(text: str) -> str:
    for pat in CITATION_PATTERNS:
        text = pat.sub(" ", text)
    text = EMPTY_PARENS.sub("", text)
    # remove orphan commas/spaces left behind
    text = re.sub(r"\s*,\s*,", ",", text)
    text = re.sub(r"\s*;\s*;", ";", text)
    text = re.sub(r"\(\s*\)", "", text)
    text = WHITESPACE_FIX.sub(" ", text).strip()
    return text


def main() -> int:
    log("step REV2/A1 · legal citation cleanup begin")
    src = HERE / "data" / "high_density" / "legal_v2" / "passages.jsonl"
    out_dir = HERE / "data" / "high_density" / "legal_v2_clean"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "passages.jsonl"

    n_in = 0; n_out = 0
    total_before = 0; total_after = 0
    with src.open("r", encoding="utf-8") as fin, out.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            n_in += 1
            rec = json.loads(line)
            orig_text = rec["text"]
            total_before += len(orig_text.split())
            cleaned = clean_citation(orig_text)
            wc = len(cleaned.split())
            if wc < 150:
                continue  # drop if too short after cleaning
            new_rec = dict(rec)
            new_rec["text"] = cleaned
            new_rec["original_wc"] = len(orig_text.split())
            new_rec["cleaned_wc"] = wc
            fout.write(json.dumps(new_rec, ensure_ascii=False) + "\n")
            n_out += 1
            total_after += wc
    log(f"step REV2/A1 · processed {n_in} → kept {n_out} · "
        f"avg WC before={total_before//max(n_in,1)} after={total_after//max(n_out,1)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
