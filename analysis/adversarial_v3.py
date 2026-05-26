"""Word-count-matched adversarial transformation v3.

This version addresses the mathematical-circularity critique of the v2
adversarial design.  In v2, each successive depth stage added a reporting
clause, which mechanically inflated W/S and forced FRE down by definition.
The v2 result was therefore not an empirical discovery but a tautological
consequence of the Flesch formula.

In v3, we construct 25 sentence pairs.  Each pair is matched on:
  - Word count (delta = 0)
  - Sentence count (both single sentences)
  - Vocabulary set (both use the same content words; only function-word
    overhead differs slightly)
But contrasts on syntactic architecture:
  - LOW-friction: two coordinated independent clauses ("X did Y and Z did W")
  - HIGH-friction: deeply nested complement clause ("That X did Y compelled
    Z to do W")

If WC and W/S are held constant, FRE cannot move much (only the syllables-
per-word term can drift, modestly).  Any movement in MCD between the pair
is therefore attributable to syntactic structure alone.  A nonparametric
paired test (Wilcoxon signed-rank) is reported.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
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


def max_clausal_depth(token, depth=0):
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
    text = " ".join(text.split())
    wc = textstat.lexicon_count(text, removepunct=True)
    fre = textstat.flesch_reading_ease(text)
    toks = [t for t in text.lower().split() if any(c.isalpha() for c in t)]
    norm = ["".join(c for c in t if c.isalpha()) for t in toks]
    norm = [t for t in norm if t]
    ttr = len(set(norm)) / len(norm) if norm else 0.0
    doc = nlp(text)
    depths = []
    arc_lens = []
    cross_counts = []
    for sent in doc.sents:
        depths.append(max_clausal_depth(sent.root, 0))
        for tok in sent:
            if tok.head == tok or tok.is_punct:
                continue
            arc_lens.append(abs(tok.i - tok.head.i))
        # arc-crossing
        sent_start = sent.start
        sent_end = sent.end
        for pos in range(sent_start, sent_end):
            n = sum(1 for t in sent if t.head != t and not t.is_punct
                    and min(t.i, t.head.i) < pos < max(t.i, t.head.i))
            cross_counts.append(n)
    return {
        "WC": wc,
        "FRE": round(fre, 3),
        "TTR": round(ttr, 4),
        "MCD": round(sum(depths)/len(depths) if depths else 0.0, 3),
        "MaxCD": max(depths) if depths else 0,
        "MAL": round(sum(arc_lens)/len(arc_lens) if arc_lens else 0.0, 3),
        "MaxArcCross": max(cross_counts) if cross_counts else 0,
        "n_sent": len(depths),
        "sylcount_per_word": round(textstat.syllable_count(text) / max(1, wc), 3),
    }


# 25 WC-matched pairs.  Each pair: shallow coordinated vs deeply nested,
# same content words (modulo small function-word differences) and same WC.
PAIRS = [
    ("The investigator discovered the data and the team published the report.",
     "That the investigator discovered the data compelled the team to publish."),
    ("The scientist confirmed the result and the journal accepted the paper.",
     "Whether the scientist confirmed the result determined the journal acceptance."),
    ("The court denied the motion and the lawyer appealed the decision.",
     "That the court denied the motion forced the lawyer to appeal urgently."),
    ("The reader noticed the error and the editor corrected the manuscript.",
     "That the reader noticed the error obliged the editor to revise."),
    ("The teacher reviewed the answer and the student rewrote the essay.",
     "That the teacher reviewed the answer required the student to rewrite."),
    ("The witness recalled the event and the prosecutor recorded the statement.",
     "Whether the witness recalled the event mattered to the prosecutor's case."),
    ("The engineer tested the device and the company released the product.",
     "That the engineer tested the device convinced the company to ship."),
    ("The author finished the chapter and the publisher scheduled the release.",
     "That the author finished the chapter allowed the publisher to schedule."),
    ("The committee reviewed the bid and the agency approved the contract.",
     "That the committee reviewed the bid satisfied the agency's procurement rules."),
    ("The reporter covered the case and the newspaper printed the article.",
     "That the reporter covered the case let the newspaper print exclusively."),
    ("The artist painted the portrait and the gallery exhibited the work.",
     "Whether the artist painted the portrait determined the gallery's exhibition."),
    ("The chef prepared the dish and the critic praised the restaurant.",
     "That the chef prepared the dish surprised the critic at the restaurant."),
    ("The pilot completed the flight and the mechanic inspected the aircraft.",
     "That the pilot completed the flight allowed the mechanic to inspect."),
    ("The student solved the problem and the professor accepted the answer.",
     "That the student solved the problem assured the professor of competence."),
    ("The reviewer flagged the issue and the developer patched the bug.",
     "That the reviewer flagged the issue obliged the developer to patch."),
    ("The doctor examined the patient and the nurse updated the chart.",
     "That the doctor examined the patient required the nurse to update."),
    ("The detective interviewed the suspect and the captain closed the case.",
     "That the detective interviewed the suspect persuaded the captain to close."),
    ("The auditor reviewed the books and the board ratified the report.",
     "That the auditor reviewed the books permitted the board to ratify."),
    ("The driver followed the route and the dispatcher logged the trip.",
     "That the driver followed the route helped the dispatcher to log."),
    ("The clerk processed the form and the office mailed the response.",
     "That the clerk processed the form let the office mail the response."),
    ("The senator drafted the bill and the committee voted on the proposal.",
     "That the senator drafted the bill compelled the committee to vote."),
    ("The mayor announced the policy and the city implemented the change.",
     "That the mayor announced the policy obliged the city to implement."),
    ("The professor lectured on theory and the students debated the topic.",
     "That the professor lectured on theory inspired the students to debate."),
    ("The composer wrote the score and the orchestra rehearsed the piece.",
     "That the composer wrote the score required the orchestra to rehearse."),
    ("The farmer planted the crop and the buyer purchased the harvest.",
     "That the farmer planted the crop assured the buyer of a harvest."),
]


def main() -> int:
    log("step REV2/B1 · adversarial v3 (WC-matched pairs) begin")
    nlp = spacy.load("en_core_web_sm")
    rows = []
    for i, (low, high) in enumerate(PAIRS):
        m_low = metrics(low, nlp)
        m_high = metrics(high, nlp)
        rows.append({"pair_id": i, "condition": "low_friction",
                     "text": low, **m_low})
        rows.append({"pair_id": i, "condition": "high_friction",
                     "text": high, **m_high})
        log(f"step REV2/B1 · pair {i}: low WC={m_low['WC']} MCD={m_low['MCD']} "
            f"FRE={m_low['FRE']} | high WC={m_high['WC']} MCD={m_high['MCD']} "
            f"FRE={m_high['FRE']}")
    df = pd.DataFrame(rows)
    out_dir = HERE / "data" / "adversarial_v3"
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "results.csv", index=False)

    # paired Wilcoxon signed-rank on key metrics
    from scipy import stats
    low_df = df[df["condition"] == "low_friction"].set_index("pair_id")
    high_df = df[df["condition"] == "high_friction"].set_index("pair_id")
    summary = {}
    md_rows = []
    for met in ["WC", "FRE", "TTR", "MCD", "MaxCD", "MAL", "MaxArcCross",
                 "sylcount_per_word"]:
        a = low_df[met].astype(float).values
        b = high_df[met].astype(float).values
        if (a == b).all():
            stat, p = float("nan"), 1.0
        else:
            stat, p = stats.wilcoxon(a, b)
        mean_low = float(a.mean())
        mean_high = float(b.mean())
        delta = mean_high - mean_low
        summary[met] = {
            "mean_low": round(mean_low, 4),
            "mean_high": round(mean_high, 4),
            "delta_high_minus_low": round(delta, 4),
            "wilcoxon_W": float(stat) if not pd.isna(stat) else None,
            "wilcoxon_p": float(p),
        }
        md_rows.append(
            f"| {met} | {mean_low:.3f} | {mean_high:.3f} | "
            f"{delta:+.3f} | {p:.3e} |")
        log(f"step REV2/B1 · {met}: low={mean_low:.3f} high={mean_high:.3f} "
            f"delta={delta:+.3f} p={p:.3e}")

    md = ["# Adversarial v3 — WC-matched pairs (n = 25)",
          "",
          "Each pair contrasts a *low-friction* (two coordinated independent "
          "clauses) version against a *high-friction* (deeply nested complement "
          "clause) version. Pairs are matched on word count and use overlapping "
          "content vocabulary; only syntactic architecture differs.",
          "",
          "| Metric | Mean low | Mean high | $\\Delta$ (high − low) | "
          "Wilcoxon $p$ |",
          "|--------|----------|-----------|------------------------|--------|"]
    md.extend(md_rows)
    (out_dir / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2),
                                            encoding="utf-8")

    # figure: boxplot of FRE and MCD across the two conditions
    fig, axes = plt.subplots(1, 4, figsize=(13, 4), dpi=160)
    for ax, met, lbl in zip(axes,
                            ["WC", "FRE", "MCD", "MaxCD"],
                            ["Word Count", "Flesch Reading Ease",
                             "Mean Clausal Depth",
                             "Maximum Clausal Depth"]):
        a = df[df["condition"] == "low_friction"][met].astype(float)
        b = df[df["condition"] == "high_friction"][met].astype(float)
        ax.boxplot([a, b], labels=["low", "high"])
        ax.set_title(lbl, fontsize=10)
        ax.grid(True, linestyle=":", alpha=0.4)
    fig.suptitle("Adversarial v3: WC-matched pairs · low vs high friction",
                 fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(HERE / "figures" / "adversarial_v3.png",
                dpi=180, bbox_inches="tight")
    plt.close(fig)
    log("step REV2/B1 · wrote figures/adversarial_v3.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
