// Routes every domain this site answers on. The table in routes.json is written by
// build.py from the "domains" list in data/reviews.json. Do not edit routes.json by hand.
import ROUTES from "./routes.json";

// "/" -> "/index.html", "/about" -> "/about.html", "/css/style.css" stays as is.
function toFile(path) {
  if (path.endsWith("/")) return path + "index.html";
  return path.split("/").pop().includes(".") ? path : path + ".html";
}

const redirect = (to) => new Response(null, { status: 301, headers: { Location: to } });

async function notFound(env, request, url, prefix) {
  const target = new URL(url);
  target.pathname = prefix + "/404.html";
  const page = await env.ASSETS.fetch(new Request(target, request));
  return new Response(page.body, { status: 404, headers: page.headers });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const host = url.hostname.toLowerCase();
    const bare = host.startsWith("www.") ? host.slice(4) : host;
    const known = bare === ROUTES.main || bare in ROUTES.sites || bare in ROUTES.redirects;

    // www -> bare domain, keeping path and query
    if (known && host !== bare) return redirect(`https://${bare}${url.pathname}${url.search}`);

    // Redirect-only domains
    if (bare in ROUTES.redirects) {
      const to = ROUTES.redirects[bare];
      return redirect(to.includes("?") ? to : to + url.search);
    }

    const file = toFile(url.pathname);
    const site = ROUTES.sites[bare];

    if (!site) {
      // Main site: hide per-domain folders, and send moved categories to their own domain
      if (file.startsWith("/_sites/")) return notFound(env, request, url, "");
      for (const m of ROUTES.moved) {
        if (m.paths.includes(file)) return redirect(`https://${m.host}/${url.search}`);
        const hit = file.match(/^\/reviews\/([^/]+)\.html$/);
        if (hit && m.review_ids.includes(hit[1])) return redirect(`https://${m.host}${file}`);
      }
    }

    // Every domain shares one stylesheet and script; pages and feeds are per domain.
    const shared = file.startsWith("/css/") || file.startsWith("/js/");
    const prefix = site && !shared ? `/_sites/${bare}` : "";
    const target = new URL(url);
    target.pathname = prefix + file;
    const res = await env.ASSETS.fetch(new Request(target, request));
    return res.status === 404 ? notFound(env, request, url, prefix) : res;
  },
};
