// Sign-up, sign-in, application, uploads and moderation. All user-supplied text is inserted with textContent.
(function () {
  "use strict";
  var $ = function (s) { return document.querySelector(s); };
  var cfg = { turnstileSiteKey: null, dev: false }, tsToken = "";

  function say(el, text, err) { if (!el) return; el.textContent = text; el.className = err ? "err" : ""; }
  function api(path, opts) {
    opts = opts || {};
    var h = opts.headers || {};
    if (opts.json) { h["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
    return fetch(path, { method: opts.method || (opts.body ? "POST" : "GET"), headers: h, body: opts.body, credentials: "same-origin" })
      .then(function (r) { return r.json().catch(function () { return { ok: false, error: "Unexpected response." }; }).then(function (j) { j.status = r.status; return j; }); });
  }
  function el(tag, text, cls) { var e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; }

  function loadTurnstile() {
    var box = $("#turnstile");
    if (!box) return Promise.resolve();
    return api("/api/config").then(function (c) {
      cfg = c;
      if (!c.turnstileSiteKey) return;
      return new Promise(function (resolve) {
        var s = document.createElement("script");
        s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
        s.onload = function () {
          window.turnstile.render(box, { sitekey: c.turnstileSiteKey, callback: function (t) { tsToken = t; } });
          resolve();
        };
        document.head.appendChild(s);
      });
    });
  }

  function emailForm(formSel, path, build) {
    var f = $(formSel); if (!f) return;
    loadTurnstile();
    f.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var msg = $("#msg");
      if (!f.checkValidity()) { f.reportValidity(); return; }
      var btn = f.querySelector("button[type=submit]"); btn.disabled = true;
      api(path, { json: build(f) }).then(function (j) {
        say(msg, j.ok ? j.message : (j.error || "Something went wrong."), !j.ok);
        if (!j.ok) { btn.disabled = false; if (window.turnstile) window.turnstile.reset(); }
      });
    });
  }
  emailForm("#signup", "/api/auth/signup", function (f) {
    return { email: f.email.value, handle: f.handle.value, turnstile: tsToken,
      terms: { malicious: f.malicious.checked, responsible: f.responsible.checked, rights: f.rights.checked } };
  });
  emailForm("#signin", "/api/auth/login", function (f) { return { email: f.email.value, turnstile: tsToken }; });

  // ---- account page ----
  var who = $("#who");
  if (who) {
    api("/api/me").then(function (j) {
      if (!j.ok) { who.textContent = ""; var a = el("a", "Sign in"); a.href = "/signin.html"; who.appendChild(a); who.appendChild(document.createTextNode(" or ")); var b = el("a", "create an account"); b.href = "/signup.html"; who.appendChild(b); return; }
      var u = j.user;
      who.textContent = "Signed in as " + u.handle + ".";
      $("#logout").hidden = false;
      if (u.applicant_status === "none") $("#apply").hidden = false;
      if (u.applicant_status === "submitted") $("#pending").hidden = false;
      if (u.applicant_status === "declined") $("#declined").hidden = false;
      if (u.applicant_status === "approved") { $("#uploads").hidden = false; loadUploads(); }
      if (u.role === "admin" || u.role === "moderator") { $("#admin").hidden = false; loadQueue(); }
    });
    $("#logout").addEventListener("click", function () { api("/api/auth/logout", { method: "POST", json: {} }).then(function () { location.href = "/"; }); });
  }

  var af = $("#appform");
  if (af) af.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (!af.checkValidity()) { af.reportValidity(); return; }
    var cats = [].slice.call(af.querySelectorAll("input[name=cat]:checked")).map(function (c) { return c.value; });
    var att = {}; ["truthful", "own_experience", "no_ai", "no_payment", "disclose_changes", "removal"].forEach(function (k) { att[k] = af[k].checked; });
    var c = {}; ["works_in_category", "paid_for_reviews", "affiliate_programs", "other_relationships"].forEach(function (k) { c[k] = af[k].value; });
    api("/api/application", { json: { country: af.country.value, categories: cats, sample: af.sample.value, links: af.links.value, conflicts: c, attestations: att } })
      .then(function (j) { if (j.ok) location.reload(); else say($("#msg"), j.error, true); });
  });

  // ---- uploads ----
  function loadUploads() {
    api("/api/uploads").then(function (j) {
      var ul = $("#uplist"); ul.textContent = "";
      (j.uploads || []).forEach(function (u) {
        ul.appendChild(el("li", u.kind + ", " + new Date(u.created_at * 1000).toLocaleDateString() + ": " + u.status.replace("_", " ") + (u.note ? " (" + u.note + ")" : "")));
      });
      if (!(j.uploads || []).length) ul.appendChild(el("li", "Nothing uploaded yet."));
    });
  }
  var ib = $("#imgbtn");
  if (ib) ib.addEventListener("click", function () {
    var f = $("#imgfile").files[0], m = $("#upmsg");
    if (!f) return say(m, "Choose an image first.", true);
    if (f.size > 10 * 1024 * 1024) return say(m, "Images can be up to 10 MB.", true);
    say(m, "Uploading…");
    fetch("/api/uploads/image", { method: "POST", body: f, credentials: "same-origin", headers: { "Content-Type": "application/octet-stream" } })
      .then(function (r) { return r.json(); })
      .then(function (j) { say(m, j.ok ? "Uploaded. Status: " + j.status.replace("_", " ") + "." : j.error, !j.ok); $("#imgfile").value = ""; loadUploads(); });
  });
  var vb = $("#vidbtn");
  if (vb) vb.addEventListener("click", function () {
    var f = $("#vidfile").files[0], m = $("#upmsg");
    if (!f) return say(m, "Choose a video first.", true);
    if (f.size > 200 * 1024 * 1024) return say(m, "Videos can be up to 200 MB.", true);
    say(m, "Preparing upload…");
    api("/api/uploads/video-url", { json: {} }).then(function (j) {
      if (!j.ok) return say(m, j.error, true);
      var fd = new FormData(); fd.append("file", f);
      say(m, "Uploading video…");
      return fetch(j.uploadURL, { method: "POST", body: fd }).then(function (r) {
        if (!r.ok) return say(m, "The video upload failed.", true);
        var tries = 0;
        (function poll() {
          api("/api/uploads/video-complete", { json: { id: j.id } }).then(function (c) {
            if (c.ok && c.status !== "processing" && c.status !== "uploading") { say(m, "Uploaded. Status: " + c.status.replace("_", " ") + "."); loadUploads(); }
            else if (!c.ok && c.status !== 409) { say(m, c.error, true); loadUploads(); }
            else if (++tries < 40) setTimeout(poll, 3000);
            else say(m, "Still processing. Check back shortly.");
          });
        })();
      });
    });
  });

  // ---- moderation ----
  function actions(item, path, defs) {
    var row = el("p"), note = el("input"); note.type = "text"; note.placeholder = "Note (optional)"; note.maxLength = 500;
    row.appendChild(note);
    defs.forEach(function (d) {
      var b = el("button", d[1], "btn" + (d[2] ? " ghost" : "")); b.type = "button";
      b.addEventListener("click", function () { api(path, { json: { action: d[0], note: note.value } }).then(function (j) { if (j.ok) item.remove(); else alert(j.error); }); });
      row.appendChild(document.createTextNode(" ")); row.appendChild(b);
    });
    item.appendChild(row);
  }
  function loadQueue() {
    api("/api/admin/queue").then(function (j) {
      var q = $("#queue"); q.textContent = "";
      (j.applications || []).forEach(function (a) {
        var it = el("div", null, "item");
        it.appendChild(el("h3", "Application: " + a.handle + " (" + a.email + "), " + a.country));
        it.appendChild(el("p", "Categories: " + a.categories));
        it.appendChild(el("p", "Conflicts: " + a.conflicts));
        it.appendChild(el("p", "Links: " + (a.links || "none")));
        it.appendChild(el("pre", a.sample)); it.lastChild.style.whiteSpace = "pre-wrap";
        actions(it, "/api/admin/applications/" + a.id, [["approve", "Approve"], ["decline", "Decline", true]]);
        q.appendChild(it);
      });
      (j.uploads || []).forEach(function (u) {
        var it = el("div", null, "item");
        it.appendChild(el("h3", u.kind + " from " + u.handle + " (trust: " + u.trust + ")"));
        if (u.kind === "image") { var im = el("img"); im.src = "/media/" + u.id + ".webp"; im.alt = "Pending upload"; it.appendChild(im); }
        else it.appendChild(el("p", "Video " + u.stream_uid + ": preview it in the Cloudflare Stream dashboard before deciding."));
        actions(it, "/api/admin/uploads/" + u.id, [["approve_green", "Approve + green (auto-publish future)"], ["approve_yellow", "Approve + yellow (review future)"], ["reject", "Reject", true]]);
        q.appendChild(it);
      });
      if (!q.children.length) q.appendChild(el("p", "Nothing waiting."));
    });
  }
})();
