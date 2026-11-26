#!/usr/bin/env python3
"""Builds the Unpaid Reviews static site from data/reviews.json.

Run:  python3 build.py
Writes: index.html, reviews.html, <category>.html, policy pages, reviews/<id>.html,
        404.html, sitemap.xml, robots.txt, feed.xml
Needs only Python 3.
"""
import json
from datetime import datetime
from html import escape as e
from pathlib import Path

ROOT = Path(__file__).parent
PUBLIC = ROOT / "public"
data = json.loads((ROOT / "data" / "reviews.json").read_text())
SITE, CATS, REVIEWS, CORRECTIONS = data["site"], data["categories"], data["reviews"], data["corrections"]
BASE = f'https://{SITE["domain"]}'
CAT = {c["slug"]: c for c in CATS}

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

NAV = [("reviews.html", "All reviews", "reviews")] + \
      [(f'{c["slug"]}.html', c["name"], c["slug"]) for c in CATS] + \
      [("how-we-review.html", "How I review", "how"), ("how-we-make-money.html", "Funding", "money")]

def page(path, title, desc, body, nav="", noindex=False, jsonld=None, og_type="website"):
    depth = path.count("/")
    root = "../" * depth
    robots = '<meta name="robots" content="noindex">\n' if noindex else ""
    ld = ""
    if jsonld:
        ld = '<script type="application/ld+json">' + json.dumps(jsonld).replace("</", "<\\/") + "</script>\n"
    links = "".join(
        f'<a href="{root}{href}"' + (' aria-current="page"' if nav == key else "") + f">{e(label)}</a>"
        for href, label, key in NAV)
    canon = f"{BASE}/{'' if path == 'index.html' else path}"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{robots}<link rel="canonical" href="{canon}">
<meta property="og:site_name" content="{e(SITE["name"])}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{canon}">
<meta name="twitter:card" content="summary">
<link rel="alternate" type="application/atom+xml" title="{e(SITE["name"])}" href="{root}feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{root}css/style.css">
{ld}</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site"><div class="wrap">
  <a class="brand" href="{root}index.html">Unpaid <span>Reviews</span></a>
  <nav aria-label="Main">{links}</nav>
</div></header>
<main id="main" class="wrap">
{body}
</main>
<footer><div class="wrap"><div class="cols">
  <div><b>{e(SITE["name"])}</b><br>Independent. Paid for by the reviewer: no conflicts of interest, no affiliate links, no sponsorships, no gifts, and all revenue sources disclosed.</div>
  <div><h4>Read</h4><ul>
    <li><a href="{root}how-we-review.html">How I review</a></li>
    <li><a href="{root}how-we-make-money.html">How the site is funded</a></li>
    <li><a href="{root}corrections.html">Corrections</a></li>
    <li><a href="{root}feed.xml">RSS feed</a></li></ul></div>
  <div><h4>Get involved</h4><ul>
    <li><a href="{root}suggest.html">Suggest the next review</a></li>
    <li><a href="{root}whats-next.html">Reader reviews: the plan</a></li>
    <li><a href="{root}about.html">About</a></li>
    <li><a href="mailto:{e(SITE["contact"])}">{e(SITE["contact"])}</a></li></ul></div>
</div></div></footer>
<script src="{root}js/app.js"></script>
</body>
</html>
"""

# ---------- components ----------
def card(r, root=""):
    c = CAT[r["category"]]
    text = f'{r["title"]} {r["subject"]} {r.get("place", "")} {r["verdict"]}'.lower()
    sample = '<span class="badge">SAMPLE</span>' if r.get("sample") else ""
    sub = " · ".join(x for x in [r["subject"], r.get("place", "")] if x)
    return f"""<a class="card c-{e(r["category"])}" href="{root}reviews/{e(r["id"])}.html" data-category="{e(r["category"])}" data-score="{r["score"]}" data-date="{e(r["date"])}" data-text="{e(text)}">
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
  <p class="lead">Products, travel, restaurants and wine, bought and visited with my own money, scored on published criteria, with no conflicts of interest, and any associations minimized to prevent any influencing revenue streams and all revenue sources disclosed.</p>
  <form class="searchbar" action="reviews.html" method="get" role="search">
    <input type="search" name="q" placeholder="Search products, places, restaurants…" aria-label="Search reviews">
    <button class="btn" type="submit">Search</button>
  </form>
