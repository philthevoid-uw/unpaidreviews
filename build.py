#!/usr/bin/env python3
"""Builds the Unpaid Reviews static site from data/reviews.json.

Run:  python3 build.py
Writes: index.html, reviews.html, <category>.html, policy pages, reviews/<id>.html,
        404.html, sitemap.xml, robots.txt, feed.xml
        _sites/<domain>/...  one mini-site per category-mode domain (see "domains" in the data file)
        src/routes.json      host routing table read by src/worker.js
Needs only Python 3.
"""
import json
import re
import shutil
from datetime import datetime
from html import escape as e
from pathlib import Path

ROOT = Path(__file__).parent
PUBLIC = ROOT / "public"
data = json.loads((ROOT / "data" / "reviews.json").read_text())
SITE, CATS, REVIEWS, CORRECTIONS = data["site"], data["categories"], data["reviews"], data["corrections"]
MAIN = SITE["domain"]
DOMAINS = data.get("domains", [])
ALL_CATS, ALL_REVIEWS = list(CATS), list(REVIEWS)
CAT = {c["slug"]: c for c in CATS}
BASE = f"https://{MAIN}"
HOST = MAIN            # the domain currently being built
NAME = SITE["name"]    # brand name of the site currently being built

# ---------- domains: where each category lives ----------
# mode "category": the domain is its own site for one category; the main site sends that category there.
# mode "redirect": the domain is a plain 301 to a page on the main site.
_hosts = set()
for d in DOMAINS:
    assert d["host"] != MAIN and d["host"] not in _hosts, f'domain {d["host"]}: duplicate or same as main'
    _hosts.add(d["host"])
    assert d.get("mode") in ("category", "redirect"), f'domain {d["host"]}: mode must be "category" or "redirect"'
    if d["mode"] == "category":
        assert d.get("category") in CAT, f'domain {d["host"]}: unknown category {d.get("category")}'
        assert d.get("name"), f'domain {d["host"]}: category domains need a "name"'
    else:
        assert d.get("target", "").startswith(("/", "https://")), f'domain {d["host"]}: redirect needs a "target"'
CAT_DOMAIN = {d["category"]: d for d in DOMAINS if d["mode"] == "category"}
assert len(CAT_DOMAIN) == sum(d["mode"] == "category" for d in DOMAINS), "a category can live on only one domain"

def host_of(r):
    return CAT_DOMAIN[r["category"]]["host"] if r["category"] in CAT_DOMAIN else MAIN

def review_url(r):
    return f'https://{host_of(r)}/reviews/{r["id"]}.html'

def review_href(r, root):
    return f'{root}reviews/{r["id"]}.html' if host_of(r) == HOST else review_url(r)

# ---------- validation: fail loudly rather than publish something broken ----------
seen = set()
for r in REVIEWS:
    assert r["id"] not in seen, f'duplicate id {r["id"]}'
    seen.add(r["id"])
    assert r["category"] in CAT, f'{r["id"]}: unknown category {r["category"]}'
    assert 0 <= r["score"] <= 10, f'{r["id"]}: score must be 0-10'
    datetime.strptime(r["date"], "%Y-%m-%d")
    names = [n for n, _ in r["criteria"]]
    assert not names or names == CAT[r["category"]]["criteria"], f'{r["id"]}: criteria must be {CAT[r["category"]]["criteria"]} (or left empty for a quick note)'
    assert r.get("sample") or r.get("acquired", "").strip(), f'{r["id"]}: every real review needs a disclosure in "acquired"'
    for _, s in r["criteria"]:
        assert 0 <= s <= 10, f'{r["id"]}: criterion scores must be 0-10'

def pretty(d):
    return datetime.strptime(d, "%Y-%m-%d").strftime("%B %-d, %Y")

def real(r):
    return not r.get("sample")

def sorted_reviews(items=None):
    return sorted(items if items is not None else REVIEWS, key=lambda r: r["date"], reverse=True)

def main_nav():
    return [("reviews.html", "All reviews", "reviews")] + \
           [((f'https://{CAT_DOMAIN[c["slug"]]["host"]}/' if c["slug"] in CAT_DOMAIN else f'{c["slug"]}.html'), c["name"], c["slug"]) for c in ALL_CATS] + \
           [("how-we-review.html", "How we review", "how"), ("how-we-make-money.html", "Funding", "money")]

def category_nav(d):
    return [("index.html", "All reviews", "home"), ("how-we-review.html", "How we review", "how"),
            ("how-we-make-money.html", "Funding", "money"), (f"https://{MAIN}/", f"{SITE['name']} ↗", "parent")]

NAV = main_nav()
POLICY = re.compile(r'href="(?:\.\./)*(how-we-review|how-we-make-money|corrections|suggest|whats-next|about)\.html')

def brand_html():
    first, _, rest = NAME.partition(" ")
    return f'{e(first)} <span>{e(rest)}</span>' if rest else e(first)

def page(path, title, desc, body, nav="", noindex=False, jsonld=None, og_type="website"):
    depth = path.count("/")
    root = "../" * depth
    robots = '<meta name="robots" content="noindex">\n' if noindex else ""
    ld = ""
    if jsonld:
        ld = '<script type="application/ld+json">' + json.dumps(jsonld).replace("</", "<\\/") + "</script>\n"
    links = "".join(
        f'<a href="{href if href.startswith("http") else root + href}"' + (' aria-current="page"' if nav == key else "") + f">{e(label)}</a>"
        for href, label, key in NAV)
    canon = f"{BASE}/{'' if path == 'index.html' else path}"
    banner = (f'<div class="construction" role="status"><b>Under construction.</b> {e(SITE["banner"])}</div>\n'
              if SITE.get("banner") else "")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{robots}<link rel="canonical" href="{canon}">
