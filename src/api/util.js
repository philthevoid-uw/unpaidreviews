// Shared helpers for the account and upload API. No framework: small, auditable functions.

export const TERMS_VERSION = "contributor-2026-11-v1";
export const DAY = 86400, HOUR = 3600;
export const now = () => Math.floor(Date.now() / 1000);

export const json = (data, status = 200, headers = {}) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...headers },
  });
export const fail = (status, message, extra = {}) => json({ ok: false, error: message, ...extra }, status);

export function b64url(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
export const randomToken = (n = 32) => b64url(crypto.getRandomValues(new Uint8Array(n)));
export const newId = () => randomToken(12);

export async function sha256hex(text) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// IPs are stored only as salted hashes (for rate limits and abuse review).
export const ipHash = (env, request) =>
  sha256hex((env.HASH_PEPPER || "dev-pepper") + "|" + (request.headers.get("CF-Connecting-IP") || "0"));

export function getCookie(request, name) {
  for (const part of (request.headers.get("Cookie") || "").split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return null;
}
export const SESSION_COOKIE = "__Host-ur_session";
export const sessionCookie = (value, maxAge) =>
  `${SESSION_COOKIE}=${value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;

// State-changing requests must come from our own pages: JSON content type (not sendable by a plain
// cross-site form) plus a same-origin Origin header. Cookies are also SameSite=Lax.
export function sameOrigin(request) {
  const origin = request.headers.get("Origin");
  if (!origin) return false;
  return new URL(origin).host === new URL(request.url).host;
}

export async function readJson(request, maxBytes = 64 * 1024) {
  const ct = request.headers.get("Content-Type") || "";
  if (!ct.startsWith("application/json")) throw new HttpError(415, "Send JSON.");
  const buf = await request.arrayBuffer();
  if (buf.byteLength > maxBytes) throw new HttpError(413, "Request too large.");
  try { return JSON.parse(new TextDecoder().decode(buf)); } catch { throw new HttpError(400, "Invalid JSON."); }
}

export class HttpError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export const isEmail = (s) => typeof s === "string" && s.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(s);
export const normEmail = (s) => String(s || "").trim().toLowerCase();

const RESERVED = /(admin|moderator|support|staff|official|unpaid|review|cloudflare|anthropic|claude|root|system)/i;
export function validHandle(h) {
  return typeof h === "string" && /^[A-Za-z0-9_]{3,24}$/.test(h) && !RESERVED.test(h);
}

export async function logEvent(env, kind, { userId = null, ip = null, detail = null } = {}) {
  await env.DB.prepare("INSERT INTO events (at, kind, user_id, ip_hash, detail) VALUES (?,?,?,?,?)")
    .bind(now(), kind, userId, ip, detail ? String(detail).slice(0, 500) : null).run();
}

// Count recent events to limit abuse. Returns true when the limit has been reached.
export async function limited(env, kind, { ip, userId, perIp, perUser, windowSec }) {
  const since = now() - windowSec;
  if (ip && perIp) {
    const r = await env.DB.prepare("SELECT COUNT(*) c FROM events WHERE kind=? AND ip_hash=? AND at>?").bind(kind, ip, since).first();
    if (r.c >= perIp) return true;
  }
  if (userId && perUser) {
    const r = await env.DB.prepare("SELECT COUNT(*) c FROM events WHERE kind=? AND user_id=? AND at>?").bind(kind, userId, since).first();
    if (r.c >= perUser) return true;
  }
  return false;
}

// Cloudflare Turnstile (free CAPTCHA alternative). Fails closed unless DEV_MODE is on.
export async function verifyTurnstile(env, token, request) {
  if (env.DEV_MODE === "1") return true;
  if (!env.TURNSTILE_SECRET || !token) return false;
  const body = new URLSearchParams({ secret: env.TURNSTILE_SECRET, response: String(token) });
  const ip = request.headers.get("CF-Connecting-IP");
  if (ip) body.set("remoteip", ip);
  const r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body });
  const j = await r.json().catch(() => ({}));
  return j.success === true;
}

export const MAX_TEXT = (s, n) => typeof s === "string" ? s.trim().slice(0, n) : "";
