#!/usr/bin/env python3
"""
Renders docs/PRIVACY_POLICY.md as the standalone page published at a public URL.

Both browser stores require a privacy policy at an HTTPS address anyone can
open without signing in. This turns the policy in the repository into one
self-contained HTML file, so the published page cannot say something different
from the document the tests check.

The renderer understands only the constructs this document uses, and raises on
anything else rather than skipping it. That is the point: a renderer that
quietly dropped a line it did not recognise would publish a policy with a
clause missing, and nobody would see it happen. Run with --check to verify the
committed page is current without writing.

    python3 tools/build_privacy_page.py            # write release/privacy.html
    python3 tools/build_privacy_page.py --check     # exit 1 if it is stale
"""

import argparse
import html
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOURCE = os.path.join(REPO, "docs", "PRIVACY_POLICY.md")
TARGET = os.path.join(REPO, "release", "privacy.html")

# Inline markup, applied to already-escaped text.
INLINE = (
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), r'<a href="\2">\1</a>'),
)


def inline(text):
    out = html.escape(text, quote=False)
    for pattern, replacement in INLINE:
        out = pattern.sub(replacement, out)
    if "**" in out or re.search(r"(?<!\\)`", out):
        raise ValueError(f"unclosed inline markup: {text!r}")
    return out