</section>
<div class="proof">
  <div><b>0</b><span>affiliate links, ever</span></div>
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
<h2>How I protect independence</h2>
<div class="pillars">
  <div class="pillar"><h3>I pay for everything</h3><p>Products are bought at retail. Meals and trips are paid in full, with no reviewer discounts and no tourism-board hosting.</p></div>
  <div class="pillar"><h3>Nothing is for sale</h3><p>No affiliate links, no sponsored content and no payment that could influence what I say or how I score. Any association that could create a revenue stream is minimized, and every revenue source is disclosed.</p></div>
  <div class="pillar"><h3>Mistakes are public</h3><p>Errors are fixed in the open and logged on the <a href="corrections.html">corrections page</a>. Scores are never changed because someone complained.</p></div>
</div>
<div class="band">
  <div><h2>You pick what's next</h2><p>Tell me what to buy, visit or eat. Suggestions from the businesses involved are ignored.</p></div>
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
    skip = (f'<h2>What I would skip</h2><ul>{bullets(r["skip"])}</ul>') if r.get("skip") else ""
    related = [x for x in sorted_reviews() if x["category"] == r["category"] and x["id"] != r["id"]][:2]
    rel = ""
    if related:
        rel = '<h2>More in ' + e(c["name"]) + '</h2><div class="grid">' + "".join(card(x, "../") for x in related) + "</div>"
    body = f"""<article class="review c-{e(r["category"])}">
  <a class="back" href="../{e(r["category"])}.html">← {e(c["name"])}</a>
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
  <p class="fine">Spotted a mistake? See the <a href="../corrections.html">corrections policy</a>. Read <a href="../how-we-review.html">how I review</a>.</p>
  {rel}
</article>"""
    ld = None
    if real(r):
        ld = {"@context": "https://schema.org", "@type": "Review",
              "itemReviewed": {"@type": c["kind"], "name": r["subject"]},
              "reviewRating": {"@type": "Rating", "ratingValue": r["score"], "bestRating": 10, "worstRating": 0},
              "author": {"@type": "Organization", "name": SITE["name"]},
              "datePublished": r["date"], "reviewBody": r["verdict"]}
    return page(f'reviews/{r["id"]}.html', f'{r["title"]} | {SITE["name"]}', r["verdict"], body,
                nav=r["category"], noindex=not real(r), jsonld=ld, og_type="article")

