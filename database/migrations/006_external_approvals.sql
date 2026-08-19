CREATE TABLE IF NOT EXISTS external_action_approvals (
  id uuid PRIMARY KEY,
  action text NOT NULL CHECK (action IN ('internet_search','docker_action')),
  purpose text NOT NULL,
  query text NOT NULL DEFAULT '',
  allowed_domains jsonb NOT NULL DEFAULT '[]',
  status text NOT NULL CHECK (status IN ('pending','approved','rejected','used','expired')),
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  decided_at timestamptz,
  used_at timestamptz
);
CREATE INDEX IF NOT EXISTS external_action_approvals_status_idx ON external_action_approvals (status, expires_at);
