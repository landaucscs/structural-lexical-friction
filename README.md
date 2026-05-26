# Structural-Lexical Friction

**Structural-Lexical Friction: A Cross-Register Computational Study of Text Difficulty**

This repository accompanies the working paper of the same name. It releases the manuscript, the cross-register corpus, the per-passage metric tables, every analysis script, every figure, and the full reproducibility chain from raw fetchers to the final PDF.

The paper introduces **structural-lexical friction** — the joint cognitive resistance a reader incurs when integrating lexical and syntactic information — and operationalises it through seventeen per-passage indices computed across **16,904 English passages** drawn from four high-density informational registers (Korean CSAT reading passages, LogiQA reasoning items, *arXiv* abstracts, U.S. federal judicial opinions with citations programmatically stripped) and five general informational registers (Brown, Project Gutenberg, *WikiText-103*, Reuters, OneStopEnglish at ELE and INT levels). A multi-block classification ablation, a word-count-matched adversarial transformation, and a three-parser robustness check together support a multi-dimensional view of text difficulty in which the *Flesch* formula's $W/S$ term mechanically absorbs clausal embedding, and parser-aware syntactic indices recover the structural signal once length is removed or held constant.

---

## Repository layout

```
.
├── manuscript.md                 # Source manuscript (Markdown + MathJax)
├── manuscript.pdf                # Compiled paper (579 KB, 26 pages)
├── README.md                     # this file
├── LICENSE                       # MIT (code) + CC-BY 4.0 (manuscript + figures)
├── CITATION.cff                  # Cite this work
├── requirements.txt              # Python dependency pins
├── .gitignore                    # excludes regenerable / large intermediate files
│
├── fetchers/                     # corpus acquisition scripts
│   ├── ingest_csat.py            # CSAT reading-comprehension items
│   ├── fetch_arxiv.py            # arXiv API (5 categories)
│   ├── fetch_courtlistener.py    # U.S. federal opinions (CourtListener API)
│   ├── fetch_baseline.py         # Brown + Gutenberg + Wikipedia (legacy)
│   ├── rescue_baseline.py        # Gutenberg + opportunistic wiki retry
│   ├── stream_legal_bulk.py      # CourtListener S3 bulk streaming
│   ├── validate.py               # corpus-jsonl schema validator
│   └── v2/                       # v2-round expansion fetchers
│   │   ├── fetch_wikitext.py     # HuggingFace wikitext-103-raw-v1
│   │   ├── fetch_reuters.py      # NLTK Reuters-21578
│   │   ├── fetch_onestop.py      # OneStopEnglish (GitHub)
│   │   ├── fetch_gutenberg_more.py
│   │   ├── fetch_arxiv_expand.py
│   │   ├── stream_legal_multichunk.py    # sentence-aligned legal chunks
│   │   └── fix_onestop_chunks.py
│   └── v3/                       # v3-round expansion fetchers
│       ├── clean_legal_citations.py     # reporter + statutory citation regex strip
│       └── fetch_logiqa.py
│
├── analysis/                     # downstream analysis scripts
│   ├── unify_v3.py               # canonical corpus assembly
│   ├── compute_metrics_v2.py     # 17-index pipeline (sm + trf parsers)
│   ├── build_length_matched.py   # 150-190w sub-corpus chunker
│   ├── run_classification_v2.py  # full + length-controlled ablation, DeLong
│   ├── intra_register_quartile.py
│   ├── multiclass_classification.py
│   ├── nested_cv_gbm.py
│   ├── nested_cv_gbm_recover.py  # checkpointed recovery variant
│   ├── adversarial_v3.py         # word-count-matched adversarial pairs
│   ├── parser_pilot.py           # 3-way pilot (sm/trf/Stanza)
│   ├── stanza_v3_subset.py       # v3 cross-parser anchor
│   ├── finalize_trf.py           # trf metrics top-up + merge
│   ├── permutation_importance.py # collinearity-robust feature importance
│   └── run_all_v3.py             # orchestrator
│
├── figures/                      # all manuscript figures (PNG)
│   ├── classification_v2_sm_roc.png             # Figure 1
│   ├── permutation_importance.png               # Figure 2 (impurity ‖ permutation)
│   ├── adversarial_v3.png                       # Figure 3 (WC-matched pairs)
│   └── (supplementary figures from earlier rounds)
│
├── data/
│   ├── unified_v3/
│   │   └── corpus.jsonl          # canonical 16,904-passage corpus
│   └── unified_v2/               # primary result tables (CSV / MD)
│       ├── metrics_v3_sm.csv     # 17 indices × 16,904 passages (en_core_web_sm)
│       ├── classification_v3_sm_results.csv
│       ├── classification_v3_sm_summary.md
│       ├── classification_v3_sm_delong.csv
│       ├── classification_v3_lm_results.csv         # length-matched
│       ├── classification_v3_lm_summary.md
│       ├── classification_v3_intra.csv              # intra-register quartile
│       ├── classification_v3_multiclass.csv         # multi-class register
│       ├── nested_cv_gbm.json
│       ├── nested_cv_gbm.md
│       ├── mann_whitney_csat_logiqa.csv             # pre-pooling test
│       ├── mann_whitney_csat_logiqa.md
│       ├── stanza_v3_subset.csv                     # parser-robustness anchor
│       ├── stanza_v3_subset.md
│       ├── vif_table.csv
│       ├── pca_loadings.csv
│       ├── pca_classification.csv
│       ├── vif_pca_summary.md
│       ├── permutation_importance.csv
│       └── permutation_importance.md
│
├── data/adversarial_v3/          # word-count-matched pair set + per-pair indices
│   ├── results.csv
│   ├── summary.json
│   └── summary.md
│
├── doi_verification_log.md       # CrossRef-checked DOI audit
├── verified_citations_v2.json    # machine-readable verification record
├── verify_dois_v2.py             # rerun the DOI check
│
└── convert_to_pdf_mathjax.py     # manuscript.md → manuscript.pdf (Playwright + MathJax)
```

