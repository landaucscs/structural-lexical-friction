# v2 Multi-Class Register Classification

N = 16904 · 9 registers (simple_wikipedia removed)

## Macro and per-class AUC (5-fold CV)

| Model | Tier | macro-AUC | Acc | arxiv_abstract | brown_news_general | csat | gutenberg_fiction | judicial_opinion | logiqa | onestop_ele | onestop_int | reuters_newswire | wikitext_modern_encyclopedic |
|-------|------|-----------|-----|---|---|---|---|---|---|---|---|---|---|
| LR_OvR | T1_surface | 0.9502 | 0.7392 | 0.9690 | 0.8551 | 0.9464 | 0.9818 | 0.9899 | 0.9901 | 0.9674 | 0.9563 | 0.8769 | 0.9688 |
| RF | T1_surface | 0.9611 | 0.8280 | 0.9773 | 0.8680 | 0.9447 | 0.9835 | 0.9956 | 0.9925 | 0.9803 | 0.9716 | 0.9221 | 0.9757 |
| LR_OvR | T3_full | 0.9722 | 0.8250 | 0.9782 | 0.8954 | 0.9590 | 0.9889 | 0.9980 | 0.9920 | 0.9880 | 0.9810 | 0.9613 | 0.9806 |
| RF | T3_full | 0.9702 | 0.8578 | 0.9833 | 0.8829 | 0.9585 | 0.9847 | 0.9986 | 0.9939 | 0.9869 | 0.9767 | 0.9643 | 0.9725 |
