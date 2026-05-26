"""Convert manuscript.md to manuscript.pdf with proper LaTeX math rendering.

Pipeline:
  1. markdown -> HTML (tables, fenced_code)
  2. inject MathJax v3 script + double-spaced academic CSS into <head>
  3. embed images as base64 data URIs
  4. open HTML in headless chromium via playwright
  5. wait for MathJax to finish typesetting
  6. page.pdf() with letter, 1-inch margins
"""
from __future__ import annotations

import base64
import datetime as _dt
import io
import sys
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright


HERE = Path(__file__).resolve().parent
PROGRESS_LOG = HERE / "progress.log"

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              line_buffering=True)


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
    max-width: 6.5in;
    margin: 0 auto;
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
h4 {
    font-size: 12pt;
    font-style: italic;
    margin-top: 0.2in;
    margin-bottom: 0.08in;
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
    page-break-inside: avoid;
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
mjx-container { line-height: 1.3 !important; }
"""

MATHJAX_HEAD = """
<script>
window.MathJax = {
  tex: {
    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
    packages: {'[+]': ['ams']}
  },
  startup: {
    ready: function () {
      MathJax.startup.defaultReady();
      MathJax.startup.promise.then(function () {
        window.mathJaxDone = true;
      });
    }
  }
};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"
        id="MathJax-script" async></script>
"""


def strip_yaml(md_text: str) -> str:
    if md_text.startswith("---"):
        end = md_text.find("\n---", 4)
        if end != -1:
            return md_text[end + 4:].lstrip()
    return md_text


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="manuscript.md")
    ap.add_argument("--output", default="manuscript.pdf")
    args = ap.parse_args()
    log(f"step PDF-FIX/2 · loading {args.input}")
    md_path = HERE / args.input
    md_text = strip_yaml(md_path.read_text(encoding="utf-8"))

    log("step PDF-FIX/2 · markdown -> HTML")
    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code"],
    )

    log("step PDF-FIX/2 · embedding figures as base64")
    # Embed every PNG under figures/ so any image referenced in the
    # manuscript can be inlined without depending on filesystem paths.
    figures_dir = HERE / "figures"
    fnames = []
    if figures_dir.exists():
        fnames.extend(sorted(
            f"figures/{p.name}" for p in figures_dir.iterdir()
            if p.suffix.lower() == ".png"))
    fnames.append("metric_variance.png")
    for fname in fnames:
        fpath = HERE / fname
        if not fpath.exists():
            continue
        b64 = base64.b64encode(fpath.read_bytes()).decode("ascii")
        uri = f"data:image/png;base64,{b64}"
        html_body = html_body.replace(f'src="{fname}"', f'src="{uri}"')

    html = (
        "<!DOCTYPE html>\n"
        "<html><head><meta charset='utf-8'>"
        f"{MATHJAX_HEAD}"
        f"<style>{CSS}</style></head><body>"
        f"{html_body}"
        "</body></html>"
    )

    html_path = HERE / (Path(args.output).stem + ".html")
    html_path.write_text(html, encoding="utf-8")
    log(f"step PDF-FIX/2 · wrote {html_path.name}")

    log("step PDF-FIX/2 · launching chromium")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(viewport={"width": 920, "height": 1200})
            page = ctx.new_page()
            log("step PDF-FIX/2 · loading file in chromium")
            page.goto(html_path.as_uri(), wait_until="networkidle")
            log("step PDF-FIX/2 · waiting for MathJax mathJaxDone flag")
            page.wait_for_function(
                "() => window.mathJaxDone === true",
                timeout=30000,
            )
            page.wait_for_timeout(500)
            log("step PDF-FIX/2 · rendering pdf")
            pdf_path = HERE / args.output
            page.pdf(
                path=str(pdf_path),
                format="Letter",
                margin={"top": "1in", "right": "1in",
                        "bottom": "1in", "left": "1in"},
                print_background=True,
                prefer_css_page_size=True,
            )
            log(f"step PDF-FIX/2 · wrote {pdf_path.name}")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
