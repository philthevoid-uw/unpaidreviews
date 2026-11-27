// Image and video uploads. Everything is quarantined until a person approves it,
// except uploads from reviewers a person has marked "green" (still subject to the automated checks).
import { json, fail, newId, now, sameOrigin, readJson, logEvent, ipHash, limited, DAY, HttpError } from "./util.js";

const MAX_IMAGE = 10 * 1024 * 1024;       // bytes
const MAX_VIDEO_SECONDS = 180;
const IMAGES_PER_DAY = 20, VIDEOS_PER_DAY = 3, PENDING_CAP = 40;

// Identify by magic bytes, never by the filename or the declared Content-Type.
export function sniffImage(b) {
  if (b.length > 12 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "image/jpeg";
  if (b.length > 8 && b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47 && b[4] === 0x0d && b[5] === 0x0a && b[6] === 0x1a && b[7] === 0x0a) return "image/png";
  if (b.length > 12 && String.fromCharCode(...b.slice(0, 4)) === "RIFF" && String.fromCharCode(...b.slice(8, 12)) === "WEBP") return "image/webp";
  return null;
}

function checkAllowed(user) {
  if (user.applicant_status !== "approved") throw new HttpError(403, "Uploads open once your reviewer application is approved.");
}

async function quota(env, user, kind) {
  const day = await env.DB.prepare("SELECT COUNT(*) c FROM uploads WHERE user_id=? AND kind=? AND created_at>?")
    .bind(user.id, kind, now() - DAY).first();
  if (day.c >= (kind === "image" ? IMAGES_PER_DAY : VIDEOS_PER_DAY)) throw new HttpError(429, "Daily upload limit reached. Try again tomorrow.");
  const pend = await env.DB.prepare("SELECT COUNT(*) c FROM uploads WHERE user_id=? AND status='pending_review'").bind(user.id).first();
  if (pend.c >= PENDING_CAP) throw new HttpError(429, "You have a lot waiting for review already. Please wait for those to be reviewed.");
}

// Green reviewers publish automatically once the automated checks below have passed; everyone else waits for a person.
const initialStatus = (user) => (user.trust === "green" ? "approved" : "pending_review");

export async function uploadImage(request, env, user) {
  if (!sameOrigin(request)) return fail(403, "Bad origin.");
  checkAllowed(user);
  if (!env.MEDIA) return fail(503, "Uploads are not open yet.");
  await quota(env, user, "image");
  const declared = Number(request.headers.get("Content-Length") || 0);
  if (declared > MAX_IMAGE) return fail(413, "Images can be up to 10 MB.");
  const buf = new Uint8Array(await request.arrayBuffer());
  if (buf.length === 0 || buf.length > MAX_IMAGE) return fail(413, "Images can be up to 10 MB.");
  const type = sniffImage(buf);
  if (!type) return fail(415, "Only JPEG, PNG or WebP images are accepted.");

  // Re-encode: the stored file is a fresh WebP made by our pipeline, so any hidden payload or
  // metadata (location, camera serial, scripts appended to the file) is discarded.
  let out, info;
  try {
    if (env.IMAGES) {
      info = await env.IMAGES.input(new Blob([buf]).stream()).info();
      if (!info || info.width * info.height > 60_000_000) return fail(415, "That image is too large in dimensions.");
      const res = await env.IMAGES.input(new Blob([buf]).stream())
        .transform({ width: 2400, height: 2400, fit: "scale-down" })
        .output({ format: "image/webp", quality: 85 });
      out = new Uint8Array(await res.response().arrayBuffer());
    } else if (env.DEV_MODE === "1") {
      out = buf; info = { width: 0, height: 0 };
    } else {
      return fail(503, "Uploads are not open yet.");
    }
  } catch {
    return fail(415, "We couldn't process that image. Try a different file.");
  }
  if (sniffImage(out) !== "image/webp" && env.DEV_MODE !== "1") return fail(415, "We couldn't process that image.");

  const id = newId(), key = `img/${user.id}/${id}.webp`;
  await env.MEDIA.put(key, out, { httpMetadata: { contentType: "image/webp", cacheControl: "public, max-age=31536000, immutable" } });
  const status = initialStatus(user);
  await env.DB.prepare(`INSERT INTO uploads (id,user_id,kind,r2_key,content_type,bytes,width,height,status,published_by,created_at,decided_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`)
    .bind(id, user.id, "image", key, "image/webp", out.length, info.width || null, info.height || null, status,
      status === "approved" ? "auto" : null, now(), status === "approved" ? now() : null).run();
  await logEvent(env, "upload_image", { userId: user.id, ip: await ipHash(env, request), detail: id });
  return json({ ok: true, id, status });
}

// Videos go straight from the browser to Cloudflare Stream through a one-time upload URL.
export async function videoUploadUrl(request, env, user) {
  if (!sameOrigin(request)) return fail(403, "Bad origin.");
  checkAllowed(user);
  if (!env.STREAM_ACCOUNT_ID || !env.STREAM_TOKEN) return fail(503, "Video uploads are not open yet.");
  await quota(env, user, "video");
  const r = await fetch(`https://api.cloudflare.com/client/v4/accounts/${env.STREAM_ACCOUNT_ID}/stream/direct_upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.STREAM_TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ maxDurationSeconds: MAX_VIDEO_SECONDS, requireSignedURLs: true,
      expiry: new Date(Date.now() + 30 * 60 * 1000).toISOString(), meta: { user: user.id } }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.result) return fail(502, "Video upload isn't available right now.");
  const id = newId();
  await env.DB.prepare(`INSERT INTO uploads (id,user_id,kind,stream_uid,status,created_at) VALUES (?,?,?,?,?,?)`)
    .bind(id, user.id, "video", j.result.uid, "uploading", now()).run();
  await logEvent(env, "upload_video_url", { userId: user.id, ip: await ipHash(env, request), detail: id });
  return json({ ok: true, id, uploadURL: j.result.uploadURL });
}

export async function videoComplete(request, env, user) {
  if (!sameOrigin(request)) return fail(403, "Bad origin.");
  checkAllowed(user);
  const b = await readJson(request);
  const up = await env.DB.prepare("SELECT * FROM uploads WHERE id=? AND user_id=? AND kind='video'").bind(String(b.id || ""), user.id).first();
  if (!up) return fail(404, "Not found.");
  if (up.status !== "uploading") return json({ ok: true, status: up.status });
  const r = await fetch(`https://api.cloudflare.com/client/v4/accounts/${env.STREAM_ACCOUNT_ID}/stream/${up.stream_uid}`,
    { headers: { Authorization: `Bearer ${env.STREAM_TOKEN}` } });
  const j = await r.json().catch(() => ({}));
  const v = j.result;
  if (!v) return fail(409, "We haven't received the video yet. Wait a moment and try again.");
  if (v.status && v.status.state === "error") {
    await env.DB.prepare("UPDATE uploads SET status='rejected', note='processing failed', decided_at=? WHERE id=?").bind(now(), up.id).run();
    return fail(415, "That video couldn't be processed.");
  }
  if (!v.readyToStream) return json({ ok: true, status: "processing" });
  if (v.duration > MAX_VIDEO_SECONDS) {
    await env.DB.prepare("UPDATE uploads SET status='rejected', note='too long', decided_at=? WHERE id=?").bind(now(), up.id).run();
    await fetch(`https://api.cloudflare.com/client/v4/accounts/${env.STREAM_ACCOUNT_ID}/stream/${up.stream_uid}`, { method: "DELETE", headers: { Authorization: `Bearer ${env.STREAM_TOKEN}` } });
    return fail(413, "Videos can be up to 3 minutes.");
  }
  const status = initialStatus(user);
  await env.DB.prepare("UPDATE uploads SET status=?, duration=?, bytes=?, published_by=?, decided_at=? WHERE id=?")
    .bind(status, v.duration || null, v.size || null, status === "approved" ? "auto" : null, status === "approved" ? now() : null, up.id).run();
  return json({ ok: true, status });
}

export async function myUploads(env, user) {
  const { results } = await env.DB.prepare("SELECT id,kind,status,note,created_at FROM uploads WHERE user_id=? ORDER BY created_at DESC LIMIT 100").bind(user.id).all();
  return json({ ok: true, uploads: results });
}

// Public/served media. Only approved items are public; owners and staff may see their own/any pending item.
export async function serveMedia(request, env, user, id) {
  const up = await env.DB.prepare("SELECT * FROM uploads WHERE id=? AND kind='image'").bind(id).first();
  if (!up || !env.MEDIA) return new Response("Not found", { status: 404 });
  const staff = user && (user.role === "admin" || user.role === "moderator");
  const visible = up.status === "approved" || (user && (user.id === up.user_id || staff));
  if (!visible) return new Response("Not found", { status: 404 });
  const obj = await env.MEDIA.get(up.r2_key);
  if (!obj) return new Response("Not found", { status: 404 });
  return new Response(obj.body, { headers: {
    "Content-Type": "image/webp", "X-Content-Type-Options": "nosniff",
    "Content-Disposition": "inline",
    "Cache-Control": up.status === "approved" ? "public, max-age=3600" : "private, no-store",
    "Content-Security-Policy": "default-src 'none'; sandbox" } });
}

// ---- moderation (moderator/admin only) ----
export async function queue(env) {
  const apps = await env.DB.prepare(`SELECT a.id, a.user_id, u.handle, u.email, a.country, a.categories, a.sample, a.links, a.conflicts, a.attestations, a.created_at
    FROM applications a JOIN users u ON u.id=a.user_id WHERE a.status='submitted' ORDER BY a.created_at LIMIT 50`).all();
  const ups = await env.DB.prepare(`SELECT p.id, p.kind, p.user_id, u.handle, u.trust, p.stream_uid, p.created_at
    FROM uploads p JOIN users u ON u.id=p.user_id WHERE p.status='pending_review' ORDER BY p.created_at LIMIT 100`).all();
  return json({ ok: true, applications: apps.results, uploads: ups.results });
}

// action: approve_green | approve_yellow | reject
export async function decideUpload(request, env, staff, id) {
  if (!sameOrigin(request)) return fail(403, "Bad origin.");
  const b = await readJson(request);
  const action = String(b.action || ""), note = String(b.note || "").slice(0, 500);
  const up = await env.DB.prepare("SELECT * FROM uploads WHERE id=?").bind(id).first();
  if (!up) return fail(404, "Not found.");
  if (!["approve_green", "approve_yellow", "reject"].includes(action)) return fail(400, "Unknown action.");
  const approve = action !== "reject";
  await env.DB.prepare("UPDATE uploads SET status=?, published_by=?, note=?, decided_at=? WHERE id=?")
    .bind(approve ? "approved" : "rejected", staff.id, note || null, now(), id).run();
  // A person's decision sets how this reviewer's future uploads are handled.
  if (approve) await env.DB.prepare("UPDATE users SET trust=? WHERE id=?").bind(action === "approve_green" ? "green" : "yellow", up.user_id).run();
  await logEvent(env, "upload_decision", { userId: staff.id, detail: `${id}:${action}` });
  return json({ ok: true });
}

export async function decideApplication(request, env, staff, id) {
  if (!sameOrigin(request)) return fail(403, "Bad origin.");
  const b = await readJson(request);
  const approve = b.action === "approve";
  if (!approve && b.action !== "decline") return fail(400, "Unknown action.");
  const app = await env.DB.prepare("SELECT * FROM applications WHERE id=?").bind(id).first();
  if (!app) return fail(404, "Not found.");
  await env.DB.batch([
    env.DB.prepare("UPDATE applications SET status=?, note=?, decided_at=?, decided_by=? WHERE id=?")
      .bind(approve ? "approved" : "declined", String(b.note || "").slice(0, 500) || null, now(), staff.id, id),
    env.DB.prepare("UPDATE users SET applicant_status=? WHERE id=?").bind(approve ? "approved" : "declined", app.user_id),
  ]);
  await logEvent(env, "application_decision", { userId: staff.id, detail: `${id}:${b.action}` });
  return json({ ok: true });
}
