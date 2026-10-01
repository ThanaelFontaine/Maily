-- Account provider: 'gmail' (Gmail API) or 'imap' (Orange, etc.).
ALTER TABLE accounts ADD COLUMN provider TEXT NOT NULL DEFAULT 'gmail';
