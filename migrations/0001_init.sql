CREATE TABLE accounts (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  display_name TEXT,
  color TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  last_sync_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE threads (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  gmail_thread_id TEXT NOT NULL,
  subject TEXT,
  last_message_at TEXT,
  message_count INTEGER NOT NULL DEFAULT 0,
  UNIQUE(account_id, gmail_thread_id)
);

CREATE TABLE messages (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  gmail_id TEXT NOT NULL,
  thread_id TEXT,
  rfc822_message_id TEXT,
  direction TEXT NOT NULL DEFAULT 'in',
  addr_from TEXT,
  addr_to TEXT,
  addr_cc TEXT,
  addr_bcc TEXT,
  subject TEXT,
  snippet TEXT,
  body_text TEXT,
  body_html TEXT,
  internal_date INTEGER,
  label_ids TEXT,
  is_unread INTEGER NOT NULL DEFAULT 0,
  is_starred INTEGER NOT NULL DEFAULT 0,
  has_attachments INTEGER NOT NULL DEFAULT 0,
  is_trashed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(account_id, gmail_id)
);
CREATE INDEX idx_messages_account_thread ON messages(account_id, thread_id);
CREATE INDEX idx_messages_internal_date ON messages(internal_date DESC);

CREATE TABLE labels (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  gmail_label_id TEXT NOT NULL,
  name TEXT,
  type TEXT,
  UNIQUE(account_id, gmail_label_id)
);

CREATE TABLE attachments (
  id INTEGER PRIMARY KEY,
  owner_kind TEXT NOT NULL,
  owner_id INTEGER NOT NULL,
  content_id TEXT,
  filename TEXT,
  stored_name TEXT,
  mime_type TEXT,
  size INTEGER,
  gmail_attachment_id TEXT,
  local_path TEXT
);
CREATE INDEX idx_attachments_owner ON attachments(owner_kind, owner_id);

CREATE TABLE outbox (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  addr_to TEXT NOT NULL,
  addr_cc TEXT,
  addr_bcc TEXT,
  subject TEXT,
  body_text TEXT,
  body_html TEXT,
  in_reply_to TEXT,
  thread_id TEXT,
  idempotency_key TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0,
  gmail_id TEXT,
  error TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  sent_at TEXT
);

CREATE TABLE sync_state (
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value TEXT,
  PRIMARY KEY (account_id, key)
);

CREATE VIRTUAL TABLE messages_fts USING fts5(
  subject, body_text, addr_from,
  content='messages', content_rowid='id'
);

CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, subject, body_text, addr_from)
  VALUES (new.id, new.subject, new.body_text, new.addr_from);
END;

CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, subject, body_text, addr_from)
  VALUES ('delete', old.id, old.subject, old.body_text, old.addr_from);
END;

CREATE TRIGGER messages_au AFTER UPDATE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, subject, body_text, addr_from)
  VALUES ('delete', old.id, old.subject, old.body_text, old.addr_from);
  INSERT INTO messages_fts(rowid, subject, body_text, addr_from)
  VALUES (new.id, new.subject, new.body_text, new.addr_from);
END;

CREATE VIEW v1_accounts AS
  SELECT id, email, display_name, status, last_sync_at FROM accounts;

CREATE VIEW v1_messages AS
  SELECT id, account_id, gmail_id, thread_id, direction, addr_from, addr_to,
         addr_cc, subject, snippet, body_text, internal_date, is_unread,
         is_starred, has_attachments, is_trashed
  FROM messages WHERE is_trashed = 0;

CREATE VIEW v1_threads AS
  SELECT id, account_id, gmail_thread_id, subject, last_message_at, message_count
  FROM threads;
