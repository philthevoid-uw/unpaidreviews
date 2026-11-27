// Sends the sign-in emails. Uses Cloudflare Email Sending when the EMAIL binding exists,
// otherwise Resend if RESEND_API_KEY is set. In DEV_MODE the message is only logged.
const FROM = "Unpaid Reviews <no-reply@unpaidreviews.com>";

export async function sendMail(env, { to, subject, text }) {
  if (env.DEV_MODE === "1") { console.log(`[mail to ${to}] ${subject}\n${text}`); return true; }
  try {
    if (env.EMAIL) {
      await env.EMAIL.send({ from: "no-reply@unpaidreviews.com", to, subject, text });
      return true;
    }
    if (env.RESEND_API_KEY) {
      const r = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({ from: FROM, to, subject, text }),
      });
      return r.ok;
    }
  } catch (err) { console.error("mail failed", err && err.message); }
  return false;
}

export const mailConfigured = (env) => env.DEV_MODE === "1" || !!env.EMAIL || !!env.RESEND_API_KEY;
