-- Phase 6: email verification state on users
ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN email_verified_at DATETIME;

-- Existing accounts are treated as already verified.
UPDATE users SET email_verified = 1 WHERE email_verified = 0 OR email_verified IS NULL;
