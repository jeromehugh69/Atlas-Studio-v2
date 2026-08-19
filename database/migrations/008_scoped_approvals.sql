ALTER TABLE external_action_approvals DROP CONSTRAINT IF EXISTS external_action_approvals_action_check;
ALTER TABLE external_action_approvals ADD COLUMN IF NOT EXISTS target text NOT NULL DEFAULT '';
ALTER TABLE external_action_approvals ADD COLUMN IF NOT EXISTS actor text NOT NULL DEFAULT 'Atlas';
ALTER TABLE external_action_approvals ADD COLUMN IF NOT EXISTS payload jsonb NOT NULL DEFAULT '{}';
ALTER TABLE external_action_approvals ADD COLUMN IF NOT EXISTS action_hash text NOT NULL DEFAULT '';
