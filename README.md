# INDX + Gen 2 unified guide

One page that flattens Prusa's two manuals, the CORE One/+ INDX conversion and
the CORE One+ Gen 2 upgrade, into the single order prescribed by Prusa's
[companion article](https://help.prusa3d.com/article/assemblling-the-prusa-indx-core-one-with-the-gen-2-upgrade_1147602),
with the article's own notes inlined at the step they apply to.

Built for a CORE One+ (Gen 1) owner installing the INDX conversion kit that
ships with the Gen 2 parts in the box.

- `build.py` — stdlib-only Python script. `fetch` pulls Prusa's guide-bundle
  JSON and the article into `data/`; `build` renders `index.html`; `check`
  re-downloads and lists every step whose text, title or photos changed since
  the snapshot.
- `data/` — the snapshot the page was built from (step text, photo URLs, edit
  timestamps).
- `index.html` — the **switch map**: one row per run of official-guide steps
  (start link, stop point, things to remember), with the companion article's
  notes at each hand-off. You follow the official guides, with their user
  comments, and use this page to know where the next hand-off is.
- `full.html` — every step flattened into one page with Prusa's photos
  (hot-linked, not copied). No user comments.
- Progress checkboxes on both pages persist in the browser's localStorage.

```sh
python3 build.py        # fetch + build
python3 build.py check  # what did Prusa change since the snapshot?
```

Prusa was still editing these manuals daily as of 2026-09-23, so run `check`
before an assembly session and rebuild if it reports changes.

Content and photos are © Prusa Research a.s., reproduced for personal use.
The page is marked `noindex`; please don't link to it publicly.
