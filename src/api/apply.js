// Step 2: the reviewer application (conflict-of-interest answers and attestations).
import { json, fail, readJson, newId, now, sameOrigin, MAX_TEXT, logEvent, ipHash } from "./util.js";

export const STANDARDS_VERSION = "reviewer-standards-2026-11-v1";
const CATEGORIES = ["products", "travel", "restaurants", "wine", "other"];
const ATTEST = ["truthful", "own_experience", "no_ai", "no_payment", "disclose_changes", "removal"];

export async function submitApplication(request, env, user) {
  if (!sameOrigin(request)) return fail(403, "Bad origin.");
  if (user.applicant_status !== "none") return fail(409, "You already have an application on file.");
  const b = await readJson(request);
  const country = MAX_TEXT(b.country, 80);
  const categories = (Array.isArray(b.categories) ? b.categories : []).filter((c) => CATEGORIES.includes(c));
  const sample = MAX_TEXT(b.sample, 2000);
  const links = MAX_TEXT(b.links, 1000);
  const c = b.conflicts || {};
  const conflicts = {
    works_in_category: MAX_TEXT(c.works_in_category, 600),
    paid_for_reviews: MAX_TEXT(c.paid_for_reviews, 600),
    affiliate_programs: MAX_TEXT(c.affiliate_programs, 600),
    other_relationships: MAX_TEXT(c.other_relationships, 600),
  };
  const a = b.attestations || {};
  if (!country || !categories.length) return fail(400, "Choose your country and at least one category.");
  if (sample.length < 300) return fail(400, "The writing sample should be at least 300 characters.");
  for (const k of Object.keys(conflicts)) if (!conflicts[k]) return fail(400, "Answer every conflict-of-interest question. Write \"None\" if it doesn't apply.");
  if (!ATTEST.every((k) => a[k] === true)) return fail(400, "Please confirm every statement.");
  const id = newId();
  await env.DB.batch([
    env.DB.prepare(`INSERT INTO applications (id,user_id,country,categories,sample,links,conflicts,attestations,created_at) VALUES (?,?,?,?,?,?,?,?,?)`)
      .bind(id, user.id, country, JSON.stringify(categories), sample, links, JSON.stringify(conflicts),
        JSON.stringify({ version: STANDARDS_VERSION, ticked: ATTEST, at: now() }), now()),
    env.DB.prepare("UPDATE users SET applicant_status = 'submitted' WHERE id = ?").bind(user.id),
  ]);
  await logEvent(env, "application", { userId: user.id, ip: await ipHash(env, request) });
  return json({ ok: true });
}
