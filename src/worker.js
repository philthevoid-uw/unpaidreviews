// Routes every domain this site answers on. The table in routes.json is written by
// build.py from the "domains" list in data/reviews.json. Do not edit routes.json by hand.
import ROUTES from "./routes.json";
import { handleApi, isApiPath } from "./api/index.js";

// "/" -> "/index.html", "/about" -> "/about.html", "/css/style.css" stays as is.
function toFile(path) {
  if (path.endsWith("/")) return path + "index.html";
  return path.split("/").pop().includes(".") ? path : path + ".html";
}

const redirect = (to) => new Response(null, { status: 301, headers: { Location: to } });

async function notFound(env, request, url, prefix) {
  const target = new URL(url);
  target.pathname = prefix + "/404.html";
  const page = await env.ASSETS.fetch(new Request(target, { method: "GET", headers: request.headers }));
  return new Response(page.body, { status: 404, headers: page.headers });
}

// Headers added to every response on every domain.
const SECURITY_HEADERS = {
  "Content-Security-Policy": [
    "default-src 'self'", "script-src 'self' https://challenges.cloudflare.com",
    "style-src 'self' 'unsafe-inline'", "font-src 'self'",
    "img-src 'self' data:", "connect-src 'self' https://*.cloudflarestream.com https://upload.videodelivery.net",
    "frame-src https://challenges.cloudflare.com https://*.cloudflarestream.com",
    "media-src 'self' https://*.cloudflarestream.com", "object-src 'none'",
    "base-uri 'self'", "form-action 'self'", "frame-ancestors 'none'",
  ].join("; "),
  "Strict-Transport-Security": "max-age=15552000",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
  "Cross-Origin-Opener-Policy": "same-origin",
};

// RFC 9116. Renew the Expires date at least once a year.
const SECURITY_TXT = `Contact: mailto:hello@unpaidreviews.com
Expires: 2027-11-26T00:00:00.000Z
Preferred-Languages: en
Canonical: https://unpaidreviews.com/.well-known/security.txt
`;

function withSecurityHeaders(res) {
  const out = new Response(res.body, res);
  for (const [k, v] of Object.entries(SECURITY_HEADERS)) {
    if (k === "Content-Security-Policy" && out.headers.has(k)) continue; // stricter per-response policy wins (media, sign-in page)
    out.headers.set(k, v);
  }
  return out;
}

export default {
  async fetch(request, env) {
    return withSecurityHeaders(await route(request, env));
  },
};

async function route(request, env) {
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

    if (url.pathname === "/.well-known/security.txt")
      return new Response(SECURITY_TXT, { headers: { "Content-Type": "text/plain; charset=utf-8" } });

    // Accounts, uploads and moderation live on the main domain only
    if (bare === ROUTES.main && isApiPath(url.pathname)) return handleApi(request, env);

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
    const shared = file.startsWith("/css/") || file.startsWith("/js/") || file.startsWith("/fonts/");
    const prefix = site && !shared ? `/_sites/${bare}` : "";
    const target = new URL(url);
    target.pathname = prefix + file;
    const res = await env.ASSETS.fetch(new Request(target, { method: "GET", headers: request.headers }));
    return res.status === 404 ? notFound(env, request, url, prefix) : res;
}
