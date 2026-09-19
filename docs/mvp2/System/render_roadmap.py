"""Generate docs16 from docs15. Documentation only; standard library, no network."""
from __future__ import annotations

import argparse
import hashlib
import html
from pathlib import Path
import re


DOCS = Path(__file__).resolve().parents[2]
SOURCE = DOCS / "15-Продуктовая-дорожная-карта.md"
OUTPUT = DOCS / "16-Управленческая-карта-разработки.html"
TOKEN = re.compile(r"\x60([^\x60]+)\x60|\[([^\]]+)\]\(([^)]+)\)|\*\*(.+?)\*\*")


def inline(value: str) -> str:
    """Escape all prose; render only code, links and strong emphasis."""
    parts = []
    end = 0
    for match in TOKEN.finditer(value):
        parts.append(html.escape(value[end:match.start()]))
        code, label, url, strong = match.groups()
        if code is not None:
            parts.append("<code>" + html.escape(code) + "</code>")
        elif url is not None:
            # Only local relative paths, anchors and HTTPS links belong in this document.
            if (":" in url and not url.startswith("https://")) or url.startswith(("//", "\\")):
                raise ValueError("Unsupported link scheme")
            parts.append('<a href="' + html.escape(url, quote=True) + '">' + inline(label) + "</a>")
        else:
            parts.append("<strong>" + inline(strong) + "</strong>")
        end = match.end()
    return "".join(parts) + html.escape(value[end:])


def markdown(source: str) -> tuple[str, str, str]:
    """Render the small Markdown subset used by the canonical roadmap."""
    lines = source.splitlines()
    body, toc = [], []
    title = ""
    index = 0
    section = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        heading = re.match(r"^(#{1,3}) (.+)$", line)
        if heading:
            level = len(heading[1])
            if level == 1:
                title = heading[2]
            else:
                section += 1
                anchor = "section-" + str(section)
                body.append(f'<h{level} id="{anchor}">{inline(heading[2])}</h{level}>')
                if level == 2:
                    toc.append(f'<li><a href="#{anchor}">{inline(heading[2])}</a></li>')
            index += 1
            continue
        if line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                    rows.append(cells)
                index += 1
            if not rows or any(len(row) != len(rows[0]) for row in rows):
                raise ValueError("Malformed Markdown table")
            header = "".join('<th scope="col">' + inline(cell) + "</th>" for cell in rows[0])
            data = "".join("<tr>" + "".join("<td>" + inline(cell) + "</td>" for cell in row) + "</tr>" for row in rows[1:])
            body.append('<div class="table-scroll" tabindex="0" role="region" aria-label="Таблица"><table><thead><tr>' + header + "</tr></thead><tbody>" + data + "</tbody></table></div>")
            continue
        item = re.match(r"^(-|\d+\.) (.+)$", line)
        if item:
            ordered = item[1] != "-"
            tag = "ol" if ordered else "ul"
            items = []
            while index < len(lines):
                item = re.match(r"^(-|\d+\.) (.+)$", lines[index].strip())
                if not item or (item[1] != "-") != ordered:
                    break
                words = [item[2]]
                index += 1
                while index < len(lines) and lines[index].startswith("  ") and lines[index].strip():
                    words.append(lines[index].strip())
                    index += 1
                items.append("<li>" + inline(" ".join(words)) + "</li>")
            body.append("<" + tag + ">" + "".join(items) + "</" + tag + ">")
            continue
        paragraph = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(r"^(#{1,3} |[|]|- |\d+\. )", lines[index].strip()):
            paragraph.append(lines[index].strip())
            index += 1
        body.append("<p>" + inline(" ".join(paragraph)) + "</p>")
    if not title:
        raise ValueError("A document title is required")
    return title, "\n".join(body), "\n".join(toc)


