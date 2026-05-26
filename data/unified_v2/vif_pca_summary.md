# Multicollinearity (VIF) and PCA on Syntactic Indices

## VIF (linear regression auxiliary; full feature set)

| Feature | VIF | Flag |
|---------|-----|------|
| FRE | 5.12 | ⚠ collinear |
| ARI | 6.72 | ⚠ collinear |
| WC | 6.32 | ⚠ collinear |
| TTR | 6.53 | ⚠ collinear |
| MLS | 9.15 | ⚠ collinear |
| MTLD | 2.62 |  |
| NomR | 1.73 |  |
| MCD | 5.32 | ⚠ collinear |
| MaxCD | 2.93 |  |
| DC_C | 4.43 |  |
| CT_T | 2.15 |  |
| MLC | 2.15 |  |
| MAL | 17.61 | ⚠ collinear |
| MaxAL | 7.87 | ⚠ collinear |
| LeftBR | 1.20 |  |
| MeanArcCross | 33.91 | ⚠ collinear |
| MaxArcCross | 12.20 | ⚠ collinear |

## PCA on 10 syntactic indices

Explained variance ratio: PC1 = 0.431, PC2 = 0.268, PC3 = 0.112, PC4 = 0.066. Cumulative top-2 = 0.699.

## Classification with PCA-compressed syntactic features

| Tier | # feat | GBM AUC |
|------|--------|---------|
| T1_surface | 5 | 0.9823 |
| T1+PC1 | 6 | 0.9825 |
| T1+PC1+PC2 | 7 | 0.9826 |
| T3_full | 17 | 0.9901 |
