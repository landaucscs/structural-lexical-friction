"""Shared validation helpers.  Each stage calls validate_corpus() on its
output file and aborts on failure."""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent
PROGRESS_LOG = HERE / "progress.log"


def log(label: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {label}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def validate_corpus(
    path: Path,
    label: str,
    *,
    expected_min: int,
    expected_max: int | None = None,
    required_fields: tuple[str, ...] = ("corpus_id", "register", "bucket", "text"),
    min_word_count: int = 30,
    max_word_count: int = 1200,
) -> dict:
    """Validate a jsonl corpus file and return a summary dict.

    Raises AssertionError on any quality gate failure.  Validations:
      1. file exists, non-empty
      2. every line is valid JSON
      3. every record contains the required fields and a non-empty 'text'
      4. record count within [expected_min, expected_max]
      5. word-count distribution within [min_word_count, max_word_count]
      6. no duplicate corpus_id, no duplicate exact text
      7. text appears English-ish (ASCII ratio >= 0.9)
    """
    if not path.exists():
        raise AssertionError(f"{label}: file does not exist at {path}")
    if path.stat().st_size == 0:
        raise AssertionError(f"{label}: file is empty")

    records = []
    seen_ids = set()
    seen_texts = set()
    word_counts = []
    bad = []

    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception as exc:
                bad.append(f"line {lineno}: invalid JSON ({exc})")
                continue
            for fld in required_fields:
                if fld not in rec or not rec[fld]:
                    bad.append(f"line {lineno}: missing field {fld!r}")
                    break
            else:
                cid = rec["corpus_id"]
                if cid in seen_ids:
                    bad.append(f"line {lineno}: duplicate corpus_id {cid}")
                    continue
                seen_ids.add(cid)
                text = rec["text"].strip()
                if text in seen_texts:
                    bad.append(f"line {lineno}: duplicate text content")
                    continue
                seen_texts.add(text)
                wc = len(text.split())
                if wc < min_word_count or wc > max_word_count:
                    bad.append(f"line {lineno}: wc {wc} outside "
                               f"[{min_word_count}, {max_word_count}]")
                    continue
                ar = sum(1 for c in text if ord(c) < 128) / max(1, len(text))
                if ar < 0.90:
                    bad.append(f"line {lineno}: ASCII ratio {ar:.2f} < 0.90")
                    continue
                records.append(rec)
                word_counts.append(wc)

    n = len(records)
    summary = {
        "label": label,
        "path": str(path),
        "kept": n,
        "bad": len(bad),
        "bad_examples": bad[:5],
        "wc_min": min(word_counts) if word_counts else 0,
        "wc_max": max(word_counts) if word_counts else 0,
        "wc_mean": (sum(word_counts) / n) if n else 0,
    }
    log(f"step VALID · {label} · kept={n} bad={len(bad)} "
        f"wc=[{summary['wc_min']},{summary['wc_max']}] "
        f"mean={summary['wc_mean']:.1f}")
    if bad:
        for b in bad[:5]:
            log(f"step VALID · {label} · BAD · {b}")
    if n < expected_min:
        raise AssertionError(
            f"{label}: only {n} records kept (expected >= {expected_min})"
        )
    if expected_max is not None and n > expected_max:
        raise AssertionError(
            f"{label}: {n} records (expected <= {expected_max})"
        )
    return summary


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: validate.py <jsonl_path> <label> [min] [max]")
        sys.exit(1)
    path = Path(sys.argv[1])
    label = sys.argv[2]
    emin = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    emax = int(sys.argv[4]) if len(sys.argv) > 4 else None
    s = validate_corpus(path, label,
                        expected_min=emin, expected_max=emax)
    print(json.dumps(s, indent=2))