STYLE = """
:root{--ink:#073d40;--accent:#a0ded4;--paper:#f3f7f5;--muted:#455b5b;--line:#cbd9d5}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}
body{margin:0;background:var(--paper);color:var(--ink);font:17px/1.6 "Helvetica Neue",Arial,sans-serif;overflow-wrap:anywhere}
a{color:#085d60;text-underline-offset:.2em;text-decoration-thickness:1px}
a:hover{text-decoration-thickness:2px}a:focus-visible,.table-scroll:focus-visible{outline:3px solid #146d76;outline-offset:4px}
.skip{position:absolute;top:-100px;left:20px;padding:10px;background:white;z-index:2}.skip:focus{top:10px}
.hero{background:var(--ink);color:white;padding:60px max(24px,calc((100vw - 1260px)/2))}
.brand{display:flex;align-items:center;gap:14px;font-size:14px;letter-spacing:.13em;text-transform:uppercase}
.brand span{font-size:44px;line-height:1;color:var(--accent);letter-spacing:0}
h1{font-size:clamp(32px,4.8vw,60px);max-width:870px;line-height:1.08;letter-spacing:-.035em;font-weight:500;margin:32px 0 24px}
.hero p{max-width:790px;color:#d4e8e3;margin:0}
.layout{max-width:1324px;margin:auto;padding:40px 32px 80px;display:grid;grid-template-columns:245px minmax(0,1fr);gap:44px}
nav{font-size:14px;align-self:start;position:sticky;top:24px}
nav p{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
nav ul{list-style:none;padding:0;margin:0}nav li{border-top:1px solid var(--line)}
nav a{display:block;padding:10px 0;text-decoration:none}
main{min-width:0}h2{font-size:29px;line-height:1.2;letter-spacing:-.02em;margin:52px 0 20px;padding-top:20px;border-top:2px solid var(--ink);font-weight:500}
h3{font-size:21px;font-weight:600;margin:32px 0 16px}
p{margin:0 0 20px}strong{font-weight:650}li{margin:0 0 10px}main>ul,main>ol{padding-left:24px}
main>p:first-child{background:#d6ebe4;border-left:4px solid #17656a;padding:22px;border-radius:0 12px 12px 0}
main>h2:first-child{margin-top:0}code{font: .84em/1.5 Consolas,monospace;overflow-wrap:anywhere;background:#e3ebe8;padding:2px 4px;border-radius:3px}
.table-scroll{width:100%;overflow-x:auto;margin:24px 0 30px;border:1px solid var(--line);border-radius:12px;background:white}
table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.5}
th{text-align:left;background:#e0eeea;font-weight:600;color:var(--ink)}
th,td{padding:14px 16px;vertical-align:top;border-bottom:1px solid var(--line);overflow-wrap:anywhere}
td:first-child{font-weight:550;min-width:95px}tr:last-child td{border-bottom:0}
footer{border-top:1px solid var(--line);padding:24px 32px 40px;max-width:1324px;margin:auto;color:var(--muted);font-size:13px;overflow-wrap:anywhere}
@media(max-width:900px){.layout{display:block;padding:28px 24px 50px}nav{position:static;margin-bottom:32px}nav ul{display:grid;grid-template-columns:1fr 1fr;gap:0 24px}.hero{padding:40px 24px}h2{font-size:26px}}
@media(max-width:480px){body{font-size:16px}.layout{padding:24px 16px 44px}.hero{padding:32px 16px}.hero h1{margin-top:24px}nav ul{display:block}th,td{padding:10px 9px;font-size:13px}h2{font-size:25px}footer{padding:20px 16px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{@page{size:A4;margin:16mm}body{background:white;color:#122e31;font-size:10pt}.hero{background:white;color:#122e31;padding:0 0 12mm}.hero p{color:#455b5b}.brand{font-size:10pt}.brand span{color:#122e31}h1{font-size:28pt;max-width:none}nav,.skip{display:none}.layout{display:block;padding:0;max-width:none}h2{font-size:17pt;margin-top:10mm;break-after:avoid}h3{font-size:13pt;break-after:avoid}p,li{orphans:3;widows:3}.table-scroll{overflow:visible;border-radius:0}table{font-size:8pt}th,td{padding:6px 8px}tr{break-inside:avoid}code{overflow-wrap:anywhere}footer{padding:6mm 0 0;font-size:8pt}a{color:inherit}*{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
"""


def render() -> str:
    # LF normalization keeps the content binding stable across Windows checkouts.
    raw = SOURCE.read_text(encoding="utf-8-sig").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    title, body, toc = markdown(raw.decode("utf-8-sig"))
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="roadmap-source-sha256" content="{digest}">
<meta name="color-scheme" content="light"><title>{html.escape(title)}</title>
<style>{STYLE}</style></head><body>
<a class="skip" href="#content">К содержанию</a>
<header class="hero"><div class="brand"><span aria-hidden="true">∞</span>Nobus Space · PROстранство</div>
<h1>{html.escape(title)}</h1>
<p>От принятого MVP1 к следующему этапу. Границы продукта, последовательность Gate и правила документации.</p></header>
<div class="layout"><nav aria-label="Разделы дорожной карты"><p>Содержание</p><ul>{toc}</ul></nav>
<main id="content">{body}</main></div>
<footer>Производная канонического <a href="{html.escape(SOURCE.name)}">Markdown</a>.
Статусы берутся из исходника; HTML не изменяется вручную.<br>
SHA256 исходника (UTF-8, LF): <code>{digest}</code><br>
Оформление документа следует архивным ориентирам бренда и не является утверждением дизайна будущего MVP2.</footer>
</body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check generated content with LF normalization, without writing")
    args = parser.parse_args()
    expected = render().encode("utf-8")
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8").encode("utf-8") != expected:
            print("FAIL: docs16 does not match docs15; regenerate it")
            return 1
        print("PASS: docs16 matches docs15")
    else:
        OUTPUT.write_bytes(expected)
        print("Generated " + OUTPUT.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