<meta property="og:site_name" content="{e(NAME)}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{canon}">
<meta name="twitter:card" content="summary">
<link rel="alternate" type="application/atom+xml" title="{e(NAME)}" href="{root}feed.xml">
<link rel="stylesheet" href="{root}css/style.css">
{ld}</head>
<body>
<a class="skip" href="#main">Skip to content</a>
{banner}<header class="site"><div class="wrap">
  <a class="brand" href="{root}index.html">{brand_html()}</a>
  <nav aria-label="Main">{links}</nav>
</div></header>
<main id="main" class="wrap">
{body}
</main>
<footer><div class="wrap"><div class="cols">
  <div><b>{e(NAME)}</b><br>Independent. We do not accept payments that influence reviews or earn money from affiliate links, any advertising is clearly visible, and no revenue incentive decides what is reviewed or how it is scored.</div>
  <div><h4>Read</h4><ul>
    <li><a href="{root}how-we-review.html">How we review</a></li>
    <li><a href="{root}how-we-make-money.html">How the site is funded</a></li>
    <li><a href="{root}corrections.html">Corrections</a></li>
    <li><a href="{root}feed.xml">RSS feed</a></li></ul></div>
  <div><h4>Get involved</h4><ul>
    <li><a href="{root}suggest.html">Suggest the next review</a></li>
    <li><a href="{root}whats-next.html">Our reviewers: the plan</a></li>
    <li><a href="{root}about.html">About</a></li>
    <li><a href="mailto:{e(SITE["contact"])}">{e(SITE["contact"])}</a></li></ul></div>
</div></div></footer>
<script src="{root}js/app.js"></script>
</body>
</html>
"""
    if HOST != MAIN:  # policy pages live once, on the main site
        html = POLICY.sub(lambda m: f'href="https://{MAIN}/{m.group(1)}.html', html)
    return html

# ---------- components ----------
def card(r, root=""):
    c = CAT[r["category"]]
    text = f'{r["title"]} {r["subject"]} {r.get("place", "")} {r["verdict"]}'.lower()
    sample = '<span class="badge">SAMPLE</span>' if r.get("sample") else ""
    sub = " · ".join(x for x in [r["subject"], r.get("place", "")] if x)
    return f"""<a class="card c-{e(r["category"])}" href="{review_href(r, root)}" data-category="{e(r["category"])}" data-score="{r["score"]}" data-date="{e(r["date"])}" data-text="{e(text)}">
    <div class="meta"><span>{e(c["name"])}</span>{sample}</div>
    <h3>{e(r["title"])}</h3>
    <div class="sub">{e(sub)} · {e(pretty(r["date"]))}</div>
    <div class="row"><div class="ring" style="--p:{r["score"] * 10:.0f}" role="img" aria-label="Score {r["score"]:.1f} out of 10"><b>{r["score"]:.1f}</b></div>
    <div class="verdict">{e(r["verdict"])}</div></div>
  </a>"""

def sample_note():
    if not any(r.get("sample") for r in REVIEWS):
        return ""
    return ('<div class="samplebar">Entries marked <b>SAMPLE</b> are layouts with no real findings. '
            'Replace them with real reviews in <code>data/reviews.json</code>. Sample pages are hidden from search engines.</div>')

def controls(chips=True):
    c = ""
    if chips:
        c = '<button class="chip" data-cat="all" aria-pressed="true">All</button>' + "".join(
            f'<button class="chip" data-cat="{e(x["slug"])}" aria-pressed="false">{e(x["name"])}</button>' for x in CATS)
    return f"""<div class="toolbar">{c}</div>
<div class="toolbar" style="margin-top:0">
  <input type="search" id="q" placeholder="Search reviews…" aria-label="Search reviews">
  <select id="sort" aria-label="Sort reviews">
    <option value="new">Newest</option><option value="high">Highest score</option><option value="low">Lowest score</option>
  </select>
  <span id="count" aria-live="polite" style="color:var(--muted);font-size:.9rem"></span>
</div>"""

# ---------- pages ----------
def home():
    tiles = ""
    for c in CATS:
        n = sum(1 for r in REVIEWS if r["category"] == c["slug"] and real(r))
        status = f"{n} review{'s' if n != 1 else ''}" if n else "First reviews coming soon"
        tiles += (f'<a class="cat c-{e(c["slug"])}" href="{e(c["slug"])}.html"><h3>{e(c["name"])}</h3>'
                  f'<p>{e(c["blurb"])}</p><small>{status} →</small></a>')
    latest = "\n  ".join(card(r) for r in sorted_reviews()[:6])
    return f"""<section class="hero">
  <h1>{e(SITE["tagline"])}</h1>
  <p class="lead">{e(SITE["description"])}</p>
  <form class="searchbar" action="reviews.html" method="get" role="search">
    <input type="search" name="q" placeholder="Search products, places, restaurants…" aria-label="Search reviews">
    <button class="btn" type="submit">Search</button>
  </form>
</section>
<div class="proof">
  <div><b>0</b><span>pay per purchase: no affiliate links, ever</span></div>
  <div><b>0</b><span>sponsored reviews or gifts</span></div>
  <div><b>100%</b><span>disclose how the item was acquired</span></div>
  <div><b>All</b><span>revenue sources disclosed</span></div>
  <div><b>Public</b><span>corrections log</span></div>
</div>
<h2>Browse by category</h2>
<div class="cats">{tiles}</div>
<h2>Latest reviews</h2>
{sample_note()}
<div class="grid" id="grid">
  {latest}
