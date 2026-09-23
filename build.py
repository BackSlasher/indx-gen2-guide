#!/usr/bin/env python3
"""Unified Prusa CORE One/+ INDX conversion + CORE One+ Gen 2 upgrade guide.

Flattens Prusa's two manuals into a single page in the order prescribed by
Prusa's companion article, with the article's own notes inlined at the exact
step they apply to. Content and photos belong to Prusa Research; photos are
hot-linked from help.prusa3d.com, not copied.

Usage (stdlib only):
    python build.py fetch   # download bundles + article into data/
    python build.py build   # render data/ -> index.html
    python build.py check   # re-download and report what Prusa changed since data/
    python build.py         # fetch + build
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
OUT = HERE / "full.html"  # every step, flattened
MAP_OUT = HERE / "index.html"  # the switch map: hand-offs and notes only
BASE = "https://help.prusa3d.com"
UA = {"User-Agent": "Mozilla/5.0 (unified-indx-guide build script)"}

ARTICLE_SLUG = "assemblling-the-prusa-indx-core-one-with-the-gen-2-upgrade_1147602"

INDX = {
    1: "1-introduction_1096223",
    2: "2-printer-preparation-disassembly_1096231",
    3: "3-z-axis-upgrade_1096239",
    4: "4-indx-toolhead-side-filament-sensors_1096247",
    5: "5-spoolholders-tool-dock-assembly_1096255",
    6: "6-preflight-check_1096263",
}
GEN2 = {
    1: "1-introduction_1110653",
    2: "2-printer-disassembly_1110664",
    3: "3-belts-upgrade_1110672",
    4: "4-heatbed-upgrade_1110680",
    5: "5-preflight-check_1110689",
}
SOURCES = {"indx": ("INDX", INDX), "gen2": ("GEN 2", GEN2)}

# ---------------------------------------------------------------------------
# The route. Straight from the companion article. Step numbers are 1-based and
# inclusive, matching the numbering on help.prusa3d.com.
#   ("indx"|"gen2", chapter, first, last)  -> run of manual steps
#   ("article", n)                          -> the n-th <h3> section of the article
# ---------------------------------------------------------------------------
ROUTE = [
    ("article", 0),  # intro paragraphs (before the first h3)
    ("indx", 1, 1, 14),
    ("indx", 2, 1, 36),
    ("indx", 3, 1, 10),
    ("article", 1),  # Securing the bed spacer - right, additional information
    ("indx", 3, 11, 19),
    ("article", 2),  # Removing old expansion joints
    ("gen2", 4, 4, 8),
    ("article", 3),  # Removing the Bed-cable-cover-bottom
    ("indx", 3, 20, 39),
    ("indx", 4, 1, 3),
    ("article", 4),  # Additional information and removing the belts
    ("gen2", 3, 4, 38),
    ("article", 5),  # Gantry aligner tool
    ("indx", 4, 4, 52),
    ("article", 6),  # Mounting the side panels, PTFE and right cover
    ("indx", 4, 53, 71),
    ("indx", 5, 1, 17),
    ("article", 7),  # Fixing the heatbed
    ("gen2", 4, 11, 20),
    ("article", 8),  # Mounting the left cover, covering the electronics
    ("indx", 5, 18, 104),
    ("indx", 6, 1, 26),
]

# Extra flags on individual steps, derived from the article text.
FLAGS = {
    ("indx", 4, 12): (
        "skip",
        "SKIP. The companion article has you lubricate both M3x30 belt-tensioner "
        "screws earlier, during the Gen 2 belt exchange, and says to skip this step "
        "when it appears here.",
    ),
    ("gen2", 3, 18): (
        "note",
        "Companion article: the Bowden-guide is not needed for the INDX conversion. "
        "You can leave it off once it is detached from the motor mount.",
    ),
    ("indx", 3, 17): (
        "note",
        "Companion article: insert the M3x10 screw but tighten it only a few turns. "
        "It is fully tightened after the Gen 2 expansion joints are aligned.",
    ),
    ("indx", 3, 25): (
        "note",
        "Companion article: tighten the heatbed screws two turns only. Final "
        "tightening happens in the Gen 2 'Fixing the heatbed' step later on this page.",
    ),
}

# Steps Prusa's route never visits but you may still want to look at.
APPENDIX = [("gen2", 5, 1, 8)]
APPENDIX_NOTE = (
    "Prusa's companion article never routes you into the Gen 2 preflight chapter; "
    "the INDX preflight (chapter 6 above) covers firmware, belt tensioning and the "
    "selftest. Listed here so you can check whether anything Gen 2-specific, in "
    "particular 'Changing the printer edition', still applies to an INDX printer."
)

# ---------------------------------------------------------------------------
# fetching
# ---------------------------------------------------------------------------

def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def fetch_bundle(slug: str) -> dict:
    raw = json.loads(http_get(f"{BASE}/edge/guide-bundle?locale=en&slug={slug}"))["data"]
    g = raw["guide"]
    steps = []
    for st in raw["steps"]:
        lines = []
        for ln in st.get("lines", []):
            meta = ln.get("meta") or {}
            if isinstance(meta, list):
                meta = {}
            lines.append(
                {
                    "html": ln.get("title", ""),
                    "color": meta.get("color"),
                    "icon": meta.get("icon"),
                    "level": meta.get("level") or 0,
                }
            )
        gallery = []
        media = st.get("media") or {}
        if isinstance(media, dict):
            for im in media.get("gallery") or []:
                # Prusa annotates photos (markers, crossed-out items) as a
                # separate "_painted" file stored under `child`; the site shows
                # that one when present. Prefer it.
                if isinstance(im.get("child"), dict) and im["child"].get("original"):
                    im = im["child"]
                gallery.append(
                    {
                        "original": im.get("original"),
                        "large": im.get("large") or im.get("original"),
                        "srcset": im.get("srcset", ""),
                    }
                )
        steps.append(
            {
                "id": st["id"],
                "title": st["title"],
                "updated": st["updated"],
                "lines": lines,
                "gallery": gallery,
            }
        )
    return {
        "slug": slug,
        "title": g["title"],
        "manual": raw["category"]["title"],
        "manual_slug": raw["category"]["slug"],
        "difficulty": (g.get("meta") or {}).get("difficulty"),
        "updated": g["updated"],
        "steps": steps,
    }


def fetch_article() -> dict:
    page = http_get(f"{BASE}/article/{ARTICLE_SLUG}")
    end = page.find("to finish the conversion")
    if end < 0:
        raise SystemExit("article body not found; Prusa changed the page layout")
    h1 = page.rfind("<h1", 0, end)
    stop = page.find('data-sentry-element="FeedbackWrapper"', end)
    stop = page.rfind("<div", 0, stop)
    body = page[h1:stop]
    body = re.sub(r"<style[^>]*>.*?</style>", "", body, flags=re.S)
    m = re.search(r'last_original_modified\\?":\\?"(\d{4}-\d\d-\d\d[^"\\]*)', page)
    modified = m.group(1) if m else "unknown"
    # keep only from the first real paragraph
    first = body.find("<p")
    while first >= 0 and "received your" not in strip_tags(body[first : body.find("</p>", first)]):
        first = body.find("<p", first + 2)
    body = body[first:]
    parts = re.split(r"(?=<h3)", body)
    sections = []
    for i, part in enumerate(parts):
        title = ""
        if part.startswith("<h3"):
            title = strip_tags(re.match(r"<h3[^>]*>(.*?)</h3>", part, re.S).group(1))
            part = part[part.find("</h3>") + 5 :]
        sections.append({"title": title, "html": clean_article_html(part)})
    return {"modified": modified, "sections": sections, "sha": hashlib.sha1(body.encode()).hexdigest()}


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def clean_article_html(s: str) -> str:
    s = re.sub(r"<svg.*?</svg>", "", s, flags=re.S)
    s = re.sub(r'\s(?:data-[\w-]+|class|style|decoding|loading|width|height|target|rel)="[^"]*"', "", s)
    s = re.sub(r"<span>\s*</span>", "", s)
    s = re.sub(r'href="/', f'href="{BASE}/', s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"<p>\s*</p>", "", s)
    return s.strip()


def cmd_fetch() -> None:
    DATA.mkdir(exist_ok=True)
    for key, (_, chapters) in SOURCES.items():
        for ch, slug in chapters.items():
            b = fetch_bundle(slug)
            (DATA / f"{key}-{ch}.json").write_text(json.dumps(b, ensure_ascii=False, indent=1))
            print(f"fetched {key} ch{ch}: {b['title']} ({len(b['steps'])} steps)")
    a = fetch_article()
    (DATA / "article.json").write_text(json.dumps(a, ensure_ascii=False, indent=1))
    print(f"fetched article ({len(a['sections'])} sections, modified {a['modified']})")
    (DATA / "fetched_at.txt").write_text(dt.datetime.now(dt.timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# freshness check
# ---------------------------------------------------------------------------

def cmd_check() -> int:
    changed = 0
    for key, (label, chapters) in SOURCES.items():
        for ch, slug in chapters.items():
            old = json.loads((DATA / f"{key}-{ch}.json").read_text())
            new = fetch_bundle(slug)
            o = {s["id"]: s for s in old["steps"]}
            n = {s["id"]: s for s in new["steps"]}
            for sid in n.keys() - o.keys():
                print(f"NEW    {label} ch{ch}: {n[sid]['title']}")
                changed += 1
            for sid in o.keys() - n.keys():
                print(f"GONE   {label} ch{ch}: {o[sid]['title']}")
                changed += 1
            if [s["id"] for s in old["steps"]] != [s["id"] for s in new["steps"] if s["id"] in o]:
                print(f"REORDER {label} ch{ch}")
                changed += 1
            for sid in o.keys() & n.keys():
                a, b = o[sid], n[sid]
                what = []
                if a["title"] != b["title"]:
                    what.append("title")
                if [l["html"] for l in a["lines"]] != [l["html"] for l in b["lines"]]:
                    what.append("text")
                if [g["original"] for g in a["gallery"]] != [g["original"] for g in b["gallery"]]:
                    what.append("photos")
                if what:
                    print(f"CHANGED {label} ch{ch} '{b['title']}': {', '.join(what)} (updated {b['updated']})")
                    changed += 1
                elif a["updated"] != b["updated"]:
                    print(f"touched {label} ch{ch} '{b['title']}' (no visible change, updated {b['updated']})")
    old_a = json.loads((DATA / "article.json").read_text())
    new_a = fetch_article()
    if old_a["sha"] != new_a["sha"]:
        print(f"CHANGED companion article (modified {new_a['modified']})")
        changed += 1
    print(f"\n{changed} substantive change(s). Run `build.py` to refresh." if changed else "\nUp to date.")
    return 1 if changed else 0


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

COLORS = {
    "red": "#e53935",
    "orange": "#fb8c00",
    "yellow": "#f4c20d",
    "green": "#43a047",
    "blue": "#1e88e5",
    "light_blue": "#4fc3f7",
    "violet": "#8e24aa",
}
ICON_LABEL = {"note": "Note", "caution": "Caution", "reminder": "Reminder"}


def absolutize(s: str) -> str:
    return re.sub(r'href="/', f'href="{BASE}/', s)


def render_line(ln: dict) -> str:
    cls = ["line"]
    style = ""
    if ln["level"]:
        cls.append("lvl1")
    if ln["icon"] in ICON_LABEL:
        cls.append("ic-" + ln["icon"])
        marker = f'<span class="ic">{ICON_LABEL[ln["icon"]]}</span>'
    elif ln["color"] in COLORS:
        marker = f'<span class="dot" style="background:{COLORS[ln["color"]]}"></span>'
    else:
        marker = '<span class="dot plain"></span>'
    return f'<li class="{" ".join(cls)}"{style}>{marker}<span class="t">{absolutize(ln["html"])}</span></li>'


def render_step(num: int, src: str, ch: int, idx: int, total: int, step: dict, chapter: dict) -> str:
    label = SOURCES[src][0]
    orig = f"{BASE}/guide/{chapter['slug']}#{step['id']}"
    flag = FLAGS.get((src, ch, idx))
    imgs = "".join(
        f'<a href="{g["original"]}" target="_blank" rel="noopener">'
        f'<img loading="lazy" src="{g["large"]}" srcset="{html.escape(g["srcset"])}" '
        f'sizes="(max-width: 700px) 100vw, 45vw" alt=""></a>'
        for g in step["gallery"]
    )
    lines = "".join(render_line(l) for l in step["lines"])
    flag_html = ""
    if flag:
        flag_html = f'<div class="flag flag-{flag[0]}">{html.escape(flag[1])}</div>'
    skip = " skip" if flag and flag[0] == "skip" else ""
    return f"""
