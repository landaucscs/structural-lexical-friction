"""Master orchestrator: fire all v3 analyses in sequence after sm metrics done.

Order:
  1. Mann-Whitney CSAT vs LogiQA (decision: HSAAR pool or keep separate)
  2. Binary classification (full + length-controlled) on v3
  3. Build length-matched sub-corpus from v3
  4. Compute sm metrics on length-matched
  5. Classification on length-matched
  6. Multi-class register classification
  7. Intra-register difficulty quartile
  8. VIF + PCA
  9. Nested 5-fold CV for GBM
 10. benepar subset constituent-parse robustness check
"""
from __future__ import annotations

import datetime as _dt
import io
import subprocess
import sys
from pathlib import Path

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


PY = sys.executable
PJ_ROOT = str(HERE)
import os
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"


def run(cmd: list[str], label: str) -> None:
    log(f"step ORC · ▶ {label}")
    p = subprocess.run(cmd, cwd=PJ_ROOT, env=env, capture_output=True,
                        text=True)
    if p.returncode != 0:
        log(f"step ORC · ✗ {label} (exit={p.returncode})")
        # show last 20 lines of stderr/stdout
        for line in (p.stderr or "").splitlines()[-15:]:
            log(f"step ORC · stderr · {line}")
        for line in (p.stdout or "").splitlines()[-5:]:
            log(f"step ORC · stdout · {line}")
    else:
        # show last 3 lines of stdout
        for line in (p.stdout or "").splitlines()[-3:]:
            log(f"step ORC · ↪ {line}")
        log(f"step ORC · ✓ {label}")


def main() -> int:
    log("step ORC · run_all_v3 begin")

    # 1. Mann-Whitney
    run([PY, "analysis/mann_whitney_csat_logiqa.py"], "Mann-Whitney CSAT vs LogiQA")

    # 2. Binary classification v3 (full + LC)
    run([PY, "analysis/run_classification_v2.py",
         "--metrics", "data/unified_v2/metrics_v3_sm.csv",
         "--out-stem", "classification_v3_sm"],
        "v3 sm classification")

    # 3. Build length-matched sub-corpus from v3
    # need to point to v3 corpus
    run([PY, "-c", (
        "import sys; sys.path.insert(0, 'analysis'); "
        "from build_length_matched import main as _m; "
        "import build_length_matched as B; "
        "B.HERE = type(B.HERE)('.'); "
        "import json, random; "
        "TARGET_MIN=150; TARGET_MAX=190; "
        "rng=random.Random(2026); "
        "recs=[json.loads(l) for l in open('data/unified_v3/corpus.jsonl', encoding='utf-8') if l.strip()]; "
        "by_reg={}; "
        "[by_reg.setdefault(r['register'],[]).append(r) for r in recs]; "
        "out_recs=[]; \n"
        "for reg, rs in by_reg.items(): \n"
        "    rng.shuffle(rs); kept=[]; \n"
        "    for r in rs: \n"
        "        chs = B.chunk_to_target(r['text']); \n"
        "        for ci, c in enumerate(chs): \n"
        "            if len(kept) >= 1500: break\n"
        "            nr = dict(r); nr['corpus_id'] = f\"{r['corpus_id']}_lm{ci}\"; nr['text']=c; kept.append(nr)\n"
        "        if len(kept) >= 1500: break\n"
        "    out_recs.extend(kept)\n"
        "import json\n"
        "with open('data/unified_v3/corpus_length_matched.jsonl', 'w', encoding='utf-8') as f:\n"
        "    [f.write(json.dumps(r, ensure_ascii=False)+'\\n') for r in out_recs]\n"
        "print('length-matched v3 corpus:', len(out_recs))"
    )], "Build length-matched v3 corpus")

    # 4. sm metrics on length-matched
    run([PY, "analysis/compute_metrics_v2.py",
         "--parser", "sm",
         "--corpus", "data/unified_v3/corpus_length_matched.jsonl",
         "--out-stem", "metrics_v3_sm_lm"],
        "sm metrics on v3 length-matched")

    # 5. classification on length-matched
    run([PY, "analysis/run_classification_v2.py",
         "--metrics", "data/unified_v2/metrics_v3_sm_lm.csv",
         "--out-stem", "classification_v3_lm"],
        "v3 length-matched classification")

    # 6. multi-class (modify path to v3)
    run([PY, "-c", (
        "import sys; sys.path.insert(0, 'analysis'); "
        "import multiclass_classification as M; "
        "M.HERE = type(M.HERE)('.'); "
        "import pandas as pd; "
        "df = pd.read_csv('data/unified_v2/metrics_v3_sm.csv'); "
        "df.to_csv('data/unified_v2/metrics_v2_sm.csv', index=False); "
        "M.main()"
    )], "Multi-class on v3")

    # 7. intra-register
    run([PY, "analysis/intra_register_quartile.py"], "Intra-register quartile")

    # 8. VIF + PCA
    run([PY, "analysis/vif_pca_analysis.py"], "VIF + PCA")

    # 9. Nested CV for GBM
    run([PY, "analysis/nested_cv_gbm.py"], "Nested CV (GBM)")

    # 10. benepar subset
    run([PY, "analysis/benepar_subset.py"], "Benepar subset")

    log("step ORC · run_all_v3 complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
