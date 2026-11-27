// Email-link sign-in (no passwords). Sign-up records the contributor agreements before anything else.
import { TERMS_VERSION, DAY, HOUR, now, json, fail, readJson, randomToken, sha256hex, newId, ipHash, getCookie, SESSION_COOKIE,
  sessionCookie, sameOrigin, isEmail, normEmail, validHandle, logEvent, limited, verifyTurnstile, HttpError } from "./util.js";
import { sendMail, mailConfigured } from "./mail.js";

const SESSION_DAYS = 14, LINK_MINUTES = 15;

export async function currentUser(env, request) {
  const raw = getCookie(request, SESSION_COOKIE);
  if (!raw) return null;
  const row = await env.DB.prepare(
    `SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.hash = ? AND s.expires_at > ?`)
    .bind(await sha256hex(raw), now()).first();
  return row && row.status !== "suspended" ? row : null;
}

export function publicUser(u) {
  return { id: u.id, handle: u.handle, email: u.email, role: u.role, status: u.status,
    applicant_status: u.applicant_status, trust: u.trust, terms_version: u.terms_version };
}

const isAdminEmail = (env, email) => (env.ADMIN_EMAILS || "").toLowerCase().split(",").map((s) => s.trim()).filter(Boolean).includes(email);

async function issueLink(env, request, user) {
  const token = randomToken(32);
  await env.DB.prepare("INSERT INTO login_tokens (hash, user_id, expires_at, created_at) VALUES (?,?,?,?)")
    .bind(await sha256hex(token), user.id, now() + LINK_MINUTES * 60, now()).run();
  const url = `${new URL(request.url).origin}/api/auth/verify?token=${token}`;
  return sendMail(env, {
    to: user.email,
    subject: "Your Unpaid Reviews sign-in link",
    text: `Use this link to sign in (valid ${LINK_MINUTES} minutes, works once):\n\n${url}\n\nIf you didn't ask for this, ignore this email. Nobody can sign in without it.`,
  });
}

// Step 1 of becoming a reviewer: create the account and accept the contributor agreements.
export async function signup(request, env) {
  if (!sameOrigin(request)) return fail(403, "Bad origin.");
  if (!mailConfigured(env)) return fail(503, "Sign-up is not open yet.");
  const b = await readJson(request);
  const email = normEmail(b.email), handle = String(b.handle || "").trim();
  const t = b.terms || {};
  if (!isEmail(email)) return fail(400, "Enter a valid email address.");
  if (!validHandle(handle)) return fail(400, "Handle: 3 to 24 letters, numbers or underscores, and nothing that suggests staff or the site.");
  if (t.malicious !== true || t.responsible !== true || t.rights !== true)
    return fail(400, "You need to agree to all three statements to create an account.");
  const ip = await ipHash(env, request);
  if (await limited(env, "signup", { ip, perIp: 5, windowSec: HOUR })) return fail(429, "Too many attempts. Try again later.");
  if (!(await verifyTurnstile(env, b.turnstile, request))) return fail(400, "Verification failed. Reload and try again.");
  await logEvent(env, "signup", { ip });

  let user = await env.DB.prepare("SELECT * FROM users WHERE email = ?").bind(email).first();
  if (!user) {
    const taken = await env.DB.prepare("SELECT 1 FROM users WHERE handle = ?").bind(handle).first();
    if (taken) return fail(409, "That handle is taken.");
    const id = newId();
    const admin = isAdminEmail(env, email);
    await env.DB.prepare(`INSERT INTO users (id,email,handle,role,applicant_status,trust,terms_version,terms_accepted_at,created_at)
      VALUES (?,?,?,?,?,?,?,?,?)`)
      .bind(id, email, handle, admin ? "admin" : "reviewer", admin ? "approved" : "none", admin ? "green" : "new", TERMS_VERSION, now(), now()).run();
    await logEvent(env, "terms_accepted", { userId: id, ip, detail: TERMS_VERSION });
    user = { id, email };
  }
  // Same neutral response whether or not the email already had an account.
  await issueLink(env, request, user);
  return json({ ok: true, message: "Check your email for a sign-in link." });
}

