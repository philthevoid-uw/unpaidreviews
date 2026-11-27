// Router for /api/*, /media/* and the sign-in landing. Called from src/worker.js on the main host only.
import { json, fail, HttpError } from "./util.js";
import { currentUser, publicUser, signup, login, verify, verifyPage, logout, requireUser, requireStaff } from "./auth.js";
import { submitApplication } from "./apply.js";
import { uploadImage, videoUploadUrl, videoComplete, myUploads, serveMedia, queue, decideUpload, decideApplication } from "./upload.js";

export const isApiPath = (p) => p.startsWith("/api/") || p.startsWith("/media/");

export async function handleApi(request, env) {
  if (!env.DB) return fail(503, "Accounts are not open yet.");
  try {
    return await dispatch(request, env);
  } catch (err) {
    if (err instanceof HttpError) return fail(err.status, err.message);
    console.error("api error", err && err.message);
    return fail(500, "Something went wrong.");
  }
}

async function dispatch(request, env) {
  const url = new URL(request.url), p = url.pathname, m = request.method;
  {
    if (p.startsWith("/media/") && m === "GET") return serveMedia(request, env, await currentUser(env, request), p.slice(7).replace(/\.webp$/, ""));
    if (p === "/api/auth/verify") return m === "GET" ? verifyPage(url) : m === "POST" ? verify(request, env) : fail(405, "Method not allowed.");
    if (p === "/api/config" && m === "GET") return json({ ok: true, turnstileSiteKey: env.TURNSTILE_SITE_KEY || null, dev: env.DEV_MODE === "1" });
    if (m === "POST" && p === "/api/auth/signup") return signup(request, env);
    if (m === "POST" && p === "/api/auth/login") return login(request, env);
    if (m === "POST" && p === "/api/auth/logout") return logout(request, env);

    const user = await currentUser(env, request);
    if (p === "/api/me" && m === "GET") return user ? json({ ok: true, user: publicUser(user) }) : fail(401, "Not signed in.");
    if (p === "/api/application" && m === "POST") return submitApplication(request, env, requireUser(user));
    if (p === "/api/uploads" && m === "GET") return myUploads(env, requireUser(user));
    if (p === "/api/uploads/image" && m === "POST") return uploadImage(request, env, requireUser(user));
    if (p === "/api/uploads/video-url" && m === "POST") return videoUploadUrl(request, env, requireUser(user));
    if (p === "/api/uploads/video-complete" && m === "POST") return videoComplete(request, env, requireUser(user));

    if (p === "/api/admin/queue" && m === "GET") { requireStaff(user); return queue(env); }
    let mm;
    if ((mm = p.match(/^\/api\/admin\/uploads\/([\w-]+)$/)) && m === "POST") return decideUpload(request, env, requireStaff(user), mm[1]);
    if ((mm = p.match(/^\/api\/admin\/applications\/([\w-]+)$/)) && m === "POST") return decideApplication(request, env, requireStaff(user), mm[1]);
    return fail(404, "Not found.");
  }
}