<section class="step {src}{skip}" id="s{num}" data-n="{num}">
 <header>
  <label class="chk"><input type="checkbox" data-n="{num}"><span class="num">{num}</span></label>
  <h3>{html.escape(step["title"])}</h3>
  <span class="badge {src}">{label} {ch}.{idx}</span>
  <a class="orig" href="{orig}" target="_blank" rel="noopener" title="Open this step on help.prusa3d.com">source ↗</a>
 </header>
 {flag_html}
 <div class="body">
  <div class="gallery">{imgs}</div>
  <ul class="lines">{lines}</ul>
 </div>
</section>"""


def render_article(sec: dict, n: int) -> str:
    title = sec["title"] or "Companion article: introduction"
    return f"""
<section class="article" id="a{n}">
 <header><span class="badge article">COMPANION ARTICLE</span><h3>{html.escape(title)}</h3>
 <a class="orig" href="{BASE}/article/{ARTICLE_SLUG}" target="_blank" rel="noopener">source ↗</a></header>
 <div class="body">{sec["html"]}</div>
</section>"""


def cmd_build() -> None:
    chapters = {
        (key, ch): json.loads((DATA / f"{key}-{ch}.json").read_text())
        for key, (_, chs) in SOURCES.items()
        for ch in chs
    }
    article = json.loads((DATA / "article.json").read_text())
    fetched_at = (DATA / "fetched_at.txt").read_text().strip()[:16].replace("T", " ") + " UTC"

    body: list[str] = []
    toc: list[str] = []
    num = 0
    for seg in ROUTE:
        if seg[0] == "article":
            sec = article["sections"][seg[1]]
            body.append(render_article(sec, seg[1]))
            toc.append(f'<li class="art"><a href="#a{seg[1]}">{html.escape(sec["title"] or "Article intro")}</a></li>')
            continue
        src, ch, first, last = seg
        chap = chapters[(src, ch)]
        total = len(chap["steps"])
        start_num = num + 1
        run = []
        for idx in range(first, last + 1):
            num += 1
            run.append(render_step(num, src, ch, idx, total, chap["steps"][idx - 1], chap))
        rng = f"{first}–{last}" if (first, last) != (1, total) else "all"
        body.append(
            f'<h2 class="chap {src}" id="c-{src}-{ch}-{first}">'
            f'<span class="badge {src}">{SOURCES[src][0]}</span> {html.escape(chap["title"])}'
            f' <small>steps {rng} of {total} · {html.escape(chap["difficulty"] or "")}</small></h2>'
        )
        body.extend(run)
        toc.append(
            f'<li class="{src}"><a href="#c-{src}-{ch}-{first}">{html.escape(chap["title"])}'
            f' <small>{rng}</small></a><span class="cnt" data-from="{start_num}" data-to="{num}"></span></li>'
        )
    total_steps = num

    appendix = [f'<h2 class="chap appendix" id="appendix">Appendix: not on Prusa\'s route</h2><p class="note">{html.escape(APPENDIX_NOTE)}</p>']
    anum = 0
    for src, ch, first, last in APPENDIX:
        chap = chapters[(src, ch)]
        for idx in range(first, last + 1):
            anum += 1
            appendix.append(
                render_step(0, src, ch, idx, len(chap["steps"]), chap["steps"][idx - 1], chap)
                .replace('id="s0"', f'id="x{anum}"')
                .replace('data-n="0"', 'data-n="x%d"' % anum)
                .replace('<span class="num">0</span>', '<span class="num">A</span>')
            )
    toc.append('<li class="appendix"><a href="#appendix">Appendix (Gen 2 preflight)</a></li>')

    latest = {
        label: max(chapters[(key, ch)]["steps"][i]["updated"] for ch in chs for i in range(len(chapters[(key, ch)]["steps"])))
        for key, (label, chs) in SOURCES.items()
    }
    fresh = " · ".join(f"{k} manual last edited {v[:10]}" for k, v in latest.items())
    fresh += f" · companion article modified {article['modified'][:10]}"

    page = TEMPLATE.replace("{{BODY}}", "\n".join(body + appendix))
    page = page.replace("{{TOC}}", "\n".join(toc))
    page = page.replace("{{TOTAL}}", str(total_steps))
    page = page.replace("{{FETCHED}}", fetched_at)
    page = page.replace("{{FRESH}}", fresh)
    page = page.replace("{{ARTICLE_URL}}", f"{BASE}/article/{ARTICLE_SLUG}")
    OUT.write_text(page)
    print(f"wrote {OUT} ({total_steps} steps, {len(page)//1024} KB)")

    page = render_map(chapters, article, fetched_at, fresh, total_steps)
    MAP_OUT.write_text(page)
    print(f"wrote {MAP_OUT} ({len(page)//1024} KB)")


def render_map(chapters: dict, article: dict, fetched_at: str, fresh: str, total_steps: int) -> str:
    """The switch map: one row per run of official-guide steps, the companion
    article's notes at each hand-off, and links into help.prusa3d.com."""
    rows: list[str] = []
    n = 0
    seg_no = 0
    for seg in ROUTE:
        if seg[0] == "article":
            sec = article["sections"][seg[1]]
            title = sec["title"] or "Before you start"
            rows.append(
                f'<details class="art" id="a{seg[1]}" open><summary><span class="badge article">ARTICLE</span> '
                f'{html.escape(title)}</summary><div class="body">{sec["html"]}</div></details>'
            )
            continue
        src, ch, first, last = seg
        chap = chapters[(src, ch)]
        total = len(chap["steps"])
        s_first, s_last = chap["steps"][first - 1], chap["steps"][last - 1]
        count = last - first + 1
        start_n, n = n + 1, n + count
        seg_no += 1
        guide = f"{BASE}/guide/{chap['slug']}"
        flags = []
        for idx in range(first, last + 1):
            f = FLAGS.get((src, ch, idx))
            if f:
                st = chap["steps"][idx - 1]
                flags.append(
                    f'<li class="flag-{f[0]}"><a href="{guide}#{st["id"]}" target="_blank" rel="noopener">'
                    f'step {idx} · {html.escape(st["title"])}</a>: {html.escape(f[1])}</li>'
                )
        flags_html = f'<ul class="flags">{"".join(flags)}</ul>' if flags else ""
        stop = (
            "finish the chapter"
            if last == total
            else f'stop after step {last} <a href="{guide}#{s_last["id"]}" target="_blank" rel="noopener">{html.escape(s_last["title"])}</a>'
        )
        rows.append(
            f"""<section class="seg {src}" id="g{seg_no}">
 <label class="chk"><input type="checkbox" data-n="g{seg_no}"></label>
 <div class="main">
  <div class="head"><span class="badge {src}">{SOURCES[src][0]}</span>
   <b>{html.escape(chap["title"])}</b>
   <span class="meta">steps {first}–{last} of {total} · {count} steps · {html.escape(chap["difficulty"] or "")}</span></div>
  <div class="go"><a class="btn" href="{guide}#{s_first["id"]}" target="_blank" rel="noopener">▶ Start at step {first}: {html.escape(s_first["title"])}</a>
   <span class="stop">then {stop}</span></div>
  {flags_html}
 </div>
 <span class="pos">{start_n}–{n}</span>
</section>"""
        )

    app = []
    for src, ch, first, last in APPENDIX:
        chap = chapters[(src, ch)]
        guide = f"{BASE}/guide/{chap['slug']}"
        items = "".join(
            f'<li><a href="{guide}#{chap["steps"][i-1]["id"]}" target="_blank" rel="noopener">{i}. {html.escape(chap["steps"][i-1]["title"])}</a></li>'
            for i in range(first, last + 1)
        )
        app.append(f'<p class="note">{html.escape(APPENDIX_NOTE)}</p><ul class="applist">{items}</ul>')

    page = MAP_TEMPLATE.replace("{{ROWS}}", "\n".join(rows))
    page = page.replace("{{APPENDIX}}", "\n".join(app))
    page = page.replace("{{SEGS}}", str(seg_no))
    page = page.replace("{{TOTAL}}", str(total_steps))
    page = page.replace("{{FETCHED}}", fetched_at)
    page = page.replace("{{FRESH}}", fresh)
    page = page.replace("{{ARTICLE_URL}}", f"{BASE}/article/{ARTICLE_SLUG}")
    return page


