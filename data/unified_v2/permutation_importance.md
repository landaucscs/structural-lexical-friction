# Permutation Importance Complement to RF Impurity

Permutation importance is computed by shuffling each feature on the held-out test split (20% stratified) and measuring the drop in test ROC-AUC, averaged over 15 random shuffles per feature. Unlike impurity importance, it is not split-vote-diluted by feature collinearity.

| Rank (perm) | Feature | Perm Δ AUC (mean ± SD) | RF impurity | Rank (impurity) |
|------|---------|------------------------|-------------|-----------------|
| 1 | WC | 0.2263 ± 0.0083 | 0.3435 | 1 |
| 2 | ARI | 0.0152 ± 0.0010 | 0.0690 | 5 |
| 3 | NomR | 0.0077 ± 0.0007 | 0.1310 | 2 |
| 4 | FRE | 0.0074 ± 0.0004 | 0.0854 | 4 |
| 5 | MLS | 0.0052 ± 0.0006 | 0.0362 | 8 |
| 6 | MaxArcCross | 0.0048 ± 0.0006 | 0.0423 | 7 |
| 7 | TTR | 0.0048 ± 0.0008 | 0.0994 | 3 |
| 8 | MTLD | 0.0039 ± 0.0006 | 0.0524 | 6 |
| 9 | MCD | 0.0018 ± 0.0003 | 0.0217 | 11 |
| 10 | LeftBR | 0.0016 ± 0.0003 | 0.0222 | 9 |
| 11 | MeanArcCross | 0.0011 ± 0.0003 | 0.0222 | 10 |
| 12 | DC/C | 0.0011 ± 0.0003 | 0.0170 | 12 |
| 13 | MAL | 0.0007 ± 0.0003 | 0.0153 | 13 |
| 14 | CT/T | 0.0005 ± 0.0002 | 0.0096 | 16 |
| 15 | MaxAL | 0.0004 ± 0.0002 | 0.0126 | 15 |
| 16 | MLC | 0.0003 ± 0.0001 | 0.0130 | 14 |
| 17 | MaxCD | 0.0002 ± 0.0001 | 0.0070 | 17 |
