ALTER TABLE tasks ADD COLUMN IF NOT EXISTS plan_id uuid REFERENCES plans(id) ON DELETE SET NULL;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS execution_workspace_id uuid;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS workspace_id uuid;
CREATE TABLE IF NOT EXISTS plan_workspaces (
  id uuid PRIMARY KEY,
  plan_id uuid NOT NULL UNIQUE REFERENCES plans(id) ON DELETE CASCADE,
  root text NOT NULL,
  status text NOT NULL CHECK (status IN ('creating','ready','blocked','archived')),
  created_at timestamptz NOT NULL DEFAULT now()
);