</div>
<p style="margin-top:16px"><a href="reviews.html">Browse all reviews →</a></p>
<h2>How we protect independence</h2>
<div class="pillars">
  <div class="pillar"><h3>Written by screened reviewers</h3><p>Reviews are written by our community of reviewers. Every reviewer is screened to confirm they are a real person, not a bot, and not an employee of, or otherwise funded by, what they review.</p></div>
  <div class="pillar"><h3>No payments that shape reviews</h3><p>We do not accept payments that could influence what a review says. How each item was obtained is disclosed on every review, including anything that was provided or discounted.</p></div>
  <div class="pillar"><h3>Nothing steers what you buy</h3><p>We are not paid for affiliate links, and we do not try to influence the site or your purchase decisions in other ways. No revenue incentive decides what gets reviewed, what is skipped, or whether a review is positive or negative. Reviews from our community follow the same policy.</p></div>
  <div class="pillar"><h3>Advertising is visible</h3><p>Any advertising or paid promotion will be clearly labeled, and we will not be influenced by who does or does not advertise here. <a href="how-we-make-money.html">How the site is funded</a>.</p></div>
  <div class="pillar"><h3>Mistakes are public</h3><p>Errors are fixed in the open and logged on the <a href="corrections.html">corrections page</a>. Scores are never changed because someone complained.</p></div>
</div>
<div class="band">
  <div><h2>You help pick what's next</h2><p>Tell us what to buy, visit or eat. Suggestions from the businesses involved are ignored.</p></div>
  <a class="btn" href="suggest.html">Suggest a review</a>
</div>"""

def reviews_index():
    cards = "\n  ".join(card(r) for r in sorted_reviews())
    return f"""<section class="hero" style="padding-bottom:6px">
  <h1 style="font-size:clamp(1.8rem,4.5vw,2.6rem)">All reviews</h1>
  <p class="lead">Every review follows the same format and the same disclosure rules.</p>
</section>
{controls(True)}
{sample_note()}
<div class="grid" id="grid">
  {cards}
</div>
<div class="empty" id="empty" hidden>No reviews match your search.</div>"""

def category_page(c):
    items = sorted_reviews([r for r in REVIEWS if r["category"] == c["slug"]])
    cards = "\n  ".join(card(r) for r in items)
    crit = ", ".join(c["criteria"])
    return f"""<section class="hero c-{e(c["slug"])}" style="padding-bottom:6px">
  <div class="kicker" style="margin:0">Category</div>
  <h1 style="font-size:clamp(1.8rem,4.5vw,2.6rem)">{e(c["name"])}</h1>
  <p class="lead">{e(c["blurb"])}</p>
  <p class="facts">Every review in this category is scored on: <b>{e(crit)}</b>. <a href="how-we-review.html">How scoring works</a>.</p>
</section>
{controls(False)}
{sample_note()}
<div class="grid" id="grid">
  {cards}
</div>
<div class="empty" id="empty" hidden>No reviews match your search.</div>"""

def bullets(items):
    return "".join(f"<li>{e(x)}</li>" for x in items)

def review_page(r):
    c = CAT[r["category"]]
    crit = "".join(
        f'<div class="crit"><span>{e(n)}</span><div class="bar"><i style="width:{s * 10}%"></i></div><b>{s}</b></div>'
        for n, s in r["criteria"])
    facts = " · ".join(x for x in [r["subject"], *r.get("facts", []), r.get("place", ""), r.get("price", "")] if x)
    updated = f' · Updated {e(pretty(r["updated"]))}' if r.get("updated") else ""
    sample = ' <span class="badge">SAMPLE</span>' if r.get("sample") else ""
    skip = (f'<h2>What we would skip</h2><ul>{bullets(r["skip"])}</ul>') if r.get("skip") else ""
    related = [x for x in sorted_reviews() if x["category"] == r["category"] and x["id"] != r["id"]][:2]
    rel = ""
    if related:
        rel = '<h2>More in ' + e(c["name"]) + '</h2><div class="grid">' + "".join(card(x, "../") for x in related) + "</div>"
    body = f"""<article class="review c-{e(r["category"])}">
  <a class="back" href="../{"index.html" if HOST != MAIN else e(r["category"]) + ".html"}">← {e(c["name"]) if HOST == MAIN else "All reviews"}</a>
  <div class="kicker">{e(c["name"])} · {e(pretty(r["date"]))}{updated}{sample}</div>
  <div class="head">
    <div class="ring big" style="--p:{r["score"] * 10:.0f}" role="img" aria-label="Score {r["score"]:.1f} out of 10"><b>{r["score"]:.1f}</b></div>
    <div><h1 style="margin:0">{e(r["title"])}</h1></div>
  </div>
  <div class="facts">{e(facts)}</div>
  <p class="lede">{e(r["verdict"])}</p>
  <div class="disclosure"><b>Disclosure:</b> {e(r["acquired"])} <a href="../how-we-make-money.html">How the site is funded</a>.</div>
  {("<h2>Who it's for</h2><p>" + e(r["who_for"]) + "</p>") if r.get("who_for") else ""}
  {("<h2>" + e(c["method_label"]) + "</h2><p>" + e(r["method"]) + "</p>") if r.get("method") else ""}
  {("<h2>Scores</h2>" + crit) if crit else ""}
  {('<div class="two"><div class="pro"><h3>What worked</h3><ul>' + bullets(r["worked"]) + '</ul></div><div class="con"><h3>Flaws, but not dealbreakers</h3><ul>' + bullets(r["flaws"]) + '</ul></div></div>') if r["worked"] or r["flaws"] else ""}
  {skip}
  {('<div class="prose"><h2>' + "The full story" + '</h2>' + "".join(f"<p>{e(p)}</p>" for p in r["body"]) + '</div>') if r["body"] else ""}
  <p class="fine">Spotted a mistake? See the <a href="../corrections.html">corrections policy</a>. Read <a href="../how-we-review.html">how we review</a>.</p>
  {rel}
