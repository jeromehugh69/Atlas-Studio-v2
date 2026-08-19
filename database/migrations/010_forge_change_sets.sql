CREATE TABLE IF NOT EXISTS change_sets (
  id uuid PRIMARY KEY,
  task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  plan_id uuid NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
  workspace_id uuid NOT NULL REFERENCES plan_workspaces(id) ON DELETE CASCADE,
  title text NOT NULL,
  summary text NOT NULL,
  files jsonb NOT NULL DEFAULT '[]',
  combined_diff text NOT NULL DEFAULT '',
  status text NOT NULL CHECK (status IN ('pending_review','applied','tests_passed','committed','rejected','failed')),
  test_result jsonb NOT NULL DEFAULT '{}',
  branch text NOT NULL DEFAULT '',
  commit_hash text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS change_sets_plan_updated_idx ON change_sets (plan_id, updated_at DESC);

ALTER TABLE external_action_approvals DROP CONSTRAINT IF EXISTS external_action_approvals_action_check;