def _table(lines, start):
    """A GitHub pipe table. Returns (html, index after the table)."""
    def cells(row):
        return [cell.strip() for cell in row.strip().strip("|").split("|")]

    head = cells(lines[start])
    if start + 1 >= len(lines) or not re.fullmatch(r"\|[\s|:-]+\|", lines[start + 1].strip()):
        raise ValueError(f"table at line {start + 1} has no divider row")
    index = start + 2
    body = []
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        body.append(cells(lines[index]))
        index += 1
    out = ["<table>", "<thead><tr>"]
    out += [f"<th>{inline(cell)}</th>" for cell in head]
    out.append("</tr></thead><tbody>")
    for row in body:
        if len(row) != len(head):
            raise ValueError(f"table row has {len(row)} cells for {len(head)} columns: {row!r}")
        out.append("<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out), index


def render(markdown):
    lines = markdown.split("\n")
    out = []
    index = 0
    paragraph = []
    list_items = None
    list_tag = None

    def flush():
        nonlocal paragraph, list_items, list_tag
        if paragraph:
            out.append("<p>" + inline(" ".join(paragraph)) + "</p>")
            paragraph = []
        if list_items is not None:
            out.append(f"<{list_tag}>")
            # extend, not `+=`: an augmented assignment here would make `out`
            # local to this function and the whole render would fail.
            out.extend(f"<li>{inline(item)}</li>" for item in list_items)
            out.append(f"</{list_tag}>")
            list_items, list_tag = None, None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            flush()
            index += 1
            continue
        if stripped.startswith("<!--"):
            index += 1
            continue
        if stripped == "---":
            flush()
            out.append("<hr>")
            index += 1
            continue
        heading = re.match(r"(#{1,4})\s+(.*)$", stripped)
        if heading:
            flush()
            level = len(heading.group(1))
            out.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            index += 1
            continue
        if stripped.startswith("|"):
            flush()
            table, index = _table(lines, index)
            out.append(table)
            continue
        if stripped.startswith(">"):
            flush()
            note = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                text = lines[index].strip().lstrip(">").strip()
                if text and text != "[!NOTE]":
                    note.append(text)
                index += 1
            out.append('<blockquote><p>' + inline(" ".join(note)) + "</p></blockquote>")
            continue
        bullet = re.match(r"[-*]\s+(.*)$", stripped)
        numbered = re.match(r"\d+\.\s+(.*)$", stripped)
        if bullet or numbered:
            wanted = "ul" if bullet else "ol"
            if list_items is None:
                if paragraph:
                    out.append("<p>" + inline(" ".join(paragraph)) + "</p>")
                    paragraph = []
                list_items, list_tag = [], wanted
            elif list_tag != wanted:
                flush()
                list_items, list_tag = [], wanted
            list_items.append((bullet or numbered).group(1))
            index += 1
            continue
        if list_items is not None and line.startswith(("  ", "\t")):
            # A wrapped list item.
            list_items[-1] += " " + stripped
            index += 1
            continue
        if re.match(r"^[A-Za-z(*`\[\"]|^\d", stripped):
            paragraph.append(stripped)
            index += 1
            continue
        raise ValueError(f"line {index + 1} is not a construct this renderer knows: {line!r}")

    flush()
    return "\n".join(out)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Privacy policy: Inox Hydra Bridge</title>
<meta name="description" content="What the Inox Hydra Bridge browser extension reads, where it goes, and what is kept. It has no server.">
<meta name="robots" content="index, follow">
<style>
:root {{
  color-scheme: light dark;
  --paper: #fcfcfa; --ink: #1b1b19; --muted: #5c5c57;
  --edge: #dedcd6; --soft: #f3f2ee; --link: #1f5f4f;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --paper: #17171a; --ink: #e9e8e4; --muted: #a3a29c;
    --edge: #32323a; --soft: #202026; --link: #76c2ac;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--paper); color: var(--ink);
  font: 16px/1.65 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  -webkit-text-size-adjust: 100%;
}}
main {{ max-width: 46rem; margin: 0 auto; padding: 3rem 16px 6rem; }}
h1 {{ font-size: 1.75rem; line-height: 1.25; margin: 0 0 1rem; letter-spacing: -0.01em; }}
h2 {{ font-size: 1.2rem; margin: 2.75rem 0 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--edge); }}
h3 {{ font-size: 1rem; margin: 1.75rem 0 0.5rem; }}
h4 {{ font-size: 0.95rem; margin: 1.25rem 0 0.5rem; color: var(--muted); }}
p, li {{ margin: 0 0 0.9rem; }}
ul, ol {{ padding-left: 1.4rem; margin: 0 0 1rem; }}
a {{ color: var(--link); }}
code {{
  background: var(--soft); border: 1px solid var(--edge); border-radius: 4px;
  padding: 0.05em 0.3em; font: 0.875em/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow-wrap: anywhere;
}}
hr {{ border: 0; border-top: 1px solid var(--edge); margin: 2.5rem 0; }}
blockquote {{
  margin: 1.25rem 0; padding: 0.75rem 1rem; background: var(--soft);
  border-left: 3px solid var(--edge); border-radius: 0 6px 6px 0;
}}
blockquote p {{ margin: 0; }}
table {{ width: 100%; border-collapse: collapse; margin: 1.25rem 0; font-size: 0.925rem; display: block; overflow-x: auto; }}
th, td {{ border: 1px solid var(--edge); padding: 0.55rem 0.7rem; text-align: left; vertical-align: top; }}
th {{ background: var(--soft); font-weight: 600; }}
footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--edge); color: var(--muted); font-size: 0.875rem; }}
</style>
</head>
<body>
<main>
{body}
<footer>
<p>Inox Hydra is a program that runs on your own computer. This page is generated from
<code>docs/PRIVACY_POLICY.md</code> in the project's source, by <code>tools/build_privacy_page.py</code>.</p>
</footer>
</main>
</body>
</html>
"""


def build():
    with open(SOURCE, encoding="utf-8") as handle:
        markdown = handle.read()
    if "—" in markdown:
        raise ValueError("the policy contains an em-dash, which this project does not use")
    return PAGE.format(body=render(markdown))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if the committed page is not what the source renders to")
    args = parser.parse_args()
    page = build()
    if args.check:
        if not os.path.exists(TARGET):
            print(f"{TARGET} does not exist; run this without --check", file=sys.stderr)
            return 1
        with open(TARGET, encoding="utf-8") as handle:
            if handle.read() != page:
                print("release/privacy.html is stale: docs/PRIVACY_POLICY.md has changed since it "
                      "was built. Run python3 tools/build_privacy_page.py", file=sys.stderr)
                return 1
        print("release/privacy.html is current")
        return 0
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    with open(TARGET, "w", encoding="utf-8") as handle:
        handle.write(page)
    print(f"wrote {os.path.relpath(TARGET, REPO)} ({len(page):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