</article>"""
    ld = None
    if real(r):
        ld = {"@context": "https://schema.org", "@type": "Review",
              "itemReviewed": {"@type": c["kind"], "name": r["subject"]},
              "reviewRating": {"@type": "Rating", "ratingValue": r["score"], "bestRating": 10, "worstRating": 0},
              "author": {"@type": "Organization", "name": SITE["name"]},
              "datePublished": r["date"], "reviewBody": r["verdict"]}
    return page(f'reviews/{r["id"]}.html', f'{r["title"]} | {NAME}', r["verdict"], body,
                nav=r["category"], noindex=not real(r), jsonld=ld, og_type="article")

def how_review():
    cat_rows = "".join(f'<tr><td><b>{e(c["name"])}</b></td><td>{e(", ".join(c["criteria"]))}</td></tr>' for c in CATS)
    return f"""<article class="page">
  <h1>How we review</h1>
  <p>Trust is the only thing this site offers, so our rules are written down and apply to every review.</p>
  <h2>Who writes the reviews</h2>
  <p>Reviews are written by our community of reviewers, not by the site's owners or a single critic. Before anyone can post, we screen them:</p>
  <ul>
    <li><b>Real people.</b> We verify that each reviewer is a real person and not a bot, and we do not allow automated or AI-written reviews.</li>
    <li><b>Not employees.</b> Reviewers cannot be employees, owners or contractors of the business, brand or place they review, or of its competitors.</li>
    <li><b>Not funded to review.</b> Reviewers cannot be paid, sponsored or otherwise funded by anyone to provide a review. Reviewers who break these rules are removed and their reviews taken down.</li>
    <li><b>Disclosed.</b> Each review shows how the reviewer obtained the item or experience.</li>
  </ul>
  <h2>Independence rules</h2>
  <ul>
    <li><b>No payments that influence a review.</b> We do not accept payments, gifts or perks that could shape what a review says or how it scores.</li>
    <li><b>No affiliate income.</b> We are not paid for affiliate links, commissions or referral fees, and we do not try to influence the site or anyone's purchase decisions in other ways.</li>
    <li><b>No revenue incentive over coverage.</b> No revenue incentive influences what is reviewed or not reviewed, or whether a review is positive or negative.</li>
    <li><b>Advertising is visible.</b> Any advertising or revenue-generating promotion is clearly labeled, and we are not influenced by who does or does not advertise here.</li>
    <li><b>Disclosure on every review.</b> Each page states how the item was obtained, including anything that was provided, discounted or hosted.</li>
    <li><b>Community reviews follow the same policy.</b> Every review is written by our community, so every review must follow these rules, and the community is built on these guiding principles.</li>
    <li><b>No conflicts of interest.</b> A reviewer with any relationship to what they review does not review it, or discloses the relationship. We do the same for the site itself.</li>
    <li><b>Associations minimized.</b> We keep any association with a reviewed business, brand or sponsor to a minimum so that no revenue stream can influence a review, and we disclose any that remain.</li>
    <li><b>All revenue sources disclosed.</b> Every way the site earns money is listed on <a href="how-we-make-money.html">how the site is funded</a>.</li>
    <li><b>No pre-publication previews.</b> Businesses never see a review before it goes live, and cannot change an opinion or a score.</li>
  </ul>
  <h2>How scoring works</h2>
  <p>Each review rates four criteria from 1 to 10. The criteria depend on the category:</p>
  <table><tr><th>Category</th><th>Criteria</th></tr>{cat_rows}</table>
  <p>The overall score is a considered judgment, not a mechanical average, and the review explains it.</p>
  <p><b>Wine quick notes:</b> older bottles from our CellarTracker history appear as short quick notes with a score and, where one was written, a tasting note. CellarTracker uses a 100-point scale, so a 90 there is shown here as 9.0 out of 10. Quick notes have no criteria breakdown, and each one says how the bottle was acquired, or that we no longer have a record.</p>
  <p><b>Scale:</b> 9–10 exceptional · 7–8 good · 5–6 mixed · 3–4 poor · 1–2 avoid.</p>
  <h2>Testing standards</h2>
  <ul>
    <li><b>Products:</b> used for a meaningful period before publishing, with the duration stated and at least one alternative compared where possible.</li>
    <li><b>Travel:</b> visited in person, with the dates and season stated, costs given, and any discount, comp or hosting disclosed.</li>
    <li><b>Wine:</b> tasted with the bottle's vintage, producer and price noted, with how long it was open and how it changed where we tracked that.</li>
    <li><b>Restaurants:</b> visited at least twice where practical, ordering like any customer, without announcing that we write reviews.</li>
  </ul>
  <h2>Every review has the same parts</h2>
  <p>Bottom line, who it is for, how we tested or visited, scores, what worked, flaws but not dealbreakers, and what we would skip. Using one format makes reviews comparable and makes it harder to hide a weak spot.</p>
  <h2>Updates and corrections</h2>
  <p>Reviews are dated and updated when things change. Errors are corrected in the open: see <a href="corrections.html">corrections</a>.</p>
