# Intra-Register Difficulty Quartile Classification

Within each register, the lowest-FRE quartile (hardest, $y=1$) is compared against the highest-FRE quartile (easiest, $y=0$) using 5-fold cross-validation.  FRE is excluded from the feature set to keep the task non-circular (FRE defined the labels).

| Register | Tier | n | AUC (*LR*) | AUC (*GBM*) |
|----------|------|----|-----------|-------------|
| wikitext_modern_encyclopedic | T1_noFRE | 1000 | 0.9813 | 0.9811 |
| wikitext_modern_encyclopedic | T3_noFRE | 1000 | 0.9907 | 0.9894 |
| brown_news_general | T1_noFRE | 200 | 0.9909 | 0.9600 |
| brown_news_general | T3_noFRE | 200 | 0.9961 | 0.9737 |
| gutenberg_fiction | T1_noFRE | 926 | 0.9984 | 0.9963 |
| gutenberg_fiction | T3_noFRE | 926 | 0.9964 | 0.9980 |
| reuters_newswire | T1_noFRE | 740 | 0.9950 | 0.9922 |
| reuters_newswire | T3_noFRE | 740 | 0.9972 | 0.9948 |
