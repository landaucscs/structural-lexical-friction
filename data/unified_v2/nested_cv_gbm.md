# Nested 5-fold CV for GBM (with inner RandomizedSearch)

Outer loop: 5-fold StratifiedKFold; inner loop: 3-fold CV with 12 random hyperparameter samples for T1/T2 (drawn from the full grid) and 6 samples for T3 (drawn from a reduced grid to fit the memory budget on the available hardware).  Reports mean outer-fold AUC and best inner-loop parameters per outer fold.

| Tier | # feat | Mean AUC | SD | Per-fold AUC |
|------|--------|----------|------|--------------|
| T1_surface | 5 | 0.9833 | 0.0017 | 0.9832, 0.9857, 0.9845, 0.9823, 0.9807 |
| T2_lex | 7 | 0.9875 | 0.0019 | 0.9880, 0.9891, 0.9895, 0.9868, 0.9841 |
| T3_full | 17 | 0.9918 | 0.0014 | 0.9925, 0.9923, 0.9938, 0.9905, 0.9898 |

## Best hyperparameters per outer fold
### T1_surface
- Fold 1: n_estimators=400, max_depth=3, learning_rate=0.08
- Fold 2: n_estimators=400, max_depth=3, learning_rate=0.08
- Fold 3: n_estimators=400, max_depth=3, learning_rate=0.08
- Fold 4: n_estimators=400, max_depth=3, learning_rate=0.08
- Fold 5: n_estimators=400, max_depth=3, learning_rate=0.08

### T2_lex
- Fold 1: n_estimators=400, max_depth=5, learning_rate=0.08
- Fold 2: n_estimators=400, max_depth=3, learning_rate=0.08
- Fold 3: n_estimators=400, max_depth=5, learning_rate=0.08
- Fold 4: n_estimators=400, max_depth=3, learning_rate=0.08
- Fold 5: n_estimators=400, max_depth=3, learning_rate=0.08

### T3_full
- Fold 1: n_estimators=400, max_depth=5, learning_rate=0.08
- Fold 2: n_estimators=300, max_depth=4, learning_rate=0.1
- Fold 3: n_estimators=300, max_depth=4, learning_rate=0.1
- Fold 4: n_estimators=300, max_depth=4, learning_rate=0.1
- Fold 5: n_estimators=300, max_depth=4, learning_rate=0.1