Intermediate per-source fetcher outputs (`data/high_density/*`, `data/baseline/*`, etc.) and the legacy v1/v2 corpora are *not* committed; they are entirely regenerable from the fetchers in `fetchers/` and would inflate the clone size to no scientific gain. The canonical artefacts retained here are the v3 unified corpus, the v3 sm-parser metric table, every result CSV/MD the manuscript cites, and the figures.

---

## Reproducing the paper end-to-end

### 1. Environment

Python 3.12 is the tested interpreter. Create a virtual environment and install the pinned dependencies:

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -m playwright install chromium                # only needed to rebuild the PDF

# Optional (parser-robustness anchor, ~466 MB):
python -m spacy download en_core_web_trf
```

### 2. Corpus reconstruction

Some fetchers require account credentials or are rate-limited. Set them once:

```bash
export COURTLISTENER_TOKEN=<your_token>     # register at https://www.courtlistener.com
# arXiv and HuggingFace fetchers require no auth.
```

Then, in order:

```bash
# CSAT items — the CSAT JSONL files must be staged locally first; see fetchers/ingest_csat.py
python fetchers/ingest_csat.py

# arXiv (fast, 5 categories)
python fetchers/fetch_arxiv.py

# Brown + Project Gutenberg (baseline)
python fetchers/v2/fetch_gutenberg_more.py
python fetchers/v2/fetch_wikitext.py       # WikiText-103 via HuggingFace
python fetchers/v2/fetch_reuters.py        # NLTK Reuters-21578
python fetchers/v2/fetch_onestop.py        # OneStopEnglish GitHub
python fetchers/v2/fix_onestop_chunks.py

# Legal opinions — bulk-stream from CourtListener S3 (no API rate limit; ~30 minutes)
python fetchers/v2/stream_legal_multichunk.py
python fetchers/v3/clean_legal_citations.py

# LogiQA (GitHub raw)
python fetchers/v3/fetch_logiqa.py

# Canonical unified corpus
python analysis/unify_v3.py
```

### 3. Metric computation and analyses

```bash
# Primary metric table (17 indices × ~16,904 passages, ~22 min on CPU)
python analysis/compute_metrics_v2.py --parser sm --corpus data/unified_v3/corpus.jsonl --out-stem metrics_v3_sm

# Pre-pooling Mann-Whitney (CSAT vs LogiQA)
python analysis/mann_whitney_csat_logiqa.py        # if present; otherwise inline in orchestrator

# Headline classification ablation (5-fold CV, paired DeLong, bootstrap CI)
python analysis/run_classification_v2.py --metrics data/unified_v2/metrics_v3_sm.csv --out-stem classification_v3_sm

# Length-matched sub-corpus
python analysis/build_length_matched.py
python analysis/compute_metrics_v2.py --parser sm --corpus data/unified_v3/corpus_length_matched.jsonl --out-stem metrics_v3_sm_lm
python analysis/run_classification_v2.py --metrics data/unified_v2/metrics_v3_sm_lm.csv --out-stem classification_v3_lm

# Intra-register and multi-class
python analysis/intra_register_quartile.py
python analysis/multiclass_classification.py

# Nested CV (T1 + T2 + T3, with inner-loop hyperparameter search)
python analysis/nested_cv_gbm.py
# If a tier crashes mid-run, the checkpointed recovery variant is:
python analysis/nested_cv_gbm_recover.py

# VIF + PCA + permutation importance
python analysis/permutation_importance.py

# Adversarial v3 (word-count-matched pairs)
python analysis/adversarial_v3.py

