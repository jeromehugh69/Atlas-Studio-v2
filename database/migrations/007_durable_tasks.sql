ALTER TABLE tasks ADD COLUMN IF NOT EXISTS user_authorized boolean NOT NULL DEFAULT false;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS completed_at timestamptz;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS duration_ms integer CHECK (duration_ms >= 0);
CREATE INDEX IF NOT EXISTS tasks_recovery_idx ON tasks (status, priority, created_at);