export async function login(request, env) {
  if (!sameOrigin(request)) return fail(403, "Bad origin.");
  if (!mailConfigured(env)) return fail(503, "Sign-in is not open yet.");
  const b = await readJson(request);
  const email = normEmail(b.email);
  if (!isEmail(email)) return fail(400, "Enter a valid email address.");
  const ip = await ipHash(env, request);
  if (await limited(env, "login", { ip, perIp: 10, windowSec: HOUR })) return fail(429, "Too many attempts. Try again later.");
  if (!(await verifyTurnstile(env, b.turnstile, request))) return fail(400, "Verification failed. Reload and try again.");
  await logEvent(env, "login", { ip });
  const user = await env.DB.prepare("SELECT * FROM users WHERE email = ?").bind(email).first();
  if (user && user.status !== "suspended" && !(await limited(env, "link", { userId: user.id, perUser: 5, windowSec: HOUR }))) {
    await logEvent(env, "link", { userId: user.id, ip });
    await issueLink(env, request, user);
  }
  return json({ ok: true, message: "If that email has an account, a sign-in link is on its way." });
}

const page = (title, body, status = 200) => new Response(
  `<!DOCTYPE html><meta charset="utf-8"><meta name="robots" content="noindex"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title>
<style>body{font:16px/1.6 system-ui,sans-serif;max-width:30rem;margin:12vh auto;padding:0 1rem;color:#1d1b18}button{font:inherit;padding:.6rem 1.2rem;border:0;border-radius:6px;background:#1f5b47;color:#fff;cursor:pointer}</style>${body}`,
  { status, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'" } });

// GET only shows a button. Email scanners that prefetch links therefore cannot use up the token.
export function verifyPage(url) {
  const token = (url.searchParams.get("token") || "").replace(/[^A-Za-z0-9_-]/g, "");
  return page("Sign in", `<h1>Sign in to Unpaid Reviews</h1><p>Press the button to finish signing in on this device.</p>
<form method="post" action="/api/auth/verify"><input type="hidden" name="token" value="${token}"><button>Sign in</button></form>`);
}

export async function verify(request, env) {
  if (!sameOrigin(request)) return page("Sign in", "<p>Please open the link from your email again.</p>", 403);
  const form = await request.formData();
  const token = String(form.get("token") || "");
  const hash = await sha256hex(token);
  const claimed = await env.DB.prepare("UPDATE login_tokens SET used_at = ? WHERE hash = ? AND used_at IS NULL AND expires_at > ? RETURNING user_id")
    .bind(now(), hash, now()).first();
  if (!claimed) return page("Link expired", "<h1>That link has expired or was already used.</h1><p><a href=\"/signin.html\">Request a new one</a>.</p>", 400);
  const user = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(claimed.user_id).first();
  if (!user || user.status === "suspended") return page("Not available", "<p>This account cannot sign in.</p>", 403);
  const admin = isAdminEmail(env, user.email);
  await env.DB.prepare(`UPDATE users SET status = 'active', last_login_at = ?, role = ?, applicant_status = ?, trust = ? WHERE id = ?`)
    .bind(now(), admin ? "admin" : user.role, admin ? "approved" : user.applicant_status, admin ? "green" : user.trust, user.id).run();
  const session = randomToken(32);
  await env.DB.prepare("INSERT INTO sessions (hash, user_id, expires_at, created_at) VALUES (?,?,?,?)")
    .bind(await sha256hex(session), user.id, now() + SESSION_DAYS * DAY, now()).run();
  await logEvent(env, "session", { userId: user.id, ip: await ipHash(env, request) });
  return new Response(null, { status: 303, headers: { Location: "/account.html", "Set-Cookie": sessionCookie(session, SESSION_DAYS * DAY), "Cache-Control": "no-store" } });
}

export async function logout(request, env) {
  if (!sameOrigin(request)) return fail(403, "Bad origin.");
  const raw = getCookie(request, SESSION_COOKIE);
  if (raw) await env.DB.prepare("DELETE FROM sessions WHERE hash = ?").bind(await sha256hex(raw)).run();
  return json({ ok: true }, 200, { "Set-Cookie": sessionCookie("", 0) });
}

export function requireUser(user) {
  if (!user) throw new HttpError(401, "Sign in first.");
  if (user.status !== "active") throw new HttpError(403, "Verify your email first.");
  return user;
}
export function requireStaff(user, adminOnly = false) {
  requireUser(user);
  if (!(user.role === "admin" || (!adminOnly && user.role === "moderator"))) throw new HttpError(403, "Not allowed.");
  return user;
}
