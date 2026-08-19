ALTER TABLE agents
  ADD COLUMN IF NOT EXISTS skills jsonb NOT NULL DEFAULT '["development_lifecycle"]'::jsonb;

UPDATE agents
SET skills = CASE
  WHEN name = 'Atlas' THEN '["development_lifecycle", "atlas_request_intake"]'::jsonb
  ELSE COALESCE(skills, '["development_lifecycle"]'::jsonb)
END;