def how_review():
    cat_rows = "".join(f'<tr><td><b>{e(c["name"])}</b></td><td>{e(", ".join(c["criteria"]))}</td></tr>' for c in CATS)
    return f"""<article class="page">
  <h1>How I review</h1>
  <p>Trust is the only thing this site offers, so the rules are written down and apply to every review.</p>
  <h2>Independence rules</h2>
  <ul>
    <li><b>I pay my own way.</b> Products are bought at normal retail price. Meals, hotels and tours are paid in full.</li>
    <li><b>No affiliate links.</b> I earn nothing when you click or buy.</li>
    <li><b>No sponsored content, gifts, comps or press trips.</b> If something is given to me without being asked (a free dessert, an upgrade), I say so at the top of the review.</li>
    <li><b>Disclosure on every review.</b> Each page states exactly how the item was obtained.</li>
    <li><b>No conflicts of interest.</b> I do not review businesses owned by or employing people I know. If a relationship exists, I skip the review or disclose it.</li>
    <li><b>Associations minimized.</b> I keep any association with a reviewed business, brand or sponsor to a minimum so that no revenue stream can influence a review, and I disclose any that remain.</li>
    <li><b>All revenue sources disclosed.</b> Every way the site earns money is listed on <a href="how-we-make-money.html">how the site is funded</a>.</li>
    <li><b>No pre-publication previews.</b> Businesses never see a review before it goes live, and cannot change an opinion or a score.</li>
  </ul>
  <p>How the site pays for itself is covered on a separate page: <a href="how-we-make-money.html">how the site is funded</a>.</p>
  <h2>How scoring works</h2>
  <p>Each review rates four criteria from 1 to 10. The criteria depend on the category:</p>
  <table><tr><th>Category</th><th>Criteria</th></tr>{cat_rows}</table>
  <p>The overall score is a considered judgment, not a mechanical average, and the review explains it.</p>
  <p><b>Wine quick notes:</b> older bottles from my CellarTracker history appear as short quick notes with a score and, where I wrote one, a tasting note. CellarTracker uses a 100-point scale, so a 90 there is shown here as 9.0 out of 10. Quick notes have no criteria breakdown, and each one says how the bottle was acquired, or that I no longer have a record.</p>
  <p><b>Scale:</b> 9–10 exceptional · 7–8 good · 5–6 mixed · 3–4 poor · 1–2 avoid.</p>
  <h2>Testing standards</h2>
  <ul>
    <li><b>Products:</b> used for a meaningful period before publishing, with the duration stated and at least one alternative compared where possible.</li>
    <li><b>Travel:</b> visited in person, with the dates and season stated and costs given in what I actually paid.</li>
    <li><b>Wine:</b> tasted with the bottle's vintage, producer and price noted, with how long it was open and how it changed where I tracked that.</li>
    <li><b>Restaurants:</b> visited at least twice where practical, ordering and paying like any customer, without announcing that I write reviews.</li>
  </ul>
  <h2>Every review has the same parts</h2>
  <p>Bottom line, who it is for, how I tested or visited, scores, what worked, flaws but not dealbreakers, and what I would skip. Using one format makes reviews comparable and makes it harder to hide a weak spot.</p>
  <h2>Updates and corrections</h2>
  <p>Reviews are dated and updated when things change. Errors are corrected in the open: see <a href="corrections.html">corrections</a>.</p>
</article>"""

def how_money():
    return f"""<article class="page">
  <h1>How the site is funded</h1>
  <div class="status"><b>Status as of {e(pretty(SITE["policies_updated"]))}:</b> no ads are running, no affiliate links exist, and the site earns no money. Any change to this will be announced here <i>before</i> it takes effect.</div>
  <h2>What will never change</h2>
  <ul>
    <li>No affiliate links or commissions on anything I review.</li>
    <li>No payment of any kind from a business, brand or person I review, or from their competitors, in exchange for coverage, placement, ranking or silence.</li>
    <li>No sponsored content, gifts, free stays, free meals or free products.</li>
    <li>No link between the money the site earns and which products, places or restaurants are reviewed, or how they are scored.</li>
    <li>Any association that could create a revenue stream is minimized, and every revenue source is disclosed on this page.</li>
  </ul>
  <h2>If advertising is ever added</h2>
  <p>I am considering whether to run advertising. I have not decided. If I do, these rules will apply, and I will publish the specific details on this page before any ad runs:</p>
  <ul>
    <li><b>Automated, with no deals.</b> Ads are bought and priced automatically through an ad marketplace. There is no sales team, no negotiated pricing and no special terms for anyone.</li>
    <li><b>No favoritism and no penalties.</b> Neither pricing nor ad placement depends on what I have reviewed, what I plan to review, or how anything was scored. Advertisers get no advance look at reviews and no influence over them.</li>
    <li><b>Same rules for every advertiser.</b> I will not hand-pick advertisers. Any restrictions will be broad categories applied site-wide (for example, no gambling ads) and listed publicly.</li>
    <li><b>Clearly labeled and separate.</b> Ads will be marked as ads and kept out of review text.</li>
    <li><b>Reviewed businesses.</b> I will publish the exact rule for ads from businesses I have reviewed before ads start.</li>
  </ul>
  <h2>Other ways the site could be supported</h2>
  <p>Reader support (donations or memberships) is one option I may explore. Any model I use must pass one test: no revenue is tied to the products, places or restaurants I review. Every source of revenue will be disclosed on this page.</p>
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
  <p>If I get a fact wrong, I fix it, add a visible note on the review, and list it here. Businesses may point out factual errors (wrong price, wrong hours, wrong dish). They cannot change an opinion or a score.</p>
  <p>To report an error, email <a href="mailto:{e(SITE["contact"])}">{e(SITE["contact"])}</a>.</p>
  <h2>Corrections log</h2>
  {log}
</article>"""

