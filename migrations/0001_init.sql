-- Reviewer accounts, applications, uploads and moderation. Apply with:
--   npx wrangler d1 migrations apply unpaidreviews --remote
-- (or paste into the D1 console in the Cloudflare dashboard).

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  handle TEXT NOT NULL UNIQUE COLLATE NOCASE,
  role TEXT NOT NULL DEFAULT 'reviewer',            -- reviewer | moderator | admin
  status TEXT NOT NULL DEFAULT 'unverified',        -- unverified | active | suspended
  applicant_status TEXT NOT NULL DEFAULT 'none',    -- none | submitted | approved | declined
  trust TEXT NOT NULL DEFAULT 'new',                -- new | yellow (manual review) | green (auto-publish after automated checks)
  terms_version TEXT NOT NULL,
  terms_accepted_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  last_login_at INTEGER
);

CREATE TABLE IF NOT EXISTS login_tokens (
  hash TEXT PRIMARY KEY,                            -- SHA-256 of the emailed token; the token itself is never stored
  user_id TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  used_at INTEGER,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  hash TEXT PRIMARY KEY,                            -- SHA-256 of the session cookie value
  user_id TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS applications (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL UNIQUE,
  country TEXT NOT NULL,
  categories TEXT NOT NULL,                         -- JSON array
  sample TEXT NOT NULL,
  links TEXT,
  conflicts TEXT NOT NULL,                          -- JSON: answers to the conflict-of-interest questions
  attestations TEXT NOT NULL,                       -- JSON: checkboxes ticked, with the version of the standards
  status TEXT NOT NULL DEFAULT 'submitted',         -- submitted | approved | declined
  note TEXT,
  created_at INTEGER NOT NULL,
  decided_at INTEGER,
  decided_by TEXT
);

CREATE TABLE IF NOT EXISTS uploads (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  kind TEXT NOT NULL,                               -- image | video
  r2_key TEXT,                                      -- images: object key in R2
  stream_uid TEXT,                                  -- videos: Cloudflare Stream id
  content_type TEXT,
  bytes INTEGER,
  width INTEGER,
  height INTEGER,
  duration REAL,
  status TEXT NOT NULL,                             -- uploading | pending_review | approved | rejected
  published_by TEXT,                                -- 'auto' | moderator user id
  note TEXT,
  created_at INTEGER NOT NULL,
  decided_at INTEGER
);
CREATE INDEX IF NOT EXISTS uploads_status ON uploads(status, created_at);
CREATE INDEX IF NOT EXISTS uploads_user ON uploads(user_id, created_at);

-- Audit trail and rate-limit counters. ip_hash is a salted hash, never a raw IP address.
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at INTEGER NOT NULL,
  kind TEXT NOT NULL,
  user_id TEXT,
  ip_hash TEXT,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS events_kind_ip ON events(kind, ip_hash, at);
CREATE INDEX IF NOT EXISTS events_kind_user ON events(kind, user_id, at);
