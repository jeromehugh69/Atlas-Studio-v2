ALTER TABLE tasks ADD COLUMN IF NOT EXISTS priority text NOT NULL DEFAULT 'normal'
  CHECK (priority IN ('critical','high','normal','low'));

CREATE TABLE IF NOT EXISTS plans (
  id uuid PRIMARY KEY,
  title text NOT NULL,
  request text NOT NULL,
  implementation_agent_id uuid NOT NULL REFERENCES agents(id),
  priority text NOT NULL CHECK (priority IN ('critical','high','normal','low')),
  steps jsonb NOT NULL DEFAULT '[]',
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz
);

CREATE TABLE IF NOT EXISTS development_lifecycles (
  id uuid PRIMARY KEY,
  plan_id uuid NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
  title text NOT NULL,
  stage text NOT NULL,
  status text NOT NULL,
  gates jsonb NOT NULL DEFAULT '{}',
  evidence jsonb NOT NULL DEFAULT '[]',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS library_changes (
  id uuid PRIMARY KEY,
  action text NOT NULL CHECK (action IN ('add','update','remove')),
  tool_id text NOT NULL,
  name text NOT NULL,
  description text NOT NULL,
  reason text NOT NULL,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

