"""Deterministic syntactic transformation experiment.

We take a small set of short base sentences and apply a series of
clause-embedding transformations that:
    (a) strictly add words, never substitute, so vocabulary set grows
        monotonically;
    (b) increment the Mean Clausal Depth by exactly one per stage; and
    (c) leave Flesch Reading Ease and Type-Token Ratio free to drift.

For each base sentence we generate 5 variants at depth 0, 1, 2, 3, 4 and
measure WC, FRE, TTR, MCD across all variants.  We then plot the average
trajectory across base sentences.

This experiment is intentionally deterministic, free, and reproducible.
It directly addresses the construct-validity worry that lexical and
syntactic difficulty are confounded: by holding vocabulary identical (up
to monotonic growth) and varying only syntactic embedding, any FRE/TTR
movement is attributable to the embedding alone.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import spacy
import textstat


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


CLAUSAL_DEPS = {"ccomp", "xcomp", "advcl", "relcl", "acl", "csubj"}


def max_clausal_depth(token, depth: int = 0) -> int:
    if not list(token.children):
        return depth
    best = depth
    for child in token.children:
        inc = 1 if child.dep_ in CLAUSAL_DEPS else 0
        sub = max_clausal_depth(child, depth + inc)
        if sub > best:
            best = sub
    return best


def metrics(text: str, nlp) -> dict:
    flat = " ".join(text.split())
    wc = textstat.lexicon_count(flat, removepunct=True)
    fre = textstat.flesch_reading_ease(flat)
    toks = [t for t in flat.lower().split() if any(c.isalpha() for c in t)]
    norm = ["".join(c for c in t if c.isalpha()) for t in toks]
    norm = [t for t in norm if t]
    ttr = len(set(norm)) / len(norm) if norm else 0.0
    doc = nlp(flat)
    depths = [max_clausal_depth(s.root, 0) for s in doc.sents]
    mcd = sum(depths) / len(depths) if depths else 0.0
    return {"WC": wc, "FRE": round(fre, 3), "TTR": round(ttr, 4),
            "MCD": round(mcd, 3), "n_sent": len(depths)}


# Each base sentence has a sequence of variants D0..D4.  We use true ccomp
# nesting (each stage embeds the previous one inside a new reporting clause)
# so that the spaCy dependency parser registers an increment of clausal depth
# at every stage.  Vocabulary set grows monotonically by design.
VARIANTS = [
    {
        "base": "student-homework",
        "stages": [
            "The student finished the homework.",
            "The teacher said that the student finished the homework.",
            "The principal claimed that the teacher said that the student finished the homework.",
            "The superintendent reported that the principal claimed that the teacher said that the student finished the homework.",
            "The board confirmed that the superintendent reported that the principal claimed that the teacher said that the student finished the homework.",
        ],
    },
    {
        "base": "city-bridge",
        "stages": [
            "The city built the bridge.",
            "The mayor announced that the city built the bridge.",
            "The journalist wrote that the mayor announced that the city built the bridge.",
            "The editor insisted that the journalist wrote that the mayor announced that the city built the bridge.",
            "The publisher demanded that the editor insisted that the journalist wrote that the mayor announced that the city built the bridge.",
        ],
    },
    {
        "base": "scientist-result",
        "stages": [
            "The scientist published the result.",
            "The journal confirmed that the scientist published the result.",
            "The committee verified that the journal confirmed that the scientist published the result.",
            "The agency declared that the committee verified that the journal confirmed that the scientist published the result.",
            "The minister announced that the agency declared that the committee verified that the journal confirmed that the scientist published the result.",
        ],
    },
    {
        "base": "company-product",
        "stages": [
            "The company released the product.",
            "Analysts noted that the company released the product.",
            "The newspaper reported that analysts noted that the company released the product.",
            "Investors heard that the newspaper reported that analysts noted that the company released the product.",
            "Regulators learned that investors heard that the newspaper reported that analysts noted that the company released the product.",
        ],
    },
    {
        "base": "engineer-plan",
        "stages": [
            "The engineer approved the plan.",
            "Management confirmed that the engineer approved the plan.",
            "Auditors verified that management confirmed that the engineer approved the plan.",
            "Headquarters acknowledged that auditors verified that management confirmed that the engineer approved the plan.",
            "Shareholders saw that headquarters acknowledged that auditors verified that management confirmed that the engineer approved the plan.",
        ],
    },
    {
        "base": "writer-manuscript",
        "stages": [
            "The writer finished the manuscript.",
            "The editor reported that the writer finished the manuscript.",
            "The agent confirmed that the editor reported that the writer finished the manuscript.",
            "The publisher announced that the agent confirmed that the editor reported that the writer finished the manuscript.",
            "Reviewers acknowledged that the publisher announced that the agent confirmed that the editor reported that the writer finished the manuscript.",
        ],
    },
    {
        "base": "team-experiment",
        "stages": [
            "The team ran the experiment.",
            "Reviewers said that the team ran the experiment.",
            "Officials confirmed that reviewers said that the team ran the experiment.",
            "Sponsors recognized that officials confirmed that reviewers said that the team ran the experiment.",
            "Critics noted that sponsors recognized that officials confirmed that reviewers said that the team ran the experiment.",
        ],
    },
    {
        "base": "court-ruling",
        "stages": [
            "The court issued the ruling.",
            "The clerk announced that the court issued the ruling.",
            "Lawyers explained that the clerk announced that the court issued the ruling.",
            "The press reported that lawyers explained that the clerk announced that the court issued the ruling.",
            "Citizens understood that the press reported that lawyers explained that the clerk announced that the court issued the ruling.",
        ],
    },
    {
        "base": "artist-painting",
        "stages": [
            "The artist sold the painting.",
            "The dealer revealed that the artist sold the painting.",
            "Collectors heard that the dealer revealed that the artist sold the painting.",
            "Curators noted that collectors heard that the dealer revealed that the artist sold the painting.",
            "Historians recorded that curators noted that collectors heard that the dealer revealed that the artist sold the painting.",
        ],
    },
    {
        "base": "farmer-harvest",
        "stages": [
            "The farmer collected the harvest.",
            "Neighbors observed that the farmer collected the harvest.",
            "Reporters noted that neighbors observed that the farmer collected the harvest.",
            "Editors agreed that reporters noted that neighbors observed that the farmer collected the harvest.",
            "Readers learned that editors agreed that reporters noted that neighbors observed that the farmer collected the harvest.",
        ],
    },
]


def main() -> int:
    log("step 9/13 · adversarial transform begin · loading spaCy")
    nlp = spacy.load("en_core_web_sm")
    out_rows = []
    for v in VARIANTS:
        prev_vocab: set[str] = set()
        for depth, text in enumerate(v["stages"]):
            m = metrics(text, nlp)
            toks = set(
                "".join(c for c in t if c.isalpha())
                for t in text.lower().split()
                if any(c.isalpha() for c in t)
            )
            new_vocab = toks - prev_vocab
            grew = prev_vocab.issubset(toks)
            prev_vocab = toks
            out_rows.append({
                "base": v["base"], "depth": depth, "text": text,
                **m,
                "added_words": " ".join(sorted(new_vocab)),
                "vocab_monotonic": grew,
            })
            log(f"step 9/13 · {v['base']} D{depth} WC={m['WC']} "
                f"FRE={m['FRE']} TTR={m['TTR']} MCD={m['MCD']} "
                f"monotonic={grew}")

    df = pd.DataFrame(out_rows)
    df.to_csv(HERE / "data" / "adversarial" / "results.csv",
              index=False)
    log("step 9/13 · wrote adversarial/results.csv")

    # Verify the manipulation worked: MCD should rise approximately linearly
    # with depth, while FRE and TTR should move less drastically.
    by_depth = df.groupby("depth")[["WC", "FRE", "TTR", "MCD"]].mean()
    by_depth_std = df.groupby("depth")[["WC", "FRE", "TTR", "MCD"]].std()
    log("step 9/13 · mean by depth:")
    print(by_depth.round(3).to_string(), flush=True)

    # Figure: 4-panel showing trajectories
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), dpi=160)
    metrics_names = ["WC", "FRE", "TTR", "MCD"]
    colors = ["#888888", "#1f77b4", "#2ca02c", "#c0392b"]
    for ax, m_name, color in zip(axes.ravel(), metrics_names, colors):
        for base in df["base"].unique():
            sub = df[df["base"] == base].sort_values("depth")
            ax.plot(sub["depth"], sub[m_name], color=color, alpha=0.25,
                    linewidth=1)
        m_mean = df.groupby("depth")[m_name].mean()
        ax.plot(m_mean.index, m_mean.values, color=color,
                linewidth=2.6, marker="o", label="mean")
        ax.set_title(f"{m_name} vs imposed clausal depth")
        ax.set_xlabel("Imposed embedding depth (D)")
        ax.set_ylabel(m_name)
        ax.grid(True, linestyle=":", alpha=0.4)
        ax.set_xticks([0, 1, 2, 3, 4])
    fig.suptitle("Adversarial transformation: holding vocabulary "
                 "set monotonic, varying clausal depth\n"
                 "(individual base sentences faint; bold line = mean across "
                 f"{len(VARIANTS)} bases)",
                 fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(HERE / "figures" / "adversarial_transform.png",
                dpi=180, bbox_inches="tight")
    plt.close(fig)
    log("step 9/13 · wrote figures/adversarial_transform.png")

    # Compute correlation depth vs metric across all (base × depth) cells
    from scipy import stats as sps
    summary = {}
    for m_name in metrics_names:
        r, p = sps.pearsonr(df["depth"], df[m_name])
        summary[m_name] = {"pearson_r": round(r, 4),
                            "p_value": float(p)}
    log(f"step 9/13 · correlations: {summary}")
    (HERE / "data" / "adversarial" / "summary.json").write_text(
        json.dumps({
            "n_base_sentences": len(VARIANTS),
            "depths": [0, 1, 2, 3, 4],
            "correlations_depth_vs_metric": summary,
            "mean_by_depth": by_depth.round(4).to_dict(),
            "all_monotonic": bool(df["vocab_monotonic"].all()),
        }, indent=2),
        encoding="utf-8")
    log("step 9/13 · adversarial complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