</article>"""

def how_money():
    return f"""<article class="page">
  <h1>How the site is funded</h1>
  <div class="status"><b>Status as of {e(pretty(SITE["policies_updated"]))}:</b> no ads are running, no affiliate links exist, and the site earns no money. Any change to this will be announced here <i>before</i> it takes effect.</div>
  <h2>What will never change</h2>
  <ul>
    <li>We do not accept payments that would influence the content of a review, from any business, brand or person we review, or from their competitors, in exchange for coverage, placement, ranking or silence.</li>
    <li>We are not paid for affiliate links, commissions, referral fees or per-sale payments, and we do not try to influence the site or the purchase decisions people make in any other way.</li>
    <li>No revenue incentive influences what is reviewed or not reviewed, or whether anything is reviewed positively or negatively.</li>
    <li>Every review is written by our community of screened reviewers, who are real people and not employees of, or funded by, what they review. All reviews follow this same policy, and the community is built on these guiding principles.</li>
    <li>Every revenue source is disclosed on this page, and any association that could create a revenue stream is kept to a minimum.</li>
  </ul>
  <h2>If we run advertising or promotions</h2>
  <p>We have not decided whether to run advertising or other revenue-generating promotions. If we do, these rules apply, and we will publish the specific details on this page before any ad or promotion runs:</p>
  <ul>
    <li><b>Clearly visible.</b> Ads and paid promotions are labeled as such and kept separate from review text.</li>
    <li><b>Not influenced by advertisers.</b> Who does or does not advertise has no effect on what we review, what we skip, or how anything is scored. Advertisers get no advance look at reviews and no influence over them.</li>
    <li><b>No favoritism and no penalties.</b> Neither pricing nor ad placement depends on what we have reviewed, what we plan to review, or how anything was scored.</li>
    <li><b>Same rules for every advertiser.</b> Ads are sold on the same terms to everyone, with no negotiated deals. Any restrictions are broad categories applied site-wide (for example, no gambling ads) and listed publicly.</li>
    <li><b>Reviewed businesses.</b> We will publish the exact rule for ads from businesses we have reviewed before ads start.</li>
  </ul>
  <h2>Other ways the site could be supported</h2>
  <p>Reader support (donations or memberships) is one option we may explore. Any model we use must pass one test: nothing is paid based on purchases of what we review, and no revenue incentive influences what is reviewed or how it is scored. Every source of revenue will be disclosed on this page.</p>
  <h2>Change log</h2>
  <table><tr><th>Date</th><th>Change</th></tr>
    <tr><td>{e(pretty(SITE["policies_updated"]))}</td><td>Policy first written. No income of any kind.</td></tr></table>
</article>"""

def corrections():
    if CORRECTIONS:
        rows = "".join(
            f'<tr><td>{e(pretty(c["date"]))}</td><td>{e(c["review"])}</td><td>{e(c["note"])}</td></tr>' for c in CORRECTIONS)
        log = f"<table><tr><th>Date</th><th>Review</th><th>What changed</th></tr>{rows}</table>"
    else:
        log = '<p class="empty" style="padding:20px;text-align:left">No corrections yet.</p>'
    return f"""<article class="page">
  <h1>Corrections</h1>
  <p>If we get a fact wrong, we fix it, add a visible note on the review, and list it here. Businesses may point out factual errors (wrong price, wrong hours, wrong dish). They cannot change an opinion or a score.</p>
  <p>To report an error, email <a href="mailto:{e(SITE["contact"])}">{e(SITE["contact"])}</a>.</p>
  <h2>Corrections log</h2>
  {log}
</article>"""

def suggest():
    return f"""<article class="page">
  <h1>Suggest the next review</h1>
  <p>Tell us what to buy, visit or eat. We read every suggestion and choose based on how many readers want it, not on who is asking.</p>
  <ul>
    <li>Suggestions from the business, brand or people involved are ignored.</li>
    <li>We cannot promise to get to every request.</li>
    <li>Include the exact product, place or restaurant, and what you want to know.</li>
  </ul>
  <p><a class="btn" href="mailto:{e(SITE["contact"])}?subject=Review%20suggestion">Email a suggestion</a></p>
  <p>Or write to <b>{e(SITE["contact"])}</b>.</p>
</article>"""

def whats_next():
    return f"""<article class="page">
  <h1>Our reviewers: the plan</h1>
  <p class="samplebar">Draft. Nothing here is live yet.</p>
  <p>Reviews on this site are written by our community of reviewers. We are still building that community, and nothing here is live yet. It will be built on these guiding principles:</p>
  <ul>
    <li><b>Screened reviewers.</b> Every reviewer is screened to confirm they are a real person, not a bot, and not an employee of, or otherwise funded to provide a review of, what they review.</li>
    <li><b>Reviews from real experience.</b> Reviewers say how they used the product or visited the place, and how they obtained it.</li>
    <li><b>Same policy as the site.</b> Every community review must follow the site policy: no one is paid based on purchases of what is reviewed, and no revenue incentive influences what is reviewed or whether it is positive or negative.</li>
    <li><b>No incentives.</b> Nobody can offer, request or reward a review.</li>
    <li><b>Businesses cannot edit or buy their way out.</b> They may respond publicly to a review, and the review stays.</li>
    <li><b>Transparent moderation.</b> Published rules, and a regular report on what was removed and why.</li>
    <li><b>One standard for everyone.</b> Every review, including those from the people who run the site, follows the same rules and is scored on the same published criteria.</li>
  </ul>
  <h2>Lessons from wine communities</h2>
  <p>Wine sites such as CellarTracker and Vivino have run large reader communities for years. Here is what we plan to borrow and what we plan to do differently.</p>
  <ul>
    <li><b>Notes tied to a real bottle.</b> A review says which vintage was opened, how it was stored and served, and how it was acquired. One bottle's flaw does not make another reader's review wrong.</li>
    <li><b>Handles, not real names.</b> Reviewers choose a public handle. We verify identity privately when screening, and real names stay private unless the reviewer chooses to show them.</li>
    <li><b>Comments that notify.</b> When someone replies to a comment, the original commenter is told. Community members on existing sites say missing reply alerts are a common frustration.</li>
    <li><b>Follow a taster, not a score.</b> Readers can follow people whose palates match theirs, as on CellarTracker and Vivino, instead of relying on one blended number.</li>
    <li><b>No scores from too few voices.</b> A community average appears only after enough independent ratings, with the count always shown.</li>
    <li><b>No republished professional scores.</b> Critics' points and notes are copyrighted, so they are not copied here.</li>
    <li><b>Your own words only.</b> Reviews written by AI or copied from elsewhere are not allowed.</li>
    <li><b>Community kept apart from selling.</b> There are no shop links, affiliate links or purchase-based payments in reviews or in the community, so nothing pushes readers toward buying.</li>
    <li><b>Cellar tools stay elsewhere.</b> Inventory, bin locations and drinking windows are better handled by CellarTracker, so this site covers published reviews only.</li>
  </ul>
  <p>Want to be told when it opens, or to apply as a reviewer? Email <b>{e(SITE["contact"])}</b>.</p>
