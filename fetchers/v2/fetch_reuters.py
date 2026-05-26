"""Fetch Reuters-21578 via NLTK and chunk into ~150-400w passages."""
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


TARGET = 1500


def main() -> int:
    log("step PHASE1/3 · reuters fetch begin · target {}".format(TARGET))
    import nltk
    nltk.download("reuters", quiet=True)
    nltk.download("punkt", quiet=True)
    from nltk.corpus import reuters

    fileids = reuters.fileids()
    log(f"step PHASE1/3 · reuters loaded · {len(fileids)} files available")
    out_path = HERE / "data" / "baseline" / "reuters" / "passages.jsonl"
    kept = 0
    with out_path.open("w", encoding="utf-8") as fout:
        for fid in fileids:
            if kept >= TARGET:
                break
            try:
                raw = reuters.raw(fid)
            except Exception:
                continue
            # strip ALL-CAPS leading title line(s) and dateline
            lines = raw.split("\n")
            body_lines = []
            for line in lines:
                if not body_lines:
                    if line.isupper() or len(line.strip()) < 5:
                        continue
                body_lines.append(line)
            body = " ".join(body_lines)
            body = re.sub(r"\s+", " ", body).strip()
            # Reuters articles include "Reuter" trailing marker; strip
            body = re.sub(r"\s*Reuter\s*$", "", body)
            wc = len(body.split())
            if 130 <= wc <= 420:
                rec = {
                    "corpus_id": f"reuters_{fid.replace('/','_')}",
                    "register": "reuters_newswire",
                    "bucket": "baseline",
                    "fileid": fid,
                    "source": ("Reuters-21578 (NLTK distribution), "
                                "newswire 1987"),
                    "text": body,
                }
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                kept += 1
                if kept % 200 == 0:
                    log(f"step PHASE1/3 · reuters kept={kept}")
            elif wc > 420:
                # chunk longer articles into pieces, sentence-aligned
                import re as _re
                sents = _re.split(r"(?<=[.!?])\s+(?=[A-Z])", body)
                chunk = []
                chunk_wc = 0
                for s in sents:
                    sw = len(s.split())
                    if chunk_wc + sw > 400 and chunk_wc >= 130:
                        text = " ".join(chunk)
                        rec = {
                            "corpus_id": f"reuters_{fid.replace('/','_')}_c{len(chunk)}",
                            "register": "reuters_newswire",
                            "bucket": "baseline",
                            "fileid": fid,
                            "source": "Reuters-21578 (NLTK)",
                            "text": text,
                        }
                        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        kept += 1
                        chunk = [s]
                        chunk_wc = sw
                        if kept >= TARGET:
                            break
                    else:
                        chunk.append(s)
                        chunk_wc += sw
                if kept < TARGET and chunk_wc >= 130:
                    text = " ".join(chunk)
                    rec = {
                        "corpus_id": f"reuters_{fid.replace('/','_')}_cfinal",
                        "register": "reuters_newswire",
                        "bucket": "baseline",
                        "fileid": fid,
                        "source": "Reuters-21578 (NLTK)",
                        "text": text,
                    }
                    fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    kept += 1
    log(f"step PHASE1/3 · reuters done · kept {kept}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
