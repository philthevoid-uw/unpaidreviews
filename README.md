# Unpaid Reviews (unpaidreviews.com): site files

A plain static website. No database, no framework, no server software.

## Adding a review
1. Open `data/reviews.json`.
2. Copy an entry inside `"reviews"`. Give it a new unique `"id"` (lowercase, hyphens, no spaces), then replace every field with your own text.
3. Delete `"sample": true` from real reviews. Sample reviews are hidden from search engines and left out of the sitemap and RSS feed.
4. The four `"criteria"` names must match the category's list at the top of the file, or the build stops and tells you why.
5. Run `python3 build.py   # writes the site into the public folder` to regenerate every page, then upload the folder.

## Domains and categories
Everything is controlled from `data/reviews.json`; there is no other config to touch.

- **New category:** add an entry to `"categories"` (slug, name, blurb, four criteria). It appears on the main site automatically.
- **Give a category its own domain:** add to `"domains"`:
  `{"host": "cellarcommunity.com", "mode": "category", "category": "wine", "name": "Cellar Community", "tagline": "..."}`
  The domain becomes its own small site (home, reviews, sitemap, feed) and the main site sends that category's pages there with a 301.
  Remove the entry and the category goes back to the main site.
- **Point an extra domain at the main site:** `{"host": "ireviewtravel.com", "mode": "redirect", "target": "/travel.html"}`.
  Change `"mode"` to `"category"` later to turn it into a full site.
- After editing, run `python3 build.py` and push. It rewrites `public/` and `src/routes.json`, which `src/worker.js` reads. Deploys run `npx wrangler deploy` (see `wrangler.jsonc`).
- **One-time per new domain in Cloudflare:** add the domain as a site (Free), change its nameservers at the registrar, then in Workers & Pages, `unpaidreviews`, Settings, Domains & Routes, add the domain and its `www`. Policy pages (how I review, funding, corrections) live only on unpaidreviews.com; the other domains link to them.

## Before you launch
- Delete the six SAMPLE reviews.
- Check the contact address (`site.contact` in `data/reviews.json`) is a real, working mailbox.
- Rewrite `about.html` text (in `build.py`, function `about`) in your own words.
- Read the funding and independence pages (`how-we-make-money.html`, `how-we-review.html`). They make public promises, so make sure each one is true for you.
- If you add ads or any income later, update the status and change log on the funding page first.

## Putting it online
Any static host works (Netlify, Cloudflare Pages, GitHub Pages). Upload this folder, then in your domain registrar's DNS settings point `unpaidreviews.com` at the host. The host's setup screen gives the exact records to add.

## Files
- `data/reviews.json`: site name, tagline, contact, categories, corrections, all reviews
- `build.py`: generates the HTML pages (needs only Python 3)
- `src/worker.js`, `wrangler.jsonc`: routes each domain to its pages; `src/routes.json` is generated
- `css/style.css`, `js/app.js`: styling, and search/filter/sort
- Generated (do not hand-edit, they are overwritten): all `.html` pages, `reviews/*.html`, `sitemap.xml`, `feed.xml`, `robots.txt`

## Importing wine notes from CellarTracker
1. On the CellarTracker website (desktop), open the view with your tasting notes and click Export, choosing CSV. Save the file into the `imports` folder (it is never uploaded to GitHub).
2. Run `python3 tools/import_cellartracker.py imports/yourfile.csv`. It writes private drafts to `imports/drafts.json` and ignores inventory, locations, quantities, prices and private notes.
3. Choose the drafts to publish, copy them into `data/reviews.json`, and fill in `acquired` (how the bottle was obtained). The build refuses real reviews without it.
4. Run `python3 build.py`, then push.
