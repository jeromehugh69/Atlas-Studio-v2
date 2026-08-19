ALTER TABLE tasks ADD COLUMN IF NOT EXISTS grounding_status text NOT NULL DEFAULT 'pending';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS grounding_issues jsonb NOT NULL DEFAULT '[]';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS evidence_refs jsonb NOT NULL DEFAULT '[]';

CREATE INDEX IF NOT EXISTS tasks_grounding_status_idx ON tasks (grounding_status, updated_at DESC);
