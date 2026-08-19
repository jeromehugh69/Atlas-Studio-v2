-- Add user-editable Forge recommendation fields without removing prior plans.
ALTER TABLE plans ADD COLUMN IF NOT EXISTS recommendation text NOT NULL DEFAULT 'Forge recommends a scoped, reviewable change in an isolated workspace.';
ALTER TABLE plans ADD COLUMN IF NOT EXISTS impact text NOT NULL DEFAULT 'Review required';
ALTER TABLE plans ADD COLUMN IF NOT EXISTS test_plan text NOT NULL DEFAULT 'Run repository tests in Test';
ALTER TABLE plans ADD COLUMN IF NOT EXISTS rollback_plan text NOT NULL DEFAULT 'Retain the reviewed diff and prior file hashes';
ALTER TABLE plans ADD COLUMN IF NOT EXISTS proposed_files jsonb NOT NULL DEFAULT '[]';

COMMENT ON COLUMN plans.recommendation IS 'Forge recommendation reviewed and editable by the user before authorization.';
COMMENT ON COLUMN plans.proposed_files IS 'Evidence-based likely files; empty means unconfirmed rather than inferred.';
