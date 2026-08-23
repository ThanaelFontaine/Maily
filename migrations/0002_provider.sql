-- Fournisseur du compte : 'gmail' (API Gmail) ou 'imap' (Orange, etc.).
ALTER TABLE accounts ADD COLUMN provider TEXT NOT NULL DEFAULT 'gmail';