def suggest():
    return f"""<article class="page">
  <h1>Suggest the next review</h1>
  <p>Tell me what to buy, visit or eat. I read every suggestion and choose based on how many readers want it, not on who is asking.</p>
  <ul>
    <li>Suggestions from the business, brand or people involved are ignored.</li>
    <li>I pay for everything I review, so I cannot promise to get to every request.</li>
    <li>Include the exact product, place or restaurant, and what you want to know.</li>
  </ul>
  <p><a class="btn" href="mailto:{e(SITE["contact"])}?subject=Review%20suggestion">Email a suggestion</a></p>
  <p>Or write to <b>{e(SITE["contact"])}</b>.</p>
</article>"""

def whats_next():
    return f"""<article class="page">
  <h1>Reader reviews: the plan</h1>
  <p class="samplebar">Draft. Nothing here is live yet.</p>
  <p>For now, every review is written by one person. The plan is to open the site to reader reviews once the foundation is solid. These are the principles I intend to hold to:</p>
  <ul>
    <li><b>Reviews from real experience.</b> Readers will say how they used the product or visited the place.</li>
    <li><b>No incentives.</b> Nobody can offer, request or reward a review.</li>
    <li><b>Businesses cannot edit or buy their way out.</b> They may respond publicly to a review, and the review stays.</li>
    <li><b>Transparent moderation.</b> Published rules, and a regular report on what was removed and why.</li>
    <li><b>Reader and editor ratings stay separate.</b> My scores will never be blended into the community score.</li>
  </ul>
  <h2>Lessons from wine communities</h2>
  <p>Wine sites such as CellarTracker and Vivino have run large reader communities for years. Here is what I plan to borrow and what I plan to do differently.</p>
  <ul>
    <li><b>Notes tied to a real bottle.</b> A review says which vintage was opened, how it was stored and served, and how it was acquired. One bottle's flaw does not make another reader's review wrong.</li>
    <li><b>Handles, not real names.</b> Readers choose a public handle. Real names stay private unless the reader chooses to show them.</li>
    <li><b>Comments that notify.</b> When someone replies to a comment, the original commenter is told. Community members on existing sites say missing reply alerts are a common frustration.</li>
    <li><b>Follow a taster, not a score.</b> Readers can follow people whose palates match theirs, as on CellarTracker and Vivino, instead of relying on one blended number.</li>
    <li><b>No scores from too few voices.</b> A community average appears only after enough independent ratings, with the count always shown.</li>
    <li><b>No republished professional scores.</b> Critics' points and notes are copyrighted, so they are not copied here.</li>
    <li><b>Your own words only.</b> Notes written by AI or copied from elsewhere are not allowed.</li>
    <li><b>Community kept apart from selling.</b> There are no shop links and no affiliate links, so nothing on the site pushes readers toward buying.</li>
    <li><b>Cellar tools stay elsewhere.</b> Inventory, bin locations and drinking windows are better handled by CellarTracker, so this site covers published reviews only.</li>
  </ul>
  <p>Want to be told when it opens? Email <b>{e(SITE["contact"])}</b>.</p>
</article>"""