</article>"""

def about():
    return f"""<article class="page">
  <h1>About</h1>
  <p class="samplebar">Placeholder. Replace this with a short note about who we are and why we started this community. Share only what you are comfortable making public.</p>
  <p>{e(SITE["name"])} is a community that publishes independent reviews of products, travel, restaurants and wine, written by screened reviewers who are real people and are not employees of, or funded by, what they review. Every review says how the item was obtained. We do not accept payments that would influence a review, we are not paid for affiliate links, and no revenue incentive influences what is reviewed or how it is scored. Any advertising will be clearly visible, and every review must follow the same policy. See <a href="how-we-review.html">how we review</a> and <a href="how-we-make-money.html">how the site is funded</a>.</p>
</article>"""


# ---------- accounts (main site only, never indexed) ----------
TERMS_CHECKS = [
    ("malicious", "I will not upload or link to anything malicious: no viruses, malware, scripts, tracking or deceptive files, and nothing designed to harm a person, device or system."),
    ("responsible", "I am solely responsible for everything I submit or upload, including text, images and video, and for any claim that arises from it."),
    ("rights", "I warrant that I own, or have every right and permission needed to publish, everything I submit, including permission from anyone identifiable in it, and I grant Unpaid Reviews a worldwide, non-exclusive, royalty-free licence to host, display, edit for formatting and distribute it on this site."),
]
def check_html(name, text):
    return f'<label class="check"><input type="checkbox" name="{name}" required> <span>{e(text)}</span></label>'

def signup_page():
    checks = "\n".join(check_html(k, t) for k, t in TERMS_CHECKS)
    return f"""<article class="page narrow">
  <h1>Become a reviewer: step 1 of 2, create your account</h1>
  <p>No password. We email you a one-time sign-in link. Step 2 is the reviewer application, where we ask about conflicts of interest.</p>
  <form id="signup" class="stack" novalidate>
    <label>Email address <input type="email" name="email" autocomplete="email" required maxlength="254"></label>
    <label>Public handle <input type="text" name="handle" autocomplete="off" required minlength="3" maxlength="24" pattern="[A-Za-z0-9_]+"> <small>3 to 24 letters, numbers or underscores. This is the only name shown with your reviews.</small></label>
    <fieldset><legend>Contributor agreement (<a href="/contributor-terms.html" target="_blank" rel="noopener">read the full terms</a>)</legend>
    {checks}
    </fieldset>
    <div id="turnstile"></div>
    <button class="btn" type="submit">Email me a sign-in link</button>
    <p id="msg" role="status"></p>
  </form>
  <p>Already have an account? <a href="/signin.html">Sign in</a>.</p>
</article>
<script src="/js/account.js"></script>"""

def signin_page():
    return """<article class="page narrow">
  <h1>Sign in</h1>
  <form id="signin" class="stack" novalidate>
    <label>Email address <input type="email" name="email" autocomplete="email" required maxlength="254"></label>
    <div id="turnstile"></div>
    <button class="btn" type="submit">Email me a sign-in link</button>
    <p id="msg" role="status"></p>
  </form>
  <p>New here? <a href="/signup.html">Create an account</a>.</p>
