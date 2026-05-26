# Mann-Whitney U test · CSAT vs LogiQA (HSAAR pooling check)

CSAT n = 124 · LogiQA n = 4679

Two-sided Mann-Whitney U test, rank-biserial correlation as effect size.  Pooling judgment: |rank-biserial| < 0.2 *and* $p > 0.05$ treated as distributionally compatible.

| Metric | Mean CSAT | Mean LogiQA | U | $p$ | rank-biserial | Flag |
|--------|-----------|-------------|---|-----|---------------|------|
| MCD | 1.325 | 1.074 | 388622 | 8.68e-11 | -0.340 | DIFFER |
| MaxCD | 2.766 | 2.077 | 410398 | 5.52e-17 | -0.415 | DIFFER |
| DC_C | 0.620 | 0.545 | 376308 | 1.46e-08 | -0.297 | DIFFER |
| MAL | 2.426 | 2.525 | 259582 | 4.53e-02 | +0.105 | small effect |
| LeftBR | 0.498 | 0.534 | 188687 | 2.85e-11 | +0.350 | DIFFER |
| MeanArcCross | 1.200 | 1.278 | 266490 | 1.21e-01 | +0.081 |  |
| FRE | 39.094 | 39.398 | 282206 | 6.05e-01 | +0.027 |  |
| TTR | 0.642 | 0.659 | 243996 | 2.49e-03 | +0.159 | small effect |
| MTLD | 88.725 | 60.678 | 451264 | 3.90e-26 | -0.556 | DIFFER |

**Pooling decision:** NO — keep CSAT and LogiQA as separate registers