def about():
    return f"""<article class="page">
  <h1>About</h1>
  <p class="samplebar">Placeholder. Replace this with a short note about why you started the site and what you review. Share only what you are comfortable making public.</p>
  <p>{e(SITE["name"])} publishes independent reviews of products, travel, restaurants and wine. Every review says how the item was acquired, new reviews are paid for by the reviewer, associations are minimized so no revenue stream can influence what gets reviewed, and all revenue sources are disclosed. See <a href="how-we-review.html">how I review</a> and <a href="how-we-make-money.html">how the site is funded</a>.</p>
</article>"""

def not_found():
    return """<article class="page"><h1>Page not found</h1><p>That page does not exist. Try the <a href="index.html">home page</a> or <a href="reviews.html">all reviews</a>.</p></article>"""

def write(path, text):
    p = PUBLIC / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)

# ---------- build ----------
for old in (PUBLIC / "reviews").glob("*.html"):
    old.unlink()

site_ld = {"@context": "https://schema.org", "@type": "WebSite", "name": SITE["name"], "url": BASE + "/",
           "potentialAction": {"@type": "SearchAction", "target": BASE + "/reviews.html?q={search_term_string}",
                               "query-input": "required name=search_term_string"}}
write("index.html", page("index.html", f'{SITE["name"]}: {SITE["tagline"]}', SITE["description"], home(), nav="home", jsonld=site_ld))
write("reviews.html", page("reviews.html", f'All reviews | {SITE["name"]}', "Every review, searchable by category.", reviews_index(), nav="reviews"))
for c in CATS:
    write(f'{c["slug"]}.html', page(f'{c["slug"]}.html', f'{c["name"]} reviews | {SITE["name"]}', c["blurb"], category_page(c), nav=c["slug"]))
write("how-we-review.html", page("how-we-review.html", f'How I review | {SITE["name"]}', "Independence rules, scoring and testing standards.", how_review(), nav="how"))
write("how-we-make-money.html", page("how-we-make-money.html", f'How the site is funded | {SITE["name"]}', "How this site is funded and the rules that keep reviews independent.", how_money(), nav="money"))
write("corrections.html", page("corrections.html", f'Corrections | {SITE["name"]}', "Corrections policy and log.", corrections()))
write("suggest.html", page("suggest.html", f'Suggest a review | {SITE["name"]}', "Tell me what to review next.", suggest()))
write("whats-next.html", page("whats-next.html", f'Reader reviews: the plan | {SITE["name"]}', "Principles for opening the site to reader reviews.", whats_next()))
write("about.html", page("about.html", f'About | {SITE["name"]}', "About this site.", about()))
write("404.html", page("404.html", f'Not found | {SITE["name"]}', "Page not found.", not_found(), noindex=True))
for r in REVIEWS:
    write(f'reviews/{r["id"]}.html', review_page(r))

# sitemap, robots, feed
static = ["index.html", "reviews.html", "how-we-review.html", "how-we-make-money.html", "corrections.html",
          "suggest.html", "whats-next.html", "about.html"] + [f'{c["slug"]}.html' for c in CATS]
urls = [f"{BASE}/" if p == "index.html" else f"{BASE}/{p}" for p in static]
urls += [f'{BASE}/reviews/{r["id"]}.html' for r in REVIEWS if real(r)]
write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
      "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n")
write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
real_reviews = sorted_reviews([r for r in REVIEWS if real(r)])
updated = (real_reviews[0]["date"] if real_reviews else SITE["policies_updated"]) + "T00:00:00Z"
entries = "".join(
    f'  <entry><title>{e(r["title"])}</title><link href="{BASE}/reviews/{r["id"]}.html"/>'
    f'<id>{BASE}/reviews/{r["id"]}.html</id><updated>{r["date"]}T00:00:00Z</updated>'
    f'<summary>{e(r["verdict"])}</summary></entry>\n' for r in real_reviews)
write("feed.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">\n'
      f'  <title>{e(SITE["name"])}</title><link href="{BASE}/"/><id>{BASE}/</id><updated>{updated}</updated>\n{entries}</feed>\n')

print(f"Built {len(REVIEWS)} reviews ({len(real_reviews)} real, {len(REVIEWS) - len(real_reviews)} sample) and {len(static) + 1} other pages.")
