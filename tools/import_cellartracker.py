#!/usr/bin/env python3
"""Turn a CellarTracker tasting-notes CSV export into DRAFT wine reviews.

Usage:  python3 tools/import_cellartracker.py imports/notes.csv
Output: imports/drafts.json  (private, never committed)

Only your own tasting notes are read. Cellar inventory, bin locations, quantities,
purchase prices and private notes are ignored on purpose. Nothing reaches the
public site until you copy a draft into data/reviews.json and fill in its disclosure.
"""
import csv, json, re, sys
from datetime import datetime
from pathlib import Path

# Header guesses (lowercase, spaces/underscores removed). The script prints what it matched.
FIELDS = {
    "wine":     ["wine", "winename", "name", "title"],
    "vintage":  ["vintage"],
    "producer": ["producer"],
    "region":   ["appellation", "region", "subregion", "locale"],
    "country":  ["country"],
    "grape":    ["varietal", "variety", "grape", "mastervarietal"],
    "type":     ["type", "color", "category"],
    "score":    ["rating", "score", "points", "myscore"],
    "note":     ["tastingnote", "note", "notes", "comment", "tastingnotes"],
    "date":     ["tastedate", "tasteddate", "date", "tasted", "consumed"],
}

def norm(h): return re.sub(r"[^a-z]", "", h.lower())

def pick(headers):
    n = {norm(h): h for h in headers}
    return {k: next((n[g] for g in guesses if g in n), None) for k, guesses in FIELDS.items()}

def to_date(s):
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%y", "%B %d, %Y"):
        try: return datetime.strptime(s.split(" ")[0] if "%d %H" in fmt else s, fmt).strftime("%Y-%m-%d")
        except ValueError: pass
    return datetime.today().strftime("%Y-%m-%d")

def to_score(s):
    try: v = float(str(s).strip())
    except ValueError: return None, None
    return (round(v / 10, 1) if v > 10 else round(v, 1)), v

def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]

def main(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows: sys.exit("No rows found in that file.")
    m = pick(rows[0].keys())
    print("Columns matched:")
    for k, v in m.items(): print(f"  {k:9} <- {v}")
    if not m["wine"] or not m["note"]:
        sys.exit("Could not find the wine name and note columns. Send me the header row (not the data) and I will adjust.")
    out, used = [], set()
    for r in rows:
        note = (r.get(m["note"]) or "").strip()
        if not note: continue
        name = (r.get(m["wine"]) or "").strip()
        vint = (r.get(m["vintage"]) or "").strip() if m["vintage"] else ""
        score, raw = to_score(r.get(m["score"], "")) if m["score"] else (None, None)
        if score is None: continue
        title = f"{name} {vint}".strip()
        base = slug(title) or "wine"; i, rid = 2, base
        while rid in used: rid, i = f"{base}-{i}", i + 1
        used.add(rid)
        facts = [x for x in [vint, (r.get(m["producer"]) or "").strip() if m["producer"] else "",
                             (r.get(m["grape"]) or "").strip() if m["grape"] else ""] if x]
        place = ", ".join(x for x in [(r.get(m["region"]) or "").strip() if m["region"] else "",
                                       (r.get(m["country"]) or "").strip() if m["country"] else ""] if x)
        first = re.split(r"(?<=[.!?])\s", note, 1)[0]
        out.append({"id": rid, "category": "wine", "title": title, "subject": name, "facts": facts, "place": place,
                    "date": to_date(r.get(m["date"], "")) if m["date"] else to_date(""), "score": score,
                    "verdict": first[:220], "who_for": "", "method": "", "acquired": "",
                    "worked": [], "flaws": [], "skip": [], "criteria": [],
                    "body": [p.strip() for p in note.split("\n") if p.strip()],
                    "_source_score": raw, "_needs": "Fill in 'acquired' (how you got the bottle) before publishing."})
    Path("imports").mkdir(exist_ok=True)
    Path("imports/drafts.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"Wrote {len(out)} drafts to imports/drafts.json (skipped notes with no text or no score).")

if __name__ == "__main__":
    if len(sys.argv) != 2: sys.exit(__doc__)
    main(sys.argv[1])
