# Stanza Parser Robustness on v3 Subset

Stratified subset of 500 passages from the v3 corpus, parsed with Stanford *Stanza* and compared against the primary `en_core_web_sm` results.

| Pair | Pearson $r$ | $p$ |
|------|-----------|-----|
| MCD (sm) vs MCD (Stanza) | 0.8400 | 2.40e-134 |

## Per-register means

| Register | n | mean MCD (sm) | mean MCD (Stanza) | diff |
|----------|---|---------------|-------------------|------|
| arxiv_abstract | 50 | 1.127 | 1.157 | -0.031 |
| brown_news_general | 50 | 1.152 | 1.229 | -0.077 |
| csat | 50 | 1.293 | 1.462 | -0.169 |
| gutenberg_fiction | 50 | 1.646 | 1.711 | -0.065 |
| judicial_opinion | 50 | 1.106 | 1.453 | -0.348 |
| logiqa | 50 | 1.312 | 1.074 | +0.238 |
| onestop_ele | 50 | 1.140 | 1.163 | -0.023 |
| onestop_int | 50 | 1.236 | 1.243 | -0.007 |
| reuters_newswire | 50 | 1.437 | 1.453 | -0.015 |
| wikitext_modern_encyclopedic | 50 | 0.975 | 1.114 | -0.139 |
