"""Mann-Whitney U test comparing CSAT vs LogiQA distributions on key
syntactic indices.  Reports U statistic, p-value, and rank-biserial
correlation as effect size.  If pairwise p > 0.05 across all indices AND
|effect size| < 0.2, the two sources can be pooled into a single 'High-
Stakes Academic Assessment Register' (HSAAR).
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import sys
from pathlib import Path

import pandas as pd
from scipy import stats

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


KEY_METRICS = ["MCD", "MaxCD", "DC_C", "MAL", "LeftBR", "MeanArcCross",
               "FRE", "TTR", "MTLD"]


def main() -> int:
    metrics_path = HERE / "data" / "unified_v2" / "metrics_v3_sm.csv"
    if not metrics_path.exists():
        log("step MW · v3 metrics missing")
        return 1
    df = pd.read_csv(metrics_path)
    csat = df[df["register"] == "csat"]
    logiqa = df[df["register"] == "logiqa"]
    log(f"step MW · CSAT n={len(csat)} · LogiQA n={len(logiqa)}")

    rows = []
    md_rows = []
    all_ok = True
    for m in KEY_METRICS:
        a = csat[m].astype(float).dropna()
        b = logiqa[m].astype(float).dropna()
        u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        # rank-biserial effect size
        # r_rb = 1 - 2U / (n1*n2)
        rb = 1 - (2 * u) / (len(a) * len(b))
        flag = ""
        if p < 0.05 and abs(rb) >= 0.2:
            flag = "DIFFER"
            all_ok = False
        elif p < 0.05:
            flag = "small effect"
        rows.append({"metric": m,
                     "mean_csat": round(float(a.mean()), 4),
                     "mean_logiqa": round(float(b.mean()), 4),
                     "U": float(u), "p": float(p),
                     "rank_biserial": round(rb, 4),
                     "flag": flag})
        md_rows.append(
            f"| {m} | {a.mean():.3f} | {b.mean():.3f} | {u:.0f} | "
            f"{p:.2e} | {rb:+.3f} | {flag} |")
        log(f"step MW · {m}: csat={a.mean():.3f} logiqa={b.mean():.3f} "
            f"U={u:.0f} p={p:.2e} r_rb={rb:+.3f} {flag}")

    md = ["# Mann-Whitney U test · CSAT vs LogiQA (HSAAR pooling check)",
          "",
          f"CSAT n = {len(csat)} · LogiQA n = {len(logiqa)}",
          "",
          "Two-sided Mann-Whitney U test, rank-biserial correlation as effect "
          "size.  Pooling judgment: |rank-biserial| < 0.2 *and* $p > 0.05$ "
          "treated as distributionally compatible.",
          "",
          "| Metric | Mean CSAT | Mean LogiQA | U | $p$ | rank-biserial | "
          "Flag |",
          "|--------|-----------|-------------|---|-----|---------------|------|"]
    md.extend(md_rows)
    md.append("")
    md.append(f"**Pooling decision:** "
              f"{'YES — pool into HSAAR' if all_ok else 'NO — keep CSAT and LogiQA as separate registers'}")
    (HERE / "data" / "unified_v2" / "mann_whitney_csat_logiqa.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(
        HERE / "data" / "unified_v2" / "mann_whitney_csat_logiqa.csv",
        index=False)
    log(f"step MW · DECISION: " +
        ("pool into HSAAR" if all_ok else "keep separate"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