# Parser robustness — 3-way pilot
python analysis/parser_pilot.py
# Optional v3 anchor (~12 min for 500 passages on CPU)
python analysis/stanza_v3_subset.py
# Optional full-corpus trf re-parse (multi-hour; v2 corpus used in the paper)
python analysis/compute_metrics_v2.py --parser trf --corpus data/unified_v3/corpus.jsonl --out-stem metrics_v3_trf
python analysis/finalize_trf.py
```

The orchestrator script `analysis/run_all_v3.py` chains the post-corpus analyses end-to-end if you prefer one entry point.

### 4. Rebuild the PDF

```bash
python convert_to_pdf_mathjax.py    # writes manuscript.pdf (~580 KB)
```

The script renders `manuscript.md` through Markdown → HTML → headless Chromium with MathJax v3 typesetting; figures are embedded as base64 so the PDF is self-contained.

---

## Headline results

| Block | $\Delta\mathit{AUC}$ (T3 − T1, *GBM*) | $z$ | $p$ (paired DeLong) |
|---|---|---|---|
| Full corpus, full features | +0.0077 | 15.47 | $< 10^{-4}$ |
| Full corpus, length-controlled | +0.1105 | 43.77 | $< 10^{-4}$ |
| Length-matched (150–190 w), full features | +0.0369 | 14.66 | $< 10^{-4}$ |
| Length-matched, length-controlled | +0.0890 | 22.88 | $< 10^{-4}$ |
| Nested 5-fold CV (mean AUC, GBM) | T1 = 0.9833 → T3 = 0.9918 | — | monotonic across tiers |
| Adversarial v3 (WC-matched, n = 25) | $\mathit{MCD}$ Δ = +1.36 | $p = 1.5 \times 10^{-5}$ | $\mathit{FRE}$ Δ n.s. ($p = 0.34$) |
| Parser robustness (sm ↔ trf, n = 12,242 full corpus) | $r_{MCD} = 0.898$, $r_{LeftBR} = 0.940$ | — | — |
| Parser robustness (sm ↔ Stanza, v3 subset n = 500) | $r_{MCD} = 0.840$ | $p = 2.4 \times 10^{-134}$ | — |

See the manuscript §4 for the full tables and §5 for discussion.

---

## Data provenance

| Register | Source | Original licence |
|---|---|---|
| CSAT | Korea Institute of Curriculum and Evaluation (KICE) — official exam releases | Public release for educational use |
| LogiQA | Liu et al. (2020), GitHub `lgw863/LogiQA-dataset` | Released for research |
| arXiv abstracts | arXiv API (`export.arxiv.org`) | CC-0 / arXiv non-exclusive licence |
| U.S. federal judicial opinions | CourtListener S3 bulk archive (`com-courtlistener-storage`) | Public domain (U.S. federal works) |
| Brown Corpus | NLTK distribution | Brown University academic research licence |
| Project Gutenberg | gutenberg.org plain-text releases | Public domain (U.S.) |
| WikiText-103 | HuggingFace `salesforce/wikitext`, `wikitext-103-raw-v1` (Merity et al. 2016) | CC-BY-SA 3.0 |
| Reuters-21578 | NLTK Reuters distribution | Research-only use |
| OneStopEnglish | Vajjala & Lucic (2018), GitHub `nishkalavallabhi/OneStopEnglishCorpus` | CC-BY-SA 4.0 |

Where third-party licences impose redistribution restrictions, we do not commit the raw text to this repository; the relevant fetchers reconstruct each source from its canonical public location on demand.

---

## Citing this work

If you build on this paper, please cite (BibTeX placeholder until SSRN-assigned identifier issued):

```bibtex
@misc{structural-lexical-friction-2026,
  author       = {Jaeho Kim},
  title        = {{Structural-Lexical Friction: A Cross-Register Computational Study of Text Difficulty}},
  year         = 2026,
  howpublished = {Working paper, SSRN},
  url          = {https://github.com/landaucscs/structural-lexical-friction}
}
```

A machine-readable `CITATION.cff` is provided in the repository root; GitHub will surface it automatically on the repo's "Cite this repository" widget.

---

## DOI verification log

Every citation in the manuscript bibliography (18 entries) was verified against CrossRef; the audit record lives in [`doi_verification_log.md`](doi_verification_log.md) and the machine-readable payload in [`verified_citations_v2.json`](verified_citations_v2.json). To re-run the audit:

```bash
python verify_dois_v2.py
```

---

## Generative AI disclosure

The author used Claude Code (Anthropic) in developing and running the fetcher scripts and analysis pipelines. The author bears full responsibility for all conceptual framing, analytical decisions, and the final content of the manuscript. See the manuscript's Generative AI Disclosure note at the end of the PDF.

---

## Licence summary

- **Code** under `analysis/`, `fetchers/`, `convert_to_pdf_mathjax.py`, `verify_dois_v2.py`: MIT.
- **Manuscript** (`manuscript.md`, `manuscript.pdf`), figures in `figures/`, derived metrics and result tables: CC-BY 4.0.
- **Third-party source corpora**: each retains its original licence — see the *Data provenance* table above and §3.1 of the manuscript.

Full text in [`LICENSE`](LICENSE).
