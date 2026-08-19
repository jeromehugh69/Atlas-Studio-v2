ALTER TABLE agents
  ADD COLUMN IF NOT EXISTS requires_user_authorization boolean NOT NULL DEFAULT false;

INSERT INTO agents (id, workspace_id, name, role, description, tools, read_only, requires_user_authorization) VALUES
('10000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001','Atlas','Platform Intelligence Orchestrator','Receives the user direction, maintains read-only platform awareness, and coordinates approved work without implementation permissions.','["diagnostics","research","investigation","memory_read","files_read"]',true,false),
('10000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000001','Forge','Platform Development AI','Primary implementation assistant. Builds and changes platform components only after explicit user authorization.','["memory_read","files_read","files_write","code_execute","test_execute"]',false,true),
('10000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000001','Sentinel','Security Engineering','Performs threat modeling, secure-code review, dependency analysis, vulnerability triage, and hardening guidance.','["diagnostics","investigation","memory_read","files_read","security_scan"]',true,true),
('10000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000001','Verity','GRC and Compliance','Maps controls, evaluates governance and risk, prepares evidence, and reviews compliance obligations.','["research","investigation","memory_read","files_read","compliance_review","document_generate"]',true,false),
('10000000-0000-0000-0000-000000000005','00000000-0000-0000-0000-000000000001','Quanta','Quality and Test Engineering','Designs test plans, creates authorized automated tests, validates releases, and tracks quality gates.','["diagnostics","memory_read","files_read","files_write","code_execute","test_execute"]',false,true),
('10000000-0000-0000-0000-000000000006','00000000-0000-0000-0000-000000000001','Sage','Research and Development','Investigates technologies, evaluates options, runs approved experiments, and produces recommendations.','["research","investigation","memory_read","files_read","browser"]',true,false),
('10000000-0000-0000-0000-000000000007','00000000-0000-0000-0000-000000000001','Counsel','AI Legal Advisor','Provides legal issue spotting, licensing review, policy research, and draft guidance for human review.','["research","memory_read","files_read","legal_review","document_generate"]',true,false),
('10000000-0000-0000-0000-000000000008','00000000-0000-0000-0000-000000000001','Scribe','Document Engineering','Creates technical documentation, procedures, specifications, reports, and release documentation.','["memory_read","files_read","files_write","document_generate"]',false,true),
('10000000-0000-0000-0000-000000000009','00000000-0000-0000-0000-000000000001','Pixel','Image and Visual Generation','Produces approved interface concepts, product imagery, diagrams, and visual assets using local models.','["memory_read","files_read","files_write","image_generate"]',false,true),
('10000000-0000-0000-0000-000000000010','00000000-0000-0000-0000-000000000001','Blueprint','Architecture and Blueprint Generation','Designs system architecture, data flows, infrastructure diagrams, implementation plans, and blueprints.','["research","memory_read","files_read","document_generate","blueprint_generate"]',true,false),
('10000000-0000-0000-0000-000000000011','00000000-0000-0000-0000-000000000001','Nexus','API and Integration Engineering','Designs provider-neutral APIs, contracts, connectors, and integration boundaries.','["memory_read","files_read","files_write","code_execute","test_execute"]',false,true),
('10000000-0000-0000-0000-000000000012','00000000-0000-0000-0000-000000000001','DataCore','Data Engineering','Designs schemas, migrations, semantic-memory pipelines, retention controls, and safe data operations.','["memory_read","files_read","files_write","code_execute","database_admin"]',false,true),
('10000000-0000-0000-0000-000000000013','00000000-0000-0000-0000-000000000001','Interface','UX and Frontend Engineering','Designs accessible product experiences and implements approved frontend interaction systems.','["research","memory_read","files_read","files_write","code_execute","browser","test_execute"]',false,true),
('10000000-0000-0000-0000-000000000014','00000000-0000-0000-0000-000000000001','Release','DevOps and Reliability','Maintains build, deployment, observability, recovery, and release processes under authorization.','["diagnostics","memory_read","files_read","files_write","code_execute","deployment"]',false,true),
('10000000-0000-0000-0000-000000000015','00000000-0000-0000-0000-000000000001','Echo','Voice and Experience Coordinator','Coordinates local speech, voice-session behavior, and approved avatar experiences.','["speech","avatar","memory_read","files_read"]',true,false)
ON CONFLICT (id) DO UPDATE SET
  name=EXCLUDED.name,
  role=EXCLUDED.role,
  description=EXCLUDED.description,
  tools=EXCLUDED.tools,
  read_only=EXCLUDED.read_only,
  requires_user_authorization=EXCLUDED.requires_user_authorization;