</article>
<script src="/js/account.js"></script>"""

def account_page():
    cats = [("products", "Products"), ("travel", "Travel"), ("restaurants", "Restaurants"), ("wine", "Wine"), ("other", "Other")]
    catbox = "".join(f'<label class="check"><input type="checkbox" name="cat" value="{v}"> {l}</label>' for v, l in cats)
    att = [("truthful", "Everything in this application is true and complete."),
           ("own_experience", "I will review only things I have personally bought, visited or used at my own expense."),
           ("no_ai", "I will not use AI to write my reviews or to invent experiences."),
           ("no_payment", "I will not accept payment, free products, free stays, discounts or other benefits from anyone I review."),
           ("disclose_changes", "I will tell Unpaid Reviews promptly if my circumstances or conflicts of interest change."),
           ("removal", "I understand reviews and my access can be removed if I break these rules.")]
    attbox = "\n".join(check_html(k, t) for k, t in att)
    qs = [("works_in_category", "Do you work for, or own part of, any business in the categories you chose? Write \"None\" if not."),
          ("paid_for_reviews", "Have you been paid, or given free items or stays, for reviews in the last five years? Write \"None\" if not."),
          ("affiliate_programs", "Do you earn affiliate commissions or run a review or content site? Write \"None\" if not."),
          ("other_relationships", "Any other relationship with a business, brand or person you may review? Write \"None\" if not.")]
    qbox = "".join(f'<label>{e(q)} <textarea name="{k}" rows="2" maxlength="600" required></textarea></label>' for k, q in qs)
    return f"""<article class="page narrow">
  <h1>Your account</h1>
  <p id="who" role="status">Loading…</p>
  <section id="apply" hidden>
    <h2>Step 2 of 2: reviewer application</h2>
    <form id="appform" class="stack" novalidate>
      <label>Country you live in <input type="text" name="country" required maxlength="80"></label>
      <fieldset><legend>What will you review?</legend>{catbox}</fieldset>
      <label>Writing sample: a review of something you recently bought, visited or used (300 characters minimum) <textarea name="sample" rows="8" maxlength="2000" required></textarea></label>
      <label>Links to other reviews you have written (optional) <textarea name="links" rows="2" maxlength="1000"></textarea></label>
      <h3>Conflicts of interest</h3>
      {qbox}
      <fieldset><legend>Reviewer standards</legend>{attbox}</fieldset>
      <button class="btn" type="submit">Submit application</button>
      <p id="msg" role="status"></p>
    </form>
  </section>
  <section id="pending" hidden><h2>Application received</h2><p>A person reads every application. We will email you when it has been decided. Identity verification comes next for approved applicants.</p></section>
  <section id="declined" hidden><h2>Application not accepted</h2><p>Thank you for applying. We are not able to offer a reviewer place at this time.</p></section>
  <section id="uploads" hidden>
    <h2>Upload photos and video</h2>
    <p>JPEG, PNG or WebP images up to 10 MB, and video up to 20 seconds. Everything is checked, and a person approves your first upload. Nothing appears on the site until it is approved. Do not upload anything you do not have the rights to, or anything malicious, unlawful or inappropriate.</p>
    <p><input type="file" id="imgfile" accept="image/jpeg,image/png,image/webp"> <button class="btn" id="imgbtn" type="button">Upload image</button></p>
    <p><input type="file" id="vidfile" accept="video/mp4,video/quicktime,video/webm"> <button class="btn" id="vidbtn" type="button">Upload video</button></p>
    <p id="upmsg" role="status"></p>
    <h3>Your uploads</h3>
    <ul id="uplist"></ul>
  </section>
  <section id="admin" hidden>
    <h2>Moderation queue</h2>
    <div id="queue"></div>
  </section>
  <p><button class="btn ghost" id="logout" type="button" hidden>Sign out</button></p>
</article>
<script src="/js/account.js"></script>"""

def contributor_terms():
    items = "".join(f"<li>{e(t)}</li>" for _, t in TERMS_CHECKS)
    return f"""<article class="page">
  <h1>Contributor agreement</h1>
  <p><i>Draft for legal review. Version contributor-2026-11-v1.</i></p>
  <p>By creating an account you agree to the following, and you repeat that agreement every time you submit content:</p>
  <ol>{items}</ol>
  <h2>What happens to uploads</h2>
  <p>Uploads are held privately until a person approves them. We re-encode images, which removes hidden metadata such as location, and we may refuse, edit for formatting, or remove any content at any time, including on a rights or safety complaint. Report a problem at {e(SITE["contact"])}.</p>
  <h2>Accounts</h2>
  <p>We may suspend an account that breaks these terms or the reviewer standards. You can ask us to delete your account at any time.</p>
</article>"""

def not_found():
    return """<article class="page"><h1>Page not found</h1><p>That page does not exist. Try the <a href="index.html">home page</a> or <a href="reviews.html">all reviews</a>.</p></article>"""

OUT = PUBLIC

def write(path, text):
    p = OUT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)

def category_home(d):
    c = CAT[d["category"]]
    crit = ", ".join(c["criteria"])
    tag = d.get("tagline") or c["blurb"]
    return f"""<section class="hero c-{e(c["slug"])}" style="padding-bottom:6px">
  <h1 style="font-size:clamp(1.8rem,4.5vw,2.6rem)">{e(tag)}</h1>
  <p class="lead">{e(c["blurb"])}</p>
  <p class="facts">Every review here is scored on: <b>{e(crit)}</b>. {e(d["name"])} is part of <a href="https://{MAIN}/">{e(SITE["name"])}</a> and follows the same <a href="how-we-review.html">independence rules</a>.</p>
</section>
{controls(False)}
{sample_note()}
<div class="grid" id="grid">
  {"".join(card(r) for r in sorted_reviews())}
