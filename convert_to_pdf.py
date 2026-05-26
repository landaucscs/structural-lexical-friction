"""Convert manuscript.md to manuscript.pdf via markdown -> HTML -> xhtml2pdf.

Produces a double-spaced 12pt 1-inch-margin layout suitable for review
submission.  Math is rendered as inline plain text (xhtml2pdf does not
ship a TeX renderer); the source LaTeX is preserved in the .md file for
journal-style rendering downstream.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import markdown
from xhtml2pdf import pisa


HERE = Path(__file__).resolve().parent
PROGRESS_LOG = HERE / "progress.log"


def log(label: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {label}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


CSS = """
@page {
    size: letter;
    margin: 1in;
}
body {
    font-family: 'Times New Roman', Georgia, serif;
    font-size: 12pt;
    line-height: 2.0;
    color: #111;
}
h1 {
    font-size: 18pt;
    text-align: center;
    line-height: 1.4;
    margin-top: 0.4in;
    margin-bottom: 0.3in;
}
h2 {
    font-size: 14pt;
    margin-top: 0.35in;
    margin-bottom: 0.15in;
    line-height: 1.4;
}
h3 {
    font-size: 12pt;
    font-weight: bold;
    margin-top: 0.25in;
    margin-bottom: 0.1in;
    line-height: 1.4;
}
p { margin-top: 0; margin-bottom: 0.12in; text-align: justify; }
blockquote {
    margin-left: 0.35in;
    margin-right: 0.35in;
    font-style: italic;
    border-left: 2px solid #888;
    padding-left: 0.18in;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.18in 0;
    font-size: 10pt;
    line-height: 1.4;
}
th, td {
    border: 1px solid #888;
    padding: 4px 6px;
    text-align: left;
    vertical-align: top;
}
th { background-color: #eee; }
img { max-width: 100%; height: auto; display: block; margin: 0.15in auto; }
code {
    font-family: 'Courier New', monospace;
    font-size: 10pt;
    background: #f4f4f4;
    padding: 1px 3px;
}
pre {
    font-family: 'Courier New', monospace;
    font-size: 10pt;
    background: #f4f4f4;
    padding: 6px;
    line-height: 1.4;
}
hr { border: none; border-top: 1px solid #888; margin: 0.25in 0; }
"""


def strip_yaml(md_text: str) -> str:
    if md_text.startswith("---"):
        end = md_text.find("\n---", 4)
        if end != -1:
            return md_text[end + 4:].lstrip()
    return md_text


def main() -> int:
    log("step 8/8 · loading manuscript.md")
    md_path = HERE / "manuscript.md"
    md_text = strip_yaml(md_path.read_text(encoding="utf-8"))

    log("step 8/8 · converting markdown -> html")
    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code"],
    )

    # embed figures as base64 data URIs (avoids file:// URI parsing issues
    # caused by spaces in the working directory path)
    import base64
    for fname in [
        "figures/roc_curves.png",
        "figures/feature_importance.png",
        "figures/adversarial_transform.png",
        "metric_variance.png",  # legacy
    ]:
        fpath = HERE / fname
        if not fpath.exists():
            continue
        b64 = base64.b64encode(fpath.read_bytes()).decode("ascii")
        uri = f"data:image/png;base64,{b64}"
        html_body = html_body.replace(f'src="{fname}"', f'src="{uri}"')

    html = (
        "<!DOCTYPE html>\n"
        "<html><head><meta charset='utf-8'>"
        f"<style>{CSS}</style></head><body>"
        f"{html_body}"
        "</body></html>"
    )

    html_path = HERE / "manuscript.html"
    html_path.write_text(html, encoding="utf-8")
    log(f"step 8/8 · wrote {html_path.name}")

    log("step 8/8 · rendering pdf via xhtml2pdf")
    pdf_path = HERE / "manuscript.pdf"
    with pdf_path.open("wb") as f:
        pisa_status = pisa.CreatePDF(html, dest=f, encoding="utf-8")
    if pisa_status.err:
        log(f"step 8/8 · pdf conversion ERRORS={pisa_status.err}")
        return 1
    log(f"step 8/8 · wrote {pdf_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
