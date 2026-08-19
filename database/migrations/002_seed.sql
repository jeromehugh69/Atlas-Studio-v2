INSERT INTO workspaces (id, name, root_path)
VALUES ('00000000-0000-0000-0000-000000000001', 'Local Workspace', '/var/lib/atlas-studio/workspaces/default')
ON CONFLICT (root_path) DO NOTHING;

INSERT INTO agents (id, workspace_id, name, role, description, tools, read_only) VALUES
('10000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001','Atlas','Platform Intelligence','Continuous read-only diagnostics, research, investigation, and approved avatar generation across the production platform.','["diagnostics","research","investigation","memory_read","files_read","avatar_generate"]',true),
('10000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000001','Forge','Implementation Engineer','Builds and changes approved platform components inside isolated workspaces.','["memory_read","files_read","files_write","code_execute"]',false),
('10000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000001','Sage','Research Analyst','Synthesizes local knowledge and approved research sources.','["research","investigation","memory_read","files_read"]',false),
('10000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000001','Echo','Experience Coordinator','Coordinates local speech and avatar experiences.','["speech","avatar","memory_read"]',false)
ON CONFLICT (id) DO NOTHING;