</div>
<div class="empty" id="empty" hidden>No reviews match your search.</div>"""

def build_feed_and_sitemap(static, reviews):
    real_reviews = sorted_reviews([r for r in reviews if real(r)])
    urls = [f"{BASE}/" if p == "index.html" else f"{BASE}/{p}" for p in static] + \
           [review_url(r) for r in real_reviews if host_of(r) == HOST]  # a sitemap may only list its own host
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
          "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
    updated = (real_reviews[0]["date"] if real_reviews else SITE["policies_updated"]) + "T00:00:00Z"
    entries = "".join(
        f'  <entry><title>{e(r["title"])}</title><link href="{review_url(r)}"/>'
        f'<id>{review_url(r)}</id><updated>{r["date"]}T00:00:00Z</updated>'
        f'<summary>{e(r["verdict"])}</summary></entry>\n' for r in real_reviews)
    write("feed.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">\n'
          f'  <title>{e(NAME)}</title><link href="{BASE}/"/><id>{BASE}/</id><updated>{updated}</updated>\n{entries}</feed>\n')
    return real_reviews

def build_main():
    global HOST, NAME, BASE, NAV, OUT, CATS, REVIEWS
    HOST, NAME, BASE, NAV, OUT = MAIN, SITE["name"], f"https://{MAIN}", main_nav(), PUBLIC
    CATS, REVIEWS = ALL_CATS, ALL_REVIEWS
    site_ld = {"@context": "https://schema.org", "@type": "WebSite", "name": NAME, "url": BASE + "/",
               "potentialAction": {"@type": "SearchAction", "target": BASE + "/reviews.html?q={search_term_string}",
                                   "query-input": "required name=search_term_string"}}
    write("index.html", page("index.html", f'{NAME}: {SITE["tagline"]}', SITE["description"], home(), nav="home", jsonld=site_ld))
    write("reviews.html", page("reviews.html", f'All reviews | {NAME}', "Every review, searchable by category.", reviews_index(), nav="reviews"))
    for c in ALL_CATS:
        if c["slug"] in CAT_DOMAIN:
            continue  # lives on its own domain; src/worker.js redirects the old path
        write(f'{c["slug"]}.html', page(f'{c["slug"]}.html', f'{c["name"]} reviews | {NAME}', c["blurb"], category_page(c), nav=c["slug"]))
    write("how-we-review.html", page("how-we-review.html", f'How we review | {NAME}', "Independence rules, scoring and testing standards.", how_review(), nav="how"))
    write("how-we-make-money.html", page("how-we-make-money.html", f'How the site is funded | {NAME}', "How this site is funded and the rules that keep reviews independent.", how_money(), nav="money"))
    write("corrections.html", page("corrections.html", f'Corrections | {NAME}', "Corrections policy and log.", corrections()))
    write("suggest.html", page("suggest.html", f'Suggest a review | {NAME}', "Tell us what to review next.", suggest()))
    write("whats-next.html", page("whats-next.html", f'Our reviewers: the plan | {NAME}', "How reviewers are screened and the principles for our review community.", whats_next()))
    write("about.html", page("about.html", f'About | {NAME}', "About this site.", about()))
    for fn, ttl, body in (("signup.html", "Create your account", signup_page()), ("signin.html", "Sign in", signin_page()),
                          ("account.html", "Your account", account_page()), ("contributor-terms.html", "Contributor agreement", contributor_terms())):
        write(fn, page(fn, f"{ttl} | {NAME}", ttl, body, noindex=True))
    write("404.html", page("404.html", f'Not found | {NAME}', "Page not found.", not_found(), noindex=True))
    kept = [r for r in ALL_REVIEWS if host_of(r) == MAIN]
    for r in kept:
        write(f'reviews/{r["id"]}.html', review_page(r))
    static = ["index.html", "reviews.html", "how-we-review.html", "how-we-make-money.html", "corrections.html",
              "suggest.html", "whats-next.html", "about.html"] + [f'{c["slug"]}.html' for c in ALL_CATS if c["slug"] not in CAT_DOMAIN]
    real_reviews = build_feed_and_sitemap(static, ALL_REVIEWS)
    return len(kept), len(real_reviews), len(static) + 1

def build_category_site(d):
    global HOST, NAME, BASE, NAV, OUT, CATS, REVIEWS
    HOST, NAME, BASE, NAV = d["host"], d["name"], f'https://{d["host"]}', category_nav(d)
    OUT = PUBLIC / "_sites" / d["host"]
    CATS = [CAT[d["category"]]]
    REVIEWS = [r for r in ALL_REVIEWS if r["category"] == d["category"]]
    write("index.html", page("index.html", f'{NAME}: {d.get("tagline") or CAT[d["category"]]["blurb"]}', CAT[d["category"]]["blurb"], category_home(d), nav="home"))
    write("404.html", page("404.html", f'Not found | {NAME}', "Page not found.", not_found(), noindex=True))
    for r in REVIEWS:
        write(f'reviews/{r["id"]}.html', review_page(r))
    build_feed_and_sitemap(["index.html"], REVIEWS)
    return len(REVIEWS)

# ---------- build ----------
for old in (PUBLIC / "reviews").glob("*.html"):
    old.unlink()
shutil.rmtree(PUBLIC / "_sites", ignore_errors=True)
for slug in CAT_DOMAIN:  # stale page from before the category moved
    (PUBLIC / f"{slug}.html").unlink(missing_ok=True)

n_kept, n_real, n_pages = build_main()
for d in DOMAINS:
    if d["mode"] == "category":
        n = build_category_site(d)
        print(f'  {d["host"]}: {n} {d["category"]} reviews')

# routing table for src/worker.js: which host serves what, and where moved paths go
routes = {
    "main": MAIN,
    "sites": {d["host"]: {"category": d["category"]} for d in DOMAINS if d["mode"] == "category"},
    "moved": [{"host": d["host"], "paths": [f'/{d["category"]}.html'],
               "review_ids": [r["id"] for r in ALL_REVIEWS if r["category"] == d["category"]]}
              for d in DOMAINS if d["mode"] == "category"],
    "redirects": {d["host"]: (d["target"] if d["target"].startswith("https://") else f'https://{MAIN}{d["target"]}')
                  for d in DOMAINS if d["mode"] == "redirect"},
}
(ROOT / "src").mkdir(exist_ok=True)
(ROOT / "src" / "routes.json").write_text(json.dumps(routes, indent=2) + "\n")

print(f"Built {len(ALL_REVIEWS)} reviews ({n_real} real, {len(ALL_REVIEWS) - n_real} sample) and {n_pages} other pages.")