MAP_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>INDX + Gen 2 switch map</title>
<meta name="robots" content="noindex">
<style>
:root{--bg:#fafafa;--fg:#1a1a1a;--mut:#666;--line:#e2e2e2;--card:#fff;--indx:#e65100;--gen2:#1565c0;--art:#6a1b9a;--skip:#b71c1c;--done:#f1f8e9;--note:#e3f2fd}
@media (prefers-color-scheme: dark){:root{--bg:#141414;--fg:#e8e8e8;--mut:#9a9a9a;--line:#2c2c2c;--card:#1e1e1e;--done:#1b2a17;--note:#12263a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:inherit}
.top{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);padding:8px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.top h1{font-size:16px;margin:0;flex:1 1 auto}
.top .prog{color:var(--mut);font-variant-numeric:tabular-nums}
.top button{font:inherit;padding:4px 10px;border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:6px;cursor:pointer}
.wrap{max-width:860px;margin:0 auto;padding:16px}
p.note{color:var(--mut);font-size:14px}
.badge{display:inline-block;font-size:11px;font-weight:600;letter-spacing:.03em;padding:2px 7px;border-radius:4px;color:#fff;background:var(--mut);vertical-align:middle;white-space:nowrap}
.badge.indx{background:var(--indx)} .badge.gen2{background:var(--gen2)} .badge.article{background:var(--art)}
section.seg{display:flex;gap:12px;align-items:flex-start;background:var(--card);border:1px solid var(--line);border-left-width:5px;border-radius:10px;padding:12px 14px;margin:8px 0}
section.seg.indx{border-left-color:var(--indx)} section.seg.gen2{border-left-color:var(--gen2)}
section.seg.done{background:var(--done);opacity:.7}
section.seg.done .go,section.seg.done .flags{display:none}
.chk input{width:22px;height:22px;margin:2px 0 0;cursor:pointer}
.main{flex:1;min-width:0}
.head b{font-size:16px} .head .meta{color:var(--mut);font-size:13px;margin-left:6px}
.go{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center}
.btn{display:inline-block;padding:6px 12px;border-radius:6px;background:var(--fg);color:var(--bg);text-decoration:none;font-weight:600}
.stop{color:var(--mut)} .stop a{color:var(--fg)}
.pos{color:var(--mut);font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap}
ul.flags{margin:8px 0 0;padding:0 0 0 18px;font-size:14px}
ul.flags li{margin:4px 0} ul.flags li.flag-skip{color:var(--skip)} ul.flags li.flag-skip a{font-weight:600}
details.art{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--art);border-radius:10px;margin:14px 0;padding:0}
details.art summary{padding:10px 14px;cursor:pointer;font-weight:600;list-style:none}
details.art summary::before{content:"▸ ";color:var(--mut)} details.art[open] summary::before{content:"▾ "}
details.art .body{padding:0 14px 12px;font-size:14px}
details.art .body img{max-width:100%;height:auto;border-radius:6px}
details.art table{width:100%;border-collapse:collapse} details.art td{padding:4px;vertical-align:top}
h2{font-size:18px;margin:32px 0 8px}
ul.applist{padding-left:20px;font-size:14px}
footer{margin:40px 0 20px;color:var(--mut);font-size:13px;border-top:1px solid var(--line);padding-top:12px}
@media print{.top{display:none}details.art{break-inside:avoid}section.seg{break-inside:avoid}}
</style>
</head>
<body>
<div class="top">
 <h1>INDX + Gen 2 switch map</h1>
 <span class="prog"><b id="done">0</b> / {{SEGS}} segments</span>
 <button id="resume">Jump to current</button>
 <button id="reset">Reset</button>
</div>
<div class="wrap">
<p class="note">Follow the official guides on help.prusa3d.com, with their comments. This page only tells you <b>where to start, where to stop, and what to remember at each hand-off</b>, in the order Prusa's
<a href="{{ARTICLE_URL}}" target="_blank" rel="noopener">companion article</a> prescribes. Purple boxes are the article's own notes, verbatim. {{TOTAL}} steps in total.
Tick a segment when you finish it; progress is saved in this browser. <a href="full.html">Fully flattened version</a> (every step and photo, no comments).</p>
{{ROWS}}
<h2 id="appendix">Not on Prusa's route</h2>
{{APPENDIX}}
<footer>
Companion article text © Prusa Research a.s., reproduced for personal use. Snapshot {{FETCHED}}. {{FRESH}}.
Prusa still edits these manuals; run <code>build.py check</code> to see what changed.
</footer>
</div>
<script>
(function(){
 const KEY='indx-gen2-map';
 let state={};
 try{state=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){state={}}
 const boxes=[...document.querySelectorAll('input[type=checkbox][data-n]')];
 function save(){try{localStorage.setItem(KEY,JSON.stringify(state))}catch(e){}}
 function apply(){let d=0;boxes.forEach(b=>{const on=!!state[b.dataset.n];b.checked=on;b.closest('section').classList.toggle('done',on);if(on)d++});document.getElementById('done').textContent=d}
 boxes.forEach(b=>b.addEventListener('change',()=>{state[b.dataset.n]=b.checked;save();apply()}));
 document.getElementById('resume').onclick=()=>{const s=boxes.find(b=>!state[b.dataset.n]);if(s)s.closest('section').scrollIntoView({behavior:'smooth',block:'center'})};
 document.getElementById('reset').onclick=()=>{if(confirm('Clear progress?')){state={};save();apply()}};
 apply();
})();
</script>
</body>
</html>
"""


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>INDX + Gen 2 unified guide</title>
<meta name="robots" content="noindex">
<style>
:root{--bg:#fafafa;--fg:#1a1a1a;--mut:#666;--line:#e2e2e2;--card:#fff;--indx:#e65100;--gen2:#1565c0;--art:#6a1b9a;--skip:#b71c1c;--done:#f1f8e9;
 --note:#e3f2fd;--caution:#fff3e0;--reminder:#f3e5f5}
@media (prefers-color-scheme: dark){:root{--bg:#141414;--fg:#e8e8e8;--mut:#9a9a9a;--line:#2c2c2c;--card:#1e1e1e;--done:#1b2a17;--note:#12263a;--caution:#3a2a12;--reminder:#2c1a36}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:inherit}
.top{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);padding:8px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.top h1{font-size:16px;margin:0;flex:1 1 auto}
.top .prog{font-variant-numeric:tabular-nums;color:var(--mut)}
.top button{font:inherit;padding:4px 10px;border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:6px;cursor:pointer}
.bar{height:4px;background:var(--line);width:100%;border-radius:2px;overflow:hidden;flex-basis:100%}
.bar i{display:block;height:100%;background:var(--indx);width:0}
.wrap{display:grid;grid-template-columns:260px minmax(0,1fr);gap:24px;max-width:1400px;margin:0 auto;padding:16px}
nav{position:sticky;top:64px;align-self:start;max-height:calc(100vh - 80px);overflow:auto;font-size:13px}
nav ul{list-style:none;margin:0;padding:0}
nav li{margin:2px 0;display:flex;gap:6px;align-items:baseline}
nav li a{flex:1;text-decoration:none;padding:3px 6px;border-left:3px solid var(--line);border-radius:0 4px 4px 0}
nav li.indx a{border-color:var(--indx)} nav li.gen2 a{border-color:var(--gen2)} nav li.art a{border-color:var(--art);font-style:italic} nav li.appendix a{border-color:var(--mut)}
nav li a:hover{background:var(--card)}
nav .cnt{color:var(--mut);font-variant-numeric:tabular-nums;white-space:nowrap}
nav small{color:var(--mut)}
main{min-width:0}
h2.chap{margin:36px 0 12px;padding-bottom:6px;border-bottom:2px solid var(--line);font-size:20px}
h2.chap small{font-weight:normal;color:var(--mut);font-size:13px;margin-left:8px}
.badge{display:inline-block;font-size:11px;font-weight:600;letter-spacing:.03em;padding:2px 7px;border-radius:4px;color:#fff;background:var(--mut);vertical-align:middle;white-space:nowrap}
.badge.indx{background:var(--indx)} .badge.gen2{background:var(--gen2)} .badge.article{background:var(--art)}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:10px 0;overflow:hidden}
section.step.indx{border-left:5px solid var(--indx)} section.step.gen2{border-left:5px solid var(--gen2)} section.article{border-left:5px solid var(--art)}
section.done{background:var(--done);opacity:.75}
section.done .body{display:none}
body.hide-done section.done{display:none}
section header{display:flex;align-items:center;gap:10px;padding:10px 14px;flex-wrap:wrap}
section header h3{margin:0;font-size:16px;flex:1 1 200px}
.chk{display:flex;align-items:center;gap:6px;cursor:pointer}
.chk input{width:20px;height:20px;margin:0;cursor:pointer}
.num{font-variant-numeric:tabular-nums;color:var(--mut);font-size:13px;min-width:2.5em}
.orig{font-size:12px;color:var(--mut);text-decoration:none}
.body{padding:0 14px 14px}
.gallery{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.gallery a{flex:1 1 300px;max-width:560px}
.gallery img{width:100%;height:auto;border-radius:6px;display:block;background:var(--line)}
ul.lines{list-style:none;margin:0;padding:0}
ul.lines li{display:flex;gap:8px;align-items:flex-start;padding:4px 0}
ul.lines li.lvl1{margin-left:28px}
.dot{flex:none;width:14px;height:14px;border-radius:50%;margin-top:4px;border:1px solid rgba(0,0,0,.25)}
.dot.plain{background:transparent;border-color:var(--mut)}
.ic{flex:none;font-size:11px;font-weight:700;padding:1px 6px;border-radius:4px;margin-top:2px;text-transform:uppercase;letter-spacing:.04em}
li.ic-note{background:var(--note);border-radius:6px;padding:6px 8px} li.ic-note .ic{background:#1e88e5;color:#fff}
li.ic-caution{background:var(--caution);border-radius:6px;padding:6px 8px} li.ic-caution .ic{background:#fb8c00;color:#fff}
li.ic-reminder{background:var(--reminder);border-radius:6px;padding:6px 8px} li.ic-reminder .ic{background:#8e24aa;color:#fff}
.flag{margin:0 14px 10px;padding:8px 12px;border-radius:6px;font-weight:500}
.flag-skip{background:#fdecea;color:var(--skip);border:1px solid var(--skip)} .flag-note{background:var(--note)}
section.skip header h3{text-decoration:line-through;color:var(--mut)}
section.article .body{padding-top:0}
section.article .body img{max-width:100%;height:auto;border-radius:6px}
section.article table{width:100%;border-collapse:collapse} section.article td{padding:4px;vertical-align:top}
section.article ul{padding-left:22px}
p.note{color:var(--mut);font-size:14px}
footer{margin:48px 0 24px;color:var(--mut);font-size:13px;border-top:1px solid var(--line);padding-top:12px}
@media (max-width:900px){.wrap{grid-template-columns:1fr}nav{position:static;max-height:none;margin-bottom:8px}nav ul{display:flex;flex-wrap:wrap;gap:4px}nav li{flex:1 1 45%}}
@media print{.top,nav,.orig{display:none}section{break-inside:avoid;border:1px solid #ccc}section.done .body{display:block}.gallery img{max-width:45%}body{background:#fff;color:#000}.wrap{display:block}}
</style>
</head>
<body>
<div class="top">
 <h1>Prusa CORE One+ (Gen 1) → INDX + Gen 2, one page</h1>
 <span class="prog"><b id="done">0</b> / {{TOTAL}} steps</span>
 <button id="resume">Jump to next step</button>
 <button id="toggle">Hide done</button>
 <button id="reset">Reset progress</button>
 <div class="bar"><i id="fill"></i></div>
</div>
<div class="wrap">
<nav><ul>{{TOC}}</ul></nav>
<main>
<p class="note">Prusa's INDX conversion manual and CORE One+ Gen 2 upgrade manual, flattened into the single order prescribed by Prusa's
<a href="{{ARTICLE_URL}}" target="_blank" rel="noopener">companion article</a>. Every step links back to its original.
Colour bullets match the markers in the photos, as on help.prusa3d.com. Progress is saved in this browser only.</p>
{{BODY}}
<footer>
Content and photos © Prusa Research a.s., reproduced from help.prusa3d.com for personal use; photos are hot-linked, not copied.<br>
Snapshot taken {{FETCHED}}. {{FRESH}}. Prusa still edits these manuals; run <code>build.py check</code> to see what changed since this snapshot.
</footer>
</main>
</div>
<script>
(function(){
 const KEY='indx-gen2-progress';
 let state={};
 try{state=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){state={}}
 const boxes=[...document.querySelectorAll('input[type=checkbox][data-n]')];
 const total={{TOTAL}};
 function save(){try{localStorage.setItem(KEY,JSON.stringify(state))}catch(e){}}
 function apply(){
  let done=0;
  boxes.forEach(b=>{const n=b.dataset.n;const on=!!state[n];b.checked=on;b.closest('section').classList.toggle('done',on);if(on&&/^\d+$/.test(n))done++});
  document.getElementById('done').textContent=done;
  document.getElementById('fill').style.width=(100*done/total)+'%';
  document.querySelectorAll('nav .cnt').forEach(c=>{let k=0;for(let i=+c.dataset.from;i<=+c.dataset.to;i++)if(state[i])k++;c.textContent=k+'/'+(c.dataset.to-c.dataset.from+1)});
 }
 boxes.forEach(b=>b.addEventListener('change',()=>{state[b.dataset.n]=b.checked;save();apply()}));
 document.getElementById('resume').onclick=()=>{const s=boxes.find(b=>!state[b.dataset.n]&&/^\d+$/.test(b.dataset.n));if(s)s.closest('section').scrollIntoView({behavior:'smooth',block:'start'})};
 document.getElementById('toggle').onclick=e=>{document.body.classList.toggle('hide-done');e.target.textContent=document.body.classList.contains('hide-done')?'Show done':'Hide done'};
 document.getElementById('reset').onclick=()=>{if(confirm('Clear all checkboxes?')){state={};save();apply()}};
 apply();
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "fetch":
        cmd_fetch()
    elif cmd == "build":
        cmd_build()
    elif cmd == "check":
        sys.exit(cmd_check())
    elif cmd == "all":
        cmd_fetch()
        cmd_build()
    else:
        raise SystemExit(__doc__)
