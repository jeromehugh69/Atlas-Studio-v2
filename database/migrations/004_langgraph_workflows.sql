CREATE TABLE IF NOT EXISTS workflow_definitions (
  id text NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  name text NOT NULL,
  owner_agent text NOT NULL,
  definition jsonb NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id, version)
);

CREATE TABLE IF NOT EXISTS workflow_runs (
  id uuid PRIMARY KEY,
  workspace_id uuid REFERENCES workspaces(id) ON DELETE CASCADE,
  task_id uuid REFERENCES tasks(id) ON DELETE SET NULL,
  workflow_id text NOT NULL,
  workflow_version integer NOT NULL,
  status text NOT NULL,
  risk_tier smallint NOT NULL DEFAULT 0 CHECK (risk_tier BETWEEN 0 AND 3),
  requested_by text NOT NULL DEFAULT 'local-user',
  state jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (workflow_id, workflow_version) REFERENCES workflow_definitions(id, version)
);

CREATE TABLE IF NOT EXISTS workflow_steps (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
  node text NOT NULL,
  agent_id uuid REFERENCES agents(id) ON DELETE SET NULL,
  attempt integer NOT NULL DEFAULT 1,
  status text NOT NULL,
  input jsonb NOT NULL DEFAULT '{}',
  output jsonb NOT NULL DEFAULT '{}',
  started_at timestamptz,
  completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS workflow_approvals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
  action_hash text NOT NULL,
  action jsonb NOT NULL,
  decision text CHECK (decision IN ('approved','edited','rejected','expired')),
  decided_by text,
  reason text,
  requested_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz,
  expires_at timestamptz
);

CREATE TABLE IF NOT EXISTS workflow_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
  sequence bigint NOT NULL,
  event_type text NOT NULL,
  agent_id uuid REFERENCES agents(id) ON DELETE SET NULL,
  payload jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, sequence)
);

CREATE INDEX IF NOT EXISTS workflow_runs_updated_idx ON workflow_runs (updated_at DESC);
CREATE INDEX IF NOT EXISTS workflow_events_run_sequence_idx ON workflow_events (run_id, sequence);
CREATE INDEX IF NOT EXISTS workflow_approvals_pending_idx ON workflow_approvals (run_id) WHERE decision IS NULL;

